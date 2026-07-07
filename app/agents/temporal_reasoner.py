"""Layer 3 · 时序推理 Agent。评估候选疾病与患者时序特征的匹配度。

KnowS 策略（PRD §4.2 Layer 3）：
- 源：paper_en + guide
- 查询：疾病名 + "natural history"
- 目的：验证疾病自然史时序模式
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..reasoning.bayesian import load_disease_meta
from ..reasoning.temporal_logic import compute_temporal_match
from ..state.session import PhenotypeProfile, TemporalMatch
from ..tools.knows_client import KnowsClient, LAYER_SOURCES

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def run(state: dict | Any) -> dict:
    """Layer 3 入口：对每个候选假设计算时序匹配度。"""
    if hasattr(state, "hypotheses"):
        hypotheses = state.hypotheses
        profile = state.phenotype_profile
    else:
        hypotheses = state.get("hypotheses", []) if isinstance(state, dict) else []
        profile = state.get("phenotype_profile") if isinstance(state, dict) else None

    if not hypotheses or not profile:
        return {"temporal_matches": []}

    meta_db = load_disease_meta()
    matches: list[TemporalMatch] = []
    for h in hypotheses[:5]:  # 仅 Top-5 计算时序（性能）
        meta = meta_db.get(h.disease_id, {})
        if not meta:
            continue
        tm = compute_temporal_match(h.disease_id, h.disease_name, profile, meta)
        matches.append(tm)

    return {"temporal_matches": matches}


async def run_with_knows(state: dict | Any, knows_client: KnowsClient) -> dict:
    """Layer 3 异步版：时序匹配 + KnowS 检索自然史文献。"""
    result = run(state)
    matches: list[TemporalMatch] = result.get("temporal_matches", [])

    if not matches:
        return result

    all_evidence_ids: list[str] = []
    all_evidences: list = []

    for tm in matches[:3]:  # Top-3 检索
        # 用疾病 ID 查询疾病名
        meta_db = load_disease_meta()
        meta = meta_db.get(tm.disease_id, {})
        disease_name = meta.get("name", tm.disease_id)
        query = f"{disease_name} natural history onset progression"
        try:
            evidences = await knows_client.search(
                sources=LAYER_SOURCES["layer3"],
                query=query,
                retrieved_layer="layer3",
                top_k=3,
            )
            if evidences:
                all_evidence_ids.extend([ev.id for ev in evidences])
                all_evidences.extend(evidences)
        except Exception:
            pass

    if all_evidence_ids:
        result["current_layer_evidence_ids"] = all_evidence_ids
        result["current_layer_evidences"] = all_evidences

    return result
