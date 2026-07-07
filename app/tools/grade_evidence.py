"""证据分级与聚合工具 — 按 PRD §4.3 证据强度计算。"""

from __future__ import annotations

from typing import Iterable

from ..state.session import Evidence, EvidenceGrade


# 等级权重表（PRD §4.3）：A=5, B=4, C=3, D=2, E=1
GRADE_WEIGHTS: dict[EvidenceGrade, int] = {
    EvidenceGrade.A: 5,
    EvidenceGrade.B: 4,
    EvidenceGrade.C: 3,
    EvidenceGrade.D: 2,
    EvidenceGrade.E: 1,
}


def compute_evidence_strength(evidences: Iterable[Evidence]) -> tuple[str, float]:
    """计算一组证据的综合强度等级。

    按技术设计书 §4.3 公式：
        evidence_strength = Σ(grade_weight_i × count_i) / Σ count_i
    返回 (letter_grade, numeric_score)：
    - letter_grade: 综合权重对应的最高字母等级（A-E）
    - numeric_score: 0-1 归一化分数（用于排序展示）
    """
    evidences = list(evidences)
    if not evidences:
        return ("E", 0.0)

    total_weight = 0
    grade_counts: dict[EvidenceGrade, int] = {}
    for ev in evidences:
        g = ev.grade or EvidenceGrade.D
        grade_counts[g] = grade_counts.get(g, 0) + 1
        total_weight += GRADE_WEIGHTS.get(g, 2)

    total_count = sum(grade_counts.values())
    if total_count == 0:
        return ("E", 0.0)

    weighted_avg = total_weight / total_count  # 1.0-5.0
    # 映射到字母等级：5=A, 4=B, 3=C, 2=D, 1=E
    if weighted_avg >= 4.5:
        letter = "A"
    elif weighted_avg >= 3.5:
        letter = "B"
    elif weighted_avg >= 2.5:
        letter = "C"
    elif weighted_avg >= 1.5:
        letter = "D"
    else:
        letter = "E"

    # 归一化到 0-1
    score = (weighted_avg - 1.0) / 4.0
    return (letter, round(score, 3))


def best_grade(evidences: Iterable[Evidence]) -> EvidenceGrade:
    """返回证据列表中最高等级。"""
    best = EvidenceGrade.E
    best_w = 0
    for ev in evidences:
        w = GRADE_WEIGHTS.get(ev.grade or EvidenceGrade.D, 2)
        if w > best_w:
            best_w = w
            best = ev.grade or EvidenceGrade.D
    return best


def format_citation(ev: Evidence) -> str:
    """格式化单条证据为引用字符串。"""
    parts: list[str] = []
    if ev.doi:
        parts.append(f"DOI:{ev.doi}")
    elif ev.id:
        parts.append(f"ID:{ev.id[:12]}")
    if ev.journal:
        parts.append(ev.journal)
    if ev.publish_date:
        parts.append(str(ev.publish_date)[:7])
    if ev.grade:
        parts.append(f"Grade {ev.grade.value}")
    return " · ".join(parts) if parts else ev.title[:60]
