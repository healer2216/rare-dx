"""报告综合 Agent。汇总五层推理结果生成结构化诊断辅助报告。

按 PRD §2.1 原则 2：必须含免责声明。
按 PRD §4.4：每个假设附带证据链溯源。
LLM 增强版：run_with_llm 用 LLM 生成连贯自然语言摘要。
"""

from __future__ import annotations

from typing import Any

from ..tools.grade_evidence import format_citation
from ..tools.llm_gateway import LLMGateway


def run(state: dict | Any) -> dict:
    """Layer 6 入口：综合五层推理结果，生成报告。"""
    if hasattr(state, "phenotype_profile"):
        profile = state.phenotype_profile
        hypotheses = state.hypotheses
        temporal_matches = state.temporal_matches
        genetic_constraint = state.genetic_constraint
        pathway = state.diagnostic_pathway
    else:
        profile = state.get("phenotype_profile")
        hypotheses = state.get("hypotheses", [])
        temporal_matches = state.get("temporal_matches", [])
        genetic_constraint = state.get("genetic_constraint")
        pathway = state.get("diagnostic_pathway")

    # ===== 推理摘要 =====
    sections: list[str] = []

    # Section 1: 表型分析
    if profile and profile.vectors:
        pheno_lines = [f"  • {v.hpo_id} {v.term_name}" for v in profile.vectors]
        sections.append("【Layer 1 · 表型分析】\n" + "\n".join(pheno_lines))

    # Section 2: 假设排序
    if hypotheses:
        hypo_lines = []
        for h in hypotheses[:3]:
            line = f"  #{h.rank} {h.disease_name} ({h.disease_id}) 后验={h.bayesian_score:.4f}"
            if h.evidence_ids:
                line += f" 证据={len(h.evidence_ids)}条"
            hypo_lines.append(line)
        sections.append("【Layer 2 · 假设排序 Top-3】\n" + "\n".join(hypo_lines))

    # Section 3: 时序匹配
    if temporal_matches:
        tm_lines = []
        for tm in temporal_matches[:3]:
            tm_lines.append(
                f"  • {tm.disease_id}: 综合={tm.overall_temporal_score:.2f} "
                f"(发病={tm.onset_consistency:.2f}, 进展={tm.progression_consistency:.2f})"
            )
        sections.append("【Layer 3 · 时序匹配】\n" + "\n".join(tm_lines))

    # Section 4: 遗传推理
    if genetic_constraint:
        patterns = genetic_constraint.inheritance_patterns
        pattern_str = "; ".join(
            f"{p.mode.value}(conf={p.confidence:.2f})" for p in patterns
        )
        compat_count = len(genetic_constraint.compatible_diseases)
        incompat_count = len(genetic_constraint.incompatible_diseases)
        sections.append(
            f"【Layer 4 · 遗传推理】\n"
            f"  推断模式: {pattern_str}\n"
            f"  兼容假设: {compat_count} 个 / 不兼容: {incompat_count} 个"
        )

    # Section 5: 路径规划
    if pathway and pathway.steps:
        step_lines = []
        for s in pathway.steps[:3]:
            step_lines.append(
                f"  #{s.rank} {s.test_name} (EVOI={s.net_evoi:.3f})\n"
                f"      {s.rationale}"
            )
        sections.append("【Layer 5 · 推荐检查路径 Top-3】\n" + "\n".join(step_lines))

    # ===== 不确定性说明 =====
    uncertainty = "本报告基于有限的临床信息推理，假设排序仅供参考。"
    if hypotheses:
        top1_conf = hypotheses[0].confidence
        if top1_conf < 0.3:
            uncertainty += "当前 Top-1 假设置信度较低，建议补充更多信息后再评估。"
        elif top1_conf < 0.7:
            uncertainty += "当前 Top-1 假设尚可，但鉴别诊断仍存在多种可能。"
        else:
            uncertainty += "当前 Top-1 假设较突出，但仍需进一步检查验证。"

    # ===== 证据引用汇总 =====
    citations: list[str] = []
    if hypotheses:
        for h in hypotheses[:3]:
            if h.evidence_ids:
                citations.append(f"[{h.disease_name}] {len(h.evidence_ids)} 条证据")

    # ===== 主报告文本 =====
    main_text = "\n\n".join(sections) if sections else "推理结果为空"
    main_text += "\n\n" + uncertainty
    main_text += "\n\n⚠️ 本系统输出仅供临床参考，不构成诊断意见。最终诊断由接诊医师结合完整临床信息做出。"

    # ===== 快照摘要 =====
    snapshot = ""
    if hypotheses:
        top1 = hypotheses[0]
        snapshot = (
            f"鉴别诊断 Top-1: {top1.disease_name} ({top1.disease_id}), "
            f"后验概率 {top1.bayesian_score:.4f}, "
            f"置信度 {top1.confidence:.2f}。"
        )

    return {
        "report": {
            "main_text": main_text,
            "summary_snapshot": snapshot,
            "reasoning_summary": "\n".join(sections),
            "evidence_citations": citations,
            "uncertainty_notes": uncertainty,
            "last_updated_round": 1,
        }
    }


