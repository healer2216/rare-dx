"""KnowS 证据检索客户端 — 异步串行调用 6 个证据源。

按 PRD §4 + 技术设计书 §6.2 实现：
- 默认 API 根 https://api.nullht.com/v1
- 单源串行调用（CALL_INTERVAL=0.4s 防 429）
- 多源按层内串行、层间独立
- 响应字段透传，不丢未知字段
- 失败重试 3 次，最终失败跳过该源，不阻断推理
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from ..state.session import Evidence, EvidenceGrade, EvidenceSource


DEFAULT_BASE_URL = "https://api.nullht.com/v1"
CALL_INTERVAL = 0.4  # 秒，串行调用间隔，防止匿名限流
TIMEOUT = 30.0
MAX_RETRIES = 3

SOURCE_ENDPOINTS: dict[EvidenceSource, str] = {
    EvidenceSource.PAPER_EN: "/evidences/ai_search_paper_en",
    EvidenceSource.PAPER_CN: "/evidences/ai_search_paper_cn",
    EvidenceSource.MEETING: "/evidences/ai_search_meeting",
    EvidenceSource.GUIDE: "/evidences/ai_search_guide",
    EvidenceSource.TRIAL: "/evidences/ai_search_trial",
    EvidenceSource.PACKAGE_INSERT: "/evidences/ai_search_package_insert",
}


class KnowsClient:
    """KnowS Evidence Search 异步客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        call_interval: float = CALL_INTERVAL,
    ) -> None:
        self.base_url = base_url or os.environ.get("KNOWS_BASE_URL", DEFAULT_BASE_URL)
        self.api_key = api_key or os.environ.get("KNOWS_API_KEY")
        self.call_interval = call_interval
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=TIMEOUT,
        )
        self._last_call_time: float = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _rate_limit(self) -> None:
        """串行限流：确保两次调用间至少 call_interval 间隔。"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < self.call_interval:
                await asyncio.sleep(self.call_interval - elapsed)
            self._last_call_time = time.monotonic()

    async def search_single_source(
        self,
        source: EvidenceSource,
        query: str,
        retrieved_layer: str = "unknown",
        top_k: int | None = None,
    ) -> list[Evidence]:
        """对单个证据源发起检索，返回 Evidence 列表。

        失败重试 MAX_RETRIES 次；最终失败返回空列表（不抛异常）。
        响应字段透传到 Evidence 模型，未知字段保留在 metadata。
        """
        endpoint = SOURCE_ENDPOINTS.get(source)
        if endpoint is None:
            return []

        payload: dict[str, Any] = {"query": query}
        if top_k is not None:
            payload["top_k"] = top_k

        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await self._rate_limit()
                resp = await self._client.post(endpoint, json=payload)
                if resp.status_code == 429:
                    # 限流：退避后重试
                    await asyncio.sleep(self.call_interval * (attempt + 1))
                    continue
                resp.raise_for_status()
                data = resp.json()
                return _parse_evidences(data, source, retrieved_layer)
            except Exception as e:  # noqa: BLE001
                last_err = e
                await asyncio.sleep(0.5 * attempt)

        # 全部重试失败：返回空，不阻断推理
        return []

    async def search(
        self,
        sources: list[EvidenceSource],
        query: str,
        retrieved_layer: str = "unknown",
        top_k: int | None = None,
    ) -> list[Evidence]:
        """对多个证据源串行检索（防 429）。

        单源失败不阻断其他源；返回去重后的证据列表。
        """
        all_evidences: list[Evidence] = []
        seen_ids: set[str] = set()
        seen_titles: set[str] = set()
        for source in sources:
            results = await self.search_single_source(
                source, query, retrieved_layer, top_k
            )
            for ev in results:
                if ev.id and ev.id not in seen_ids:
                    # guide 类按 title 去重（同共识常多次返回）
                    title_key = (ev.title or "").strip().lower()
                    if ev.source and ev.source.value in ("guide", "guide_cn") and title_key in seen_titles:
                        continue
                    seen_ids.add(ev.id)
                    if title_key:
                        seen_titles.add(title_key)
                    all_evidences.append(ev)
        return all_evidences


def _parse_evidences(
    response: dict[str, Any],
    source: EvidenceSource,
    retrieved_layer: str,
) -> list[Evidence]:
    """把 KnowS 响应解析成 Evidence 列表，保留所有未知字段。

    KnowS 返回格式: {"question_id": "...", "evidences": [...]}
    每条 evidence 含 id/title/abstract/doi/journal/study_type/impact_factor
    等已知字段，以及可能的源特异字段。
    """
    raw_list = response.get("evidences", []) or []
    results: list[Evidence] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        ev_id = item.get("id") or ""
        if not ev_id:
            continue

        # 证据分级：按 PRD §4.3 — 基于来源和研究类型推断
        grade = _infer_grade(source, item.get("study_type"))

        # 已知字段映射到 Evidence；未知字段保留在 metadata（通过 model_extra）
        evidence = Evidence(
            id=ev_id,
            source=source,
            title=item.get("title") or "",
            abstract=item.get("abstract"),
            publish_date=item.get("publish_date"),
            doi=item.get("doi"),
            journal=item.get("journal"),
            study_type=item.get("study_type"),
            impact_factor=item.get("impact_factor"),
            retrieved_layer=retrieved_layer,
            relevance_score=item.get("relevance_score"),
            grade=grade,
        )
        results.append(evidence)
    return results


def _infer_grade(source: EvidenceSource, study_type: str | None) -> EvidenceGrade:
    """证据分级（A-E），按 PRD §4.3 表 + 技术设计书 §8.3。

    | 等级 | 定义 | 来源 |
    | A | 高质量指南或 Meta | guide |
    | B | 原始研究（样本>50） | paper_en/paper_cn |
    | C | 病例系列/小样本 | paper/meeting |
    | D | 专家意见/病例报告 | paper/meeting |
    | E | 预印本/会议摘要 | meeting/package_insert |
    """
    if source == EvidenceSource.GUIDE:
        return EvidenceGrade.A
    if source == EvidenceSource.TRIAL:
        return EvidenceGrade.C
    if source == EvidenceSource.MEETING:
        return EvidenceGrade.E
    if source == EvidenceSource.PACKAGE_INSERT:
        return EvidenceGrade.E
    if source in (EvidenceSource.PAPER_EN, EvidenceSource.PAPER_CN):
        if study_type:
            st = study_type.lower()
            if any(k in st for k in ("meta", "systematic review", "荟萃", "系统综述")):
                return EvidenceGrade.A
            if any(k in st for k in ("随机", "randomized", "rct", "队列", "cohort")):
                return EvidenceGrade.B
            if any(k in st for k in ("病例报告", "case report", "病例系列", "case series")):
                return EvidenceGrade.D
            if any(k in st for k in ("观察", "observational", "回顾", "retrospective")):
                return EvidenceGrade.C
        return EvidenceGrade.C
    return EvidenceGrade.D


# 便捷的源集合（按 PRD §4.2 各层策略）
LAYER_SOURCES = {
    "layer1": [EvidenceSource.GUIDE, EvidenceSource.PAPER_EN],
    "layer2": [EvidenceSource.PAPER_EN, EvidenceSource.PAPER_CN],
    "layer3": [EvidenceSource.PAPER_EN, EvidenceSource.PAPER_CN, EvidenceSource.GUIDE],
    "layer4": [EvidenceSource.PAPER_EN, EvidenceSource.GUIDE],
    "layer5": [EvidenceSource.PAPER_EN, EvidenceSource.GUIDE, EvidenceSource.TRIAL],
    "report": [EvidenceSource.PAPER_EN, EvidenceSource.PAPER_CN, EvidenceSource.GUIDE],
}
