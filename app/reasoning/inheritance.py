"""遗传推理算法 — 家系分析 + 孟德尔遗传模式推断 + 兼容性检查。

按技术设计书 §3.3 实现：
- analyze_pedigree: 基于家系规则的遗传模式推断
- check_mendelian_consistency: 疾病已知遗传模式与家系推断的兼容性
- infer_from_phenotype: 无家系信息时从表型推断可能模式（降级路径）
"""

from __future__ import annotations

from typing import Any

from ..state.session import (
    GeneticConstraint,
    InheritanceMode,
    InheritancePattern,
)


# ========== 家系规则推断 ==========

def analyze_pedigree(pedigree: dict | None) -> list[InheritancePattern]:
    """从家系数据推断可能的遗传模式。

    规则（按 PRD §3.4）：
    - 近亲婚配 → AR 高置信
    - 连续多代受累 → AD
    - 仅男性受累 → XR
    - 母系成员受累多 → 线粒体遗传
    """
    if not pedigree or not pedigree.get("members"):
        return [InheritancePattern(
            mode=InheritanceMode.UNKNOWN,
            confidence=0.1,
            supporting_evidence=["无足够家系信息"],
        )]

    patterns: list[InheritancePattern] = []
    members = pedigree.get("members", [])
    affected = [m for m in members if m.get("affected_status") == "true"]

    if not affected:
        return [InheritancePattern(
            mode=InheritanceMode.UNKNOWN,
            confidence=0.1,
            supporting_evidence=["家系中无其他受累成员"],
        )]

    # 规则 1: 近亲婚配 → AR
    if pedigree.get("consanguinity"):
        patterns.append(InheritancePattern(
            mode=InheritanceMode.AR,
            confidence=0.8,
            supporting_evidence=["近亲婚配高度提示常染色体隐性遗传"],
        ))

    # 规则 2: 仅男性受累 → XR
    if all(m.get("sex") == "male" for m in affected):
        patterns.append(InheritancePattern(
            mode=InheritanceMode.XR,
            confidence=0.6,
            supporting_evidence=["仅男性受累提示X连锁隐性"],
        ))

    # 规则 3: 母系遗传 → Mitochondrial
    maternal_keywords = {"mother", "maternal_uncle", "maternal_aunt", "maternal_grandmother"}
    maternal_count = sum(1 for m in affected if m.get("relationship") in maternal_keywords)
    if maternal_count >= 2:
        patterns.append(InheritancePattern(
            mode=InheritanceMode.MITOCHONDRIAL,
            confidence=0.65,
            supporting_evidence=["母系成员多代受累提示线粒体遗传"],
        ))

    # 规则 4: 多代受累 → AD
    generations = set()
    gen_map = {
        "father": 0, "mother": 0, "paternal_uncle": 0, "maternal_uncle": 0,
        "sibling": 1, "self": 1, "child": 2, "nephew": 2, "niece": 2,
    }
    for m in affected:
        generations.add(gen_map.get(m.get("relationship", ""), 1))
    if len(generations) >= 2:
        patterns.append(InheritancePattern(
            mode=InheritanceMode.AD,
            confidence=0.7,
            supporting_evidence=[f"连续 {len(generations)} 代受累提示常染色体显性"],
        ))

    if not patterns:
        patterns.append(InheritancePattern(
            mode=InheritanceMode.UNKNOWN,
            confidence=0.2,
            supporting_evidence=["家系信息不足以明确遗传模式"],
        ))

    return patterns


def infer_from_phenotype(disease_meta: dict) -> InheritancePattern:
    """无家系信息时从疾病已知遗传模式降级推断。

    取疾病最可能的遗传模式，置信度中等（0.5）。
    """
    modes = disease_meta.get("inheritance_modes", [])
    if not modes:
        return InheritancePattern(
            mode=InheritanceMode.UNKNOWN,
            confidence=0.2,
            supporting_evidence=["疾病遗传模式未知"],
        )

    # 优先级：MITOCHONDRIAL > AR > XR > AD > 其他
    priority = ["MITOCHONDRIAL", "AR", "XR", "XD", "AD", "DE_NOVO"]
    for m in priority:
        if m in modes:
            return InheritancePattern(
                mode=InheritanceMode(m),
                confidence=0.5,
                supporting_evidence=[f"疾病已知遗传模式含 {m}（无家系信息降级推断）"],
            )
    # 容错：尝试直接转换，失败则返回 UNKNOWN
    try:
        return InheritancePattern(
            mode=InheritanceMode(modes[0]),
            confidence=0.4,
            supporting_evidence=[f"疾病已知遗传模式 {modes[0]}"],
        )
    except ValueError:
        return InheritancePattern(
            mode=InheritanceMode.UNKNOWN,
            confidence=0.3,
            supporting_evidence=[f"疾病遗传模式 {modes[0]} 未识别"],
        )


# ========== 兼容性检查 ==========

def check_mendelian_consistency(
    disease_id: str,
    inferred_patterns: list[InheritancePattern],
    disease_known_modes: list[str],
) -> bool:
    """检查疾病已知遗传模式与推断是否兼容。

    - 无已知模式 → 兼容（不排除）
    - 推断置信度过低（<0.4）→ 兼容（不排除）
    - 否则要求推断模式与已知模式有交集
    """
    if not disease_known_modes:
        return True

    strong_inferred = {p.mode.value for p in inferred_patterns if p.confidence > 0.4}
    if not strong_inferred:
        return True
    if "UNKNOWN" in strong_inferred:
        return True

    return bool(strong_inferred & set(disease_known_modes))


def compute_genetic_constraint(
    pedigree: dict | None,
    hypotheses: list,
    disease_meta_db: dict[str, dict],
) -> GeneticConstraint:
    """Layer 4 核心：计算遗传约束。

    返回 GeneticConstraint，含兼容/不兼容疾病列表 + 先验修正系数。
    """
    if pedigree and pedigree.get("members"):
        patterns = analyze_pedigree(pedigree)
    else:
        # 无家系信息：用 Top-1 假设的疾病元数据降级推断
        if hypotheses:
            top_disease_id = hypotheses[0].disease_id
            meta = disease_meta_db.get(top_disease_id, {})
            patterns = [infer_from_phenotype(meta)]
        else:
            patterns = [InheritancePattern(
                mode=InheritanceMode.UNKNOWN,
                confidence=0.1,
                supporting_evidence=["无家系信息且无候选假设"],
            )]

    compatible: list[str] = []
    incompatible: list[str] = []
    for h in hypotheses:
        meta = disease_meta_db.get(h.disease_id, {})
        known_modes = meta.get("inheritance_modes", [])
        if check_mendelian_consistency(h.disease_id, patterns, known_modes):
            compatible.append(h.disease_id)
        else:
            incompatible.append(h.disease_id)

    # 近亲婚配时 AR 先验修正
    prior_mod = 1.5 if (pedigree and pedigree.get("consanguinity")) else 1.0

    return GeneticConstraint(
        inheritance_patterns=patterns,
        compatible_diseases=compatible,
        incompatible_diseases=incompatible,
        prior_modifier=prior_mod,
    )