# ========== LLM 增强版 ==========

_REPORT_SYSTEM_PROMPT = """你是罕见病诊断辅助报告撰写专家。基于推理结果生成面向执业医师的连贯报告。

输出 JSON 对象，含：
- impression: 临床印象（1-2句，概括表型特征与诊断方向）
- differential_analysis: 鉴别诊断分析（对Top-3候选逐段分析：匹配点/矛盾点/建议检查）
- pathway_interpretation: 检查路径解读（为何推荐这些检查）
- uncertainty: 不确定性说明（1句）
- disclaimer: 固定文字"本系统输出仅供临床参考，不构成诊断意见。最终诊断由接诊医师结合完整临床信息做出。"

规则：基于提供数据，不编造；禁止确诊语气；输出纯JSON。
"""


async def run_with_llm(
    state: dict | Any,
    llm_gateway: LLMGateway,
) -> dict:
    """LLM 增强版：先调 run() 拿结构化数据，再用 LLM 生成连贯自然语言报告。

    LLM 失败时降级到纯规则版 run()。
    """
    result = run(state)
    report = result["report"]

    try:
        llm_impression = await _generate_impression_with_llm(state, llm_gateway)
        report["summary_text"] = {"impression": llm_impression}
        report["llm_generated"] = True
    except Exception as _e:
        # LLM 失败：保留纯规则报告
        report["summary_text"] = report.get("main_text", "")
        report["llm_generated"] = False

    result["report"] = report
    return result


async def _generate_impression_with_llm(
    state: dict | Any,
    llm_gateway: LLMGateway,
) -> str:
    """用 LLM 生成结构化鉴别诊断报告，列出 Top-3 疾病及分析。"""
    if hasattr(state, "phenotype_profile"):
        profile = state.phenotype_profile
        hypotheses = state.hypotheses
    else:
        profile = state.get("phenotype_profile")
        hypotheses = state.get("hypotheses", [])
    gc = state.get("genetic_constraint") if not hasattr(state, "genetic_constraint") else state.genetic_constraint
    pw = state.get("diagnostic_pathway") if not hasattr(state, "diagnostic_pathway") else state.diagnostic_pathway

    # 构建输入
    parts: list[str] = []
    if profile and profile.vectors:
        pheno = "、".join(f"{v.term_name}({v.hpo_id})" for v in profile.vectors[:8])
        demo = profile.demographic or {}
        age = f"{demo.get('age','')}{demo.get('age_unit','')}" if demo.get("age") is not None else ""
        sex = demo.get("sex", "")
        parts.append(f"患者: {sex} {age}".strip())
        parts.append(f"表型: {pheno}")
    if hypotheses:
        for i, h in enumerate(hypotheses[:3]):
            rc = h.reasoning_chain or ""
            llm_text = rc.split("LLM鉴别:")[-1].strip() if "LLM鉴别:" in rc else ""
            parts.append(f"假设{i+1}: {h.disease_name}({h.disease_id}) 后验={h.bayesian_score:.4f} 置信度={h.confidence:.2f} 分析={llm_text}")
    if gc and hasattr(gc, 'inheritance_patterns') and gc.inheritance_patterns:
        modes = ", ".join(p.mode.value for p in gc.inheritance_patterns[:2])
        if modes:
            parts.append(f"遗传模式: {modes}")
    if pw and hasattr(pw, 'steps') and pw.steps:
        tests = ", ".join(s.test_name for s in pw.steps[:3])
        parts.append(f"推荐检查: {tests}")

    input_text = "\n".join(parts) if parts else "推理结果为空"

    messages = [
        {"role": "system", "content": (
            "你是罕见病诊断辅助报告撰写专家。请基于以下患者信息输出结构化鉴别诊断报告。\n\n"
            "输出格式: 纯文本，分三段。\n"
            "第一段「临床印象」: 概括表型特征与诊断方向（1-2句）。\n"
            "第二段「鉴别诊断」: 以编号列表逐条列出Top-3疾病，每项包括：\n"
            "  - 疾病名称\n"
            "  - 支持度（高/中/低）\n"
            "  - 支持证据：匹配的表型\n"
            "  - 不支持证据：不匹配的表型\n"
            "  - 建议检查\n"
            "第三段「诊疗建议」: 总结下一步推荐的检查或转诊方向（1-2句）。\n"
            "禁止确诊语气，使用'需警惕''建议排查'等措辞。"
        )},
        {"role": "user", "content": f"## 患者信息\n{input_text}\n\n请生成结构化鉴别诊断报告。"},
    ]

    result = await llm_gateway.chat("report_synthesizer", messages, temperature=0.2)
    return result.strip() if isinstance(result, str) else ""


