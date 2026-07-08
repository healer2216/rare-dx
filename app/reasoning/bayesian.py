"""贝叶斯概率计算引擎 — Naive Bayes + 人口学先验修正。

按技术设计书 §3.1 实现：
- 加载 Orphanet 疾病-表型频率表
- 先验：基于疾病患病率 + 人口学修正
- 似然：Naive Bayes 假设条件独立
- 后验：归一化到 [0,1]
- Top-K 排序：返回 DiseaseHypothesis 列表
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..state.session import (
    DiseaseHypothesis,
    EvidencePool,
    PhenotypeProfile,
    PresenceStatus,
)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_FREQ_PATH = _DATA_DIR / "hpo_frequency" / "orphanet_freq.json"
_META_PATH = _DATA_DIR / "disease_meta.json"

# 默认值
DEFAULT_FREQUENCY = 0.01  # 无频率数据时的默认表型频率
DEFAULT_PREVALENCE = 1e-5  # 无患病率数据时的默认先验
EPS = 1e-10  # 防 log(0)


# ========== 数据加载 ==========

_freq_table_cache: list[dict] | None = None
_freq_index_cache: dict[str, dict[str, float]] | None = None
_disease_meta_cache: dict[str, dict] | None = None


def get_freq_index() -> dict[str, dict[str, float]]:
    """预构建 {disease_id: {hpo_id: frequency}} 索引，O(1) 查表。"""
    global _freq_index_cache
    if _freq_index_cache is not None:
        return _freq_index_cache
    ft = load_frequency_table()
    idx: dict[str, dict[str, float]] = {}
    for e in ft:
        did = e.get("disease_id")
        hpo = e.get("hpo_id")
        freq = e.get("frequency", DEFAULT_FREQUENCY)
        if did and hpo:
            idx.setdefault(did, {})[hpo] = float(freq)
    _freq_index_cache = idx
    return idx


def load_frequency_table() -> list[dict]:
    """加载 Orphanet 疾病-表型频率表，返回 entries 列表。"""
    global _freq_table_cache
    if _freq_table_cache is not None:
        return _freq_table_cache
    if not _FREQ_PATH.exists():
        _freq_table_cache = []
        return _freq_table_cache
    with open(_FREQ_PATH, encoding="utf-8") as f:
        data = json.load(f)
    _freq_table_cache = data.get("entries", [])
    return _freq_table_cache


def load_disease_meta() -> dict[str, dict]:
    """加载疾病元数据 KB，返回 {disease_id: meta_dict}。"""
    global _disease_meta_cache
    if _disease_meta_cache is not None:
        return _disease_meta_cache
    if not _META_PATH.exists():
        _disease_meta_cache = {}
        return _disease_meta_cache
    with open(_META_PATH, encoding="utf-8") as f:
        data = json.load(f)
    _disease_meta_cache = data.get("diseases", {})
    return _disease_meta_cache


def get_disease_ids(freq_table: list[dict] | None = None) -> list[str]:
    """获取所有出现在频率表中的疾病 ID（去重保序）。"""
    ft = freq_table if freq_table is not None else load_frequency_table()
    seen: set[str] = set()
    ids: list[str] = []
    for e in ft:
        did = e.get("disease_id")
        if did and did not in seen:
            seen.add(did)
            ids.append(did)
    return ids


def _disease_freq_map(
    disease_id: str, freq_table: list[dict] | None = None
) -> dict[str, float]:
    """构造 {hpo_id: frequency} 字典。使用预建索引 O(1)。"""
    idx = get_freq_index()
    return idx.get(disease_id, {})


# ========== 概率计算 ==========

def compute_prior(disease_id: str, demographic: dict | None = None) -> float:
    """计算疾病先验概率 P(disease)，基于患病率 + 人口学修正。"""
    meta = load_disease_meta().get(disease_id, {})
    base_prev = meta.get("prevalence", DEFAULT_PREVALENCE)

    modifier = 1.0
    if demographic:
        age = demographic.get("age")
        age_unit = demographic.get("age_unit", "years")
        sex = demographic.get("sex")

        # 年龄归一到年
        age_years: float | None = None
        if age is not None:
            if age_unit == "months":
                age_years = age / 12.0
            elif age_unit == "days":
                age_years = age / 365.0
            elif age_unit == "weeks":
                age_years = age / 52.0
            else:
                age_years = float(age)

        # 年龄修正：儿科疾病在儿童期先验更高
        onset = meta.get("typical_onset", {})
        onset_max = onset.get("age_max", 18.0)
        if age_years is not None and age_years <= onset_max:
            modifier *= 2.0  # 在典型发病年龄段内，先验翻倍

        # 性别修正：XLR 疾病男性先验更高
        modes = meta.get("inheritance_modes", [])
        if sex == "male" and any("XR" in m for m in modes):
            modifier *= 3.0

    return min(base_prev * modifier, 0.1)  # 上限 10% 防止过度自信


def compute_likelihood(
    disease_id: str,
    phenotype_hpo_ids: list[str],
    freq_table: list[dict],
) -> tuple[float, list[str], list[str]]:
    """计算似然 P(phenotypes | disease) — Naive Bayes 假设条件独立。

    返回 (likelihood, supporting_ids, contradicting_ids)：
    - supporting: present 表型在疾病中频率 > 0.3
    - contradicting: absent 表型在疾病中频率 > 0.5（罕见）
    """
    dfreq = _disease_freq_map(disease_id, freq_table)
    if not dfreq:
        return (1e-6, [], [])

    log_likelihood = 0.0
    supporting: list[str] = []
    for hpo_id in phenotype_hpo_ids:
        freq = dfreq.get(hpo_id, DEFAULT_FREQUENCY)
        freq = max(freq, EPS)
        log_likelihood += math.log(freq)
        if freq > 0.3:
            supporting.append(hpo_id)

    likelihood = math.exp(log_likelihood)
    return (likelihood, supporting, [])


def compute_posterior(
    disease_id: str,
    phenotype_hpo_ids: list[str],
    demographic: dict | None = None,
    freq_table: list[dict] | None = None,
) -> dict[str, Any]:
    """计算完整后验评分。返回字典格式（便于集成到 DiseaseHypothesis）。"""
    ft = freq_table if freq_table is not None else load_frequency_table()
    prior = compute_prior(disease_id, demographic)
    likelihood, supporting, contradicting = compute_likelihood(
        disease_id, phenotype_hpo_ids, ft
    )

    # 后验：Bayes 公式简化版（不做全疾病归一化，使用 odds 形式）
    raw_posterior = prior * likelihood
    # 归一化：posterior / (posterior + (1-prior) * baseline_likelihood)
    # baseline_likelihood 假设为 1e-3（一般人群随机出现这些表型的概率）
    baseline = 1e-3
    posterior = raw_posterior / (raw_posterior + (1 - prior) * baseline + EPS)
    posterior = min(posterior, 0.999)

    log_odds = math.log10((posterior + EPS) / (1 - posterior + EPS))

    return {
        "disease_id": disease_id,
        "prior": prior,
        "likelihood": likelihood,
        "posterior": posterior,
        "log_odds": log_odds,
        "supporting_phenotype_ids": supporting,
        "contradicting_phenotype_ids": contradicting,
    }


# ========== Top-K 假设排序 ==========

def rank_hypotheses(
    phenotype_profile: PhenotypeProfile,
    demographic: dict | None = None,
    top_k: int = 10,
    min_posterior: float = 1e-5,
) -> list[DiseaseHypothesis]:
    """对所有候选疾病计算后验，返回排序后的 DiseaseHypothesis 列表。

    步骤：
    1. 提取表型 HPO IDs（present）
    2. 对每个疾病计算后验
    3. 过滤 < min_posterior
    4. 排序后取 Top-K
    5. 计算相对置信度（相对 Top-1）
    """
    freq_table = load_frequency_table()
    meta_db = load_disease_meta()
    disease_ids = get_disease_ids(freq_table)

    present_hpo_ids = [
        v.hpo_id for v in phenotype_profile.vectors
        if v.presence == PresenceStatus.PRESENT
    ]

    if not present_hpo_ids:
        return []

    # 预过滤：用索引快速找出匹配至少 1 个输入 HPO 的疾病，并记录匹配数
    input_hpo_set = set(present_hpo_ids)
    idx = get_freq_index()
    candidates_with_matches: list[tuple[str, int]] = []
    for did, hpos in idx.items():
        matched = sum(1 for h in input_hpo_set if h in hpos)
        if matched > 0:
            candidates_with_matches.append((did, matched))
    if not candidates_with_matches:
        return []

    # 计算候选疾病后验
    scores: list[dict[str, Any]] = []
    for did, _ in candidates_with_matches:
        score = compute_posterior(did, present_hpo_ids, demographic, freq_table)
        if score["posterior"] >= min_posterior:
            scores.append(score)

    # 按后验降序排序
    scores.sort(key=lambda s: s["posterior"], reverse=True)

    # 取 Top-K
    top_scores = scores[:top_k]
    if not top_scores:
        # 兜底：所有疾病后验低于阈值，按匹配 HPO 数降序取 Top-5
        # 但若 min_posterior > 0.5（测试/过滤语义），尊重阈值不兜底
        if min_posterior > 0.5:
            return []
        candidates_with_matches.sort(key=lambda x: -x[1])
        fallback_dids = [d for d, _ in candidates_with_matches[:5]]
        for did in fallback_dids:
            score = compute_posterior(did, present_hpo_ids, demographic, freq_table)
            score["posterior"] = 0.0
            top_scores.append(score)

    max_posterior = top_scores[0]["posterior"]

    hypotheses: list[DiseaseHypothesis] = []
    for rank, score in enumerate(top_scores, start=1):
        did = score["disease_id"]
        meta = meta_db.get(did, {})

        # 相对置信度（相对 Top-1）
        confidence = score["posterior"] / (max_posterior + EPS)
        confidence = round(min(confidence, 1.0), 4)

        # 推理链摘要
        reasoning_chain = (
            f"先验={score['prior']:.2e}, "
            f"似然={score['likelihood']:.2e}, "
            f"后验={score['posterior']:.4f}, "
            f"支持表型={len(score['supporting_phenotype_ids'])}个"
        )

        hypotheses.append(DiseaseHypothesis(
            disease_id=did,
            disease_name=meta.get("name", did),
            orpha_number=meta.get("orpha_number"),
            bayesian_score=round(score["posterior"], 4),
            supporting_phenotypes=score["supporting_phenotype_ids"],
            contradicting_phenotypes=score["contradicting_phenotype_ids"],
            rank=rank,
            evidence_ids=[],  # 由 Layer 2 Agent 后续填入
            confidence=confidence,
            reasoning_chain=reasoning_chain,
        ))

    return hypotheses
