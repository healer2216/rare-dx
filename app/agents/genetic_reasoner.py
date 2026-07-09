"""Layer 4 · 遗传推理 Agent。基于家系信息推断遗传模式，约束候选疾病。

KnowS 策略（PRD §4.2 Layer 4）：
- 源：guide
- 查询：疾病名 + "inheritance pattern"
- 目的：确认遗传模式
回流：若 Top-1 假设被遗传约束排除，触发 genetic → hypothesis 回流
"""

from __future__ import annotations

from typing import Any

from ..reasoning.bayesian import load_disease_meta
from ..reasoning.inheritance import compute_genetic_constraint
from ..tools.knows_client import KnowsClient, LAYER_SOURCES
from ..tools.llm_gateway import LLMGateway


def run(state: dict | Any) -> dict:
    """Layer 4 入口：推断遗传模式 + 检查假设兼容性 + 触发回流。"""
    print("[L4] genetic_reasoner start", flush=True)
    if hasattr(state, "hypotheses"):
        hypotheses = state.hypotheses
    else:
        hypotheses = state.get("hypotheses", []) if isinstance(state, dict) else []

    if not hypotheses:
        return {
            "genetic_constraint": None,
            "current_backflow_to_hypothesis": False,
        }

    # 家系信息（演示 D1 第1轮无家系数据）
    pedigree = None
    if hasattr(state, "patient_profile"):
        pp = state.patient_profile
        pedigree = getattr(pp, "structured", {}).get("pedigree") if pp else None
    elif isinstance(state, dict):
        pp = state.get("patient_profile")
        if pp and isinstance(pp, dict):
            pedigree = pp.get("structured", {}).get("pedigree")

    meta_db = load_disease_meta()
    # 兜底：LLM 假设的 disease_id 不在 meta_db 时，compute_genetic_constraint 应容错
    constraint = compute_genetic_constraint(pedigree, hypotheses, meta_db)

    # 回流判定：Top-1 假设被排除
    backflow = False
    if hypotheses and constraint:
        top1_id = hypotheses[0].disease_id
        if top1_id in constraint.incompatible_diseases:
            backflow = True

    # 读取回流计数
    if hasattr(state, "current_backflow_iterations"):
        iter_count = state.current_backflow_iterations
    else:
        iter_count = state.get("current_backflow_iterations", 0) if isinstance(state, dict) else 0

    # 达到上限不再回流
    if iter_count >= 2:
        backflow = False

    return {
        "genetic_constraint": constraint,
        "current_backflow_to_hypothesis": backflow,
    }


async def run_with_knows(
    state: dict | Any,
    knows_client: KnowsClient,
    llm_gateway: LLMGateway | None = None,
) -> dict:
    """Layer 4 异步版：遗传推理 + KnowS 检索遗传咨询指南。

    若传入 llm_gateway，对推断的遗传模式 + Top-3 候选生成 LLM 自然语言解释。
    """
    result = run(state)
    constraint = result.get("genetic_constraint")

    if not constraint or not constraint.inheritance_patterns:
        return result

    meta_db = load_disease_meta()
    all_evidence_ids: list[str] = []
    all_evidences: list = []

    # 对 Top-3 假设检索遗传模式文献
    hypotheses = state.hypotheses if hasattr(state, "hypotheses") else state.get("hypotheses", [])
    for h in hypotheses[:3]:
        meta = meta_db.get(h.disease_id, {})
        # 兜底：LLM 假设无 meta → 用 disease_name 作查询
        disease_name = meta.get("name") or h.disease_name or h.disease_id
        query = f"{disease_name} inheritance pattern genetic counseling"
        try:
            evidences = await knows_client.search_single_source(
                source=LAYER_SOURCES["layer4"][0],
                query=query,
                retrieved_layer="layer4",
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

    # ===== LLM 遗传模式解释 =====
    if llm_gateway is not None and constraint and constraint.inheritance_patterns:
        try:
            explanation = await _explain_inheritance_with_llm(
                constraint, hypotheses[:3] if hypotheses else [], meta_db, llm_gateway
            )
            # 写入首个遗传模式的 supporting_evidence
            constraint.inheritance_patterns[0].supporting_evidence.append(
                f"LLM解释: {explanation}"
            )
            result["llm_explained"] = True
        except Exception:
            result["llm_explained"] = False

    return result


# ========== LLM 遗传模式解释 ==========

_INHER_SYSTEM_PROMPT = """你是罕见病遗传咨询专家。基于推断的遗传模式与候选疾病，生成简明遗传咨询说明（2-3句）。

含：为何该遗传模式契合患者表型、与Top候选的匹配/矛盾、遗传咨询要点（如再发风险、产前诊断建议）。
面向执业医师，禁止确诊语气，基于提供数据不编造。输出纯文本，不要JSON，不要解释，仅输出说明。"""


async def _explain_inheritance_with_llm(
    constraint: Any,
    hypotheses: list,
    meta_db: dict,
    llm_gateway: LLMGateway,
) -> str:
    """用 LLM 生成遗传模式契合度说明（单字段，flash 最稳）。"""
    # 构造输入
    parts: list[str] = []
    for p in constraint.inheritance_patterns[:2]:
        parts.append(f"推断模式: {p.mode.value}(置信度={p.confidence:.2f})")
    compat = constraint.compatible_diseases[:3]
    incompat = constraint.incompatible_diseases[:3]
    if compat:
        parts.append(f"兼容假设: {', '.join(compat[:3])}")
    if incompat:
        parts.append(f"不兼容假设: {', '.join(incompat[:3])}")

    for h in hypotheses[:3]:
        meta = meta_db.get(h.disease_id, {})
        mode = meta.get("inheritance_mode") or meta.get("inheritance_modes") or "未知"
        parts.append(f"{h.disease_name}(期望遗传模式={mode}, 后验={h.bayesian_score:.2f})")

    input_text = " | ".join(parts) if parts else "遗传推理结果为空"
    messages = [
        {"role": "system", "content": _INHER_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 遗传推理结果\n{input_text}\n\n请生成遗传咨询说明。"},
    ]
    result = await llm_gateway.chat("genetic_reasoner", messages, temperature=0.2)
    return result.strip() if isinstance(result, str) else ""