async def _generate_report_with_llm(
    state: dict | Any,
    llm_gateway: LLMGateway,
) -> dict[str, str]:
    """用 LLM 生成连贯诊断报告。

    Returns:
        含 impression/differential_analysis/pathway_interpretation/
        uncertainty/disclaimer 五字段的 dict

    Raises:
        RuntimeError: LLM 调用失败
        ValueError: 输出无法解析
    """
    # 提取五层推理结果
    if hasattr(state, "phenotype_profile"):
        profile = state.phenotype_profile
        hypotheses = state.hypotheses
        temporal_matches = state.temporal_matches
        genetic_constraint = state.genetic_constraint
        pathway = state.diagnostic_pathway
    else:
        profile = state.get("phenotype_profile")
        hypotheses = state.get("hypotheses", [])
        temporal_matches = state.get("temporal_matches", [])
        genetic_constraint = state.get("genetic_constraint")
        pathway = state.get("diagnostic_pathway")

    # 构造结构化输入文本
    parts: list[str] = []

    # 表型
    if profile and profile.vectors:
        pheno = "、".join(f"{v.term_name}({v.presence})" for v in profile.vectors[:6])
        age = ""
        demo = profile.demographic or {}
        if demo.get("age") is not None:
            age = f"{demo['age']}{demo.get('age_unit','岁')}"
        sex = demo.get("sex", "")
        parts.append(f"【患者】{sex} {age}\n【表型】{pheno}")

    # 假设 Top-3（核心信息，含 LLM 鉴别意见）
    if hypotheses:
        hypo_lines = []
        for h in hypotheses[:3]:
            supp = "、".join(h.supporting_phenotypes[:3]) or "无"
            contra = "、".join(h.contradicting_phenotypes[:3]) or "无"
            rc = h.reasoning_chain or ""
            llm_diff = rc.split("LLM鉴别:")[-1].strip() if "LLM鉴别:" in rc else ""
            line = f"#{h.rank} {h.disease_name}({h.disease_id}) 后验={h.bayesian_score:.2f} 支持=[{supp}] 矛盾=[{contra}]"
            if llm_diff:
                line += f" 鉴别={llm_diff}"
            hypo_lines.append(line)
        parts.append("【候选假设】" + " | ".join(hypo_lines))

    # 推荐检查（精简）
    if pathway and pathway.steps:
        steps = "、".join(f"{s.test_name}(EVOI={s.net_evoi:.2f})" for s in pathway.steps[:3])
        parts.append(f"【推荐检查】{steps}")

    input_text = "\n\n".join(parts) if parts else "推理结果为空"

    messages = [
        {"role": "system", "content": _REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 五层推理结果\n{input_text}\n\n请生成诊断辅助报告。"},
    ]

    result = await llm_gateway.chat_json("report_synthesizer", messages, temperature=0.3)

    if not isinstance(result, dict):
        raise ValueError(f"LLM 应返回 JSON 对象，实际: {type(result)}")

    # 清理：只保留字符串值
    cleaned: dict[str, str] = {}
    expected_keys = ("impression", "differential_analysis", "pathway_interpretation",
                     "uncertainty", "disclaimer")
    # 先按精确 key 取
    valid_values: list[str] = []
    for k, v in result.items():
        if isinstance(v, str) and v.strip():
            if k in expected_keys:
                cleaned[k] = v.strip()
            else:
                # 损坏 key（如 ': '、'_key'）的值，留作回填
                valid_values.append(v.strip())
    # 缺失字段用损坏 key 的值按顺序回填
    missing_keys = [k for k in expected_keys if k not in cleaned]
    for k, v in zip(missing_keys, valid_values):
        cleaned[k] = v
    # 兜底默认值
    if not cleaned.get("disclaimer"):
        cleaned["disclaimer"] = "本系统输出仅供临床参考，不构成诊断意见。最终诊断由接诊医师结合完整临床信息做出。"
    if not cleaned.get("uncertainty"):
        cleaned["uncertainty"] = "本报告基于有限的临床信息推理，假设排序仅供参考。"

    return cleaned
