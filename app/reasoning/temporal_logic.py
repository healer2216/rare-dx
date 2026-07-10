"""时序推理算法 — 发病年龄 + 进展模式 + 症状序列匹配。

按技术设计书 §3.2 实现：
- match_onset_age: 发病年龄高斯衰减匹配
- match_progression: 进展模式精确匹配 + 部分兼容映射
- match_sequence: LCS 最长公共子序列
- compute_temporal_match: 综合 3 维加权评分
"""

from __future__ import annotations

import math
from typing import Any

from ..state.session import PhenotypeProfile, TemporalMatch


# 进展模式部分兼容映射（双向）
_COMPAT_MAP: dict[tuple[str, str], float] = {
    ("acute", "subacute"): 0.6,
    ("subacute", "acute"): 0.6,
    ("chronic_progressive", "chronic_static"): 0.3,
    ("chronic_static", "chronic_progressive"): 0.3,
    ("fluctuating", "relapsing"): 0.5,
    ("relapsing", "fluctuating"): 0.5,
    ("chronic_progressive", "subacute"): 0.4,
    ("subacute", "chronic_progressive"): 0.4,
}

# 综合评分权重（PRD/技术设计书一致）
WEIGHTS = {"onset": 0.40, "progression": 0.35, "sequence": 0.25}


def match_onset_age(
    patient_onset_years: float,
    typical_min: float,
    typical_max: float,
    variability: float = 0.3,
) -> float:
    """发病年龄匹配度 (0-1)。

    在 [min, max] 范围内 → 1.0；偏离越远 → 高斯衰减。
    """
    if typical_min <= patient_onset_years <= typical_max:
        return 1.0
    mid = (typical_min + typical_max) / 2.0
    spread = max((typical_max - typical_min) / 2.0, 0.5)
    sigma = spread * (1.0 + variability) + 0.5
    distance = abs(patient_onset_years - mid)
    # 高斯衰减：距离 1σ → 0.6, 2σ → 0.14
    score = math.exp(-(distance ** 2) / (2 * sigma ** 2))
    return round(max(score, 0.0), 4)


def match_progression(
    patient_pattern: str | None,
    disease_speed: str,
) -> float:
    """进展模式匹配度 (0-1)。"""
    if not patient_pattern:
        return 0.5  # 无信息时中性
    if patient_pattern == disease_speed:
        return 1.0
    return _COMPAT_MAP.get((patient_pattern, disease_speed), 0.1)


def match_sequence(
    patient_hpo_ids: list[str],
    expected_sequence: list[str],
) -> float:
    """症状出现序列匹配度 — LCS 最长公共子序列。"""
    if not expected_sequence:
        return 0.5  # 无参考序列时中性
    m, n = len(patient_hpo_ids), len(expected_sequence)
    if m == 0:
        return 0.0
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if patient_hpo_ids[i - 1] == expected_sequence[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]
    return round(lcs_len / max(n, 1), 4)


def _age_to_years(age: float | None, unit: str | None) -> float | None:
    if age is None:
        return None
    if unit == "months":
        return age / 12.0
    if unit == "days":
        return age / 365.0
    if unit == "weeks":
        return age / 52.0
    return float(age)


def compute_temporal_match(
    disease_id: str,
    disease_name: str,
    phenotype_profile: PhenotypeProfile,
    disease_meta: dict[str, Any],
) -> TemporalMatch:
    """对单个疾病计算时序匹配评分（发病年龄 + 进展模式 + 症状序列）。"""
    print(f"[temporal] compute_temporal_match start disease={disease_name}", flush=True)
    """Layer 3 核心：综合时序匹配评分。"""
    onset_meta = disease_meta.get("typical_onset", {})
    prog_meta = disease_meta.get("progression", {})

    # 患者发病年龄
    patient_onset = None
    for v in phenotype_profile.vectors:
        if v.onset_age is not None:
            patient_onset = _age_to_years(v.onset_age, v.onset_age_unit)
            break
    if patient_onset is None:
        # 用人口学年龄作为后备
        demo = phenotype_profile.demographic or {}
        patient_onset = _age_to_years(demo.get("age"), demo.get("age_unit"))
    if patient_onset is None:
        patient_onset = 30.0  # 默认成人

    onset_c = match_onset_age(
        patient_onset,
        onset_meta.get("age_min", 0.0),
        onset_meta.get("age_max", 80.0),
        onset_meta.get("variability", 0.5),
    )

    # 患者进展模式：从表型修饰符提取
    patient_pattern = None
    for v in phenotype_profile.vectors:
        for m in v.modifiers:
            if m.temporal_pattern:
                patient_pattern = m.temporal_pattern
                break
        if patient_pattern:
            break

    prog_c = match_progression(patient_pattern, prog_meta.get("speed", "chronic_progressive"))

    seq_c = match_sequence(
        [v.hpo_id for v in phenotype_profile.vectors],
        disease_meta.get("expected_sequence", []),
    )

    overall = (
        WEIGHTS["onset"] * onset_c
        + WEIGHTS["progression"] * prog_c
        + WEIGHTS["sequence"] * seq_c
    )

    return TemporalMatch(
        disease_id=disease_id,
        onset_consistency=onset_c,
        progression_consistency=prog_c,
        sequence_consistency=seq_c,
        overall_temporal_score=round(overall, 4),
        notes=f"onset={onset_c:.2f} prog={prog_c:.2f} seq={seq_c:.2f}",
    )
