"""Layer 2 · 贝叶斯假设生成 Agent。

调用 bayesian.py 计算后验概率，生成排序的疾病假设列表。
KnowS 集成（PRD §4.2 Layer 2）：检索 Top-5 假设的支持/反对证据。

KnowS 策略：
- 源：paper_en + paper_cn
- 查询：疾病名 + 表型组合
- 目的：为每个 Top 假设检索文献支持
"""

from __future__ import annotations

from typing import Any

from ..reasoning.bayesian import rank_hypotheses
from ..state.session import DiseaseHypothesis, EvidencePool, PhenotypeProfile
from ..tools.grade_evidence import compute_evidence_strength
from ..tools.knows_client import EvidenceSource, KnowsClient, LAYER_SOURCES
from ..tools.llm_gateway import LLMGateway


def run(state: dict | Any) -> dict:
    """Layer 2 入口：基于表型谱计算 Top-K 疾病假设。

    同步版本：只做贝叶斯排序，不调 KnowS。
    """
    if hasattr(state, "phenotype_profile"):
        profile = state.phenotype_profile
    else:
        profile = state.get("phenotype_profile") if isinstance(state, dict) else None

    if not profile or not profile.vectors:
        return {"hypotheses": []}

    demographic = {}
    if hasattr(state, "patient_profile"):
        pp = state.patient_profile
        demographic = {
            "age": getattr(pp, "age", None),
            "age_unit": "years",
            "sex": getattr(pp, "sex", None),
        }
    elif isinstance(state, dict):
        pp = state.get("patient_profile")
        if pp and isinstance(pp, dict):
            demographic = {
                "age": pp.get("age"),
                "age_unit": pp.get("age_unit", "years"),
                "sex": pp.get("sex"),
            }

    hypotheses = rank_hypotheses(
        phenotype_profile=profile,
        demographic=demographic,
        top_k=10,
        min_posterior=1e-8,
    )

    return {"hypotheses": hypotheses}


async def run_with_knows(
    state: dict | Any,
    knows_client: KnowsClient,
    llm_gateway: LLMGateway | None = None,
) -> dict:
    """Layer 2 异步版本：贝叶斯排序 + KnowS 检索 Top-5 假设证据。

    为每个 Top-5 假设检索 paper_en + paper_cn，附加证据 ID 和强度。
    若传入 llm_gateway，对 Top-3 生成 LLM 鉴别诊断解释（写入 reasoning_chain）。

    兜底策略：
    - 贝叶斯无命中（表型不在频率表）时，启用 LLM 直接生成候选疾病假设
    """
    result = run(state)
    hypotheses: list[DiseaseHypothesis] = result.get("hypotheses", [])

    # ===== 兜底：贝叶斯无命中 / 命中假设但置信度过低时，LLM 直接生成候选疾病 =====
    # 贝叶斯「有用」需同时满足：有假设 + Top-1 置信度高于安全阈值（0.3）
    # 否则 LLM 兜底，避免被 conservative_downgrade 清空
    bayesian_useful = bool(hypotheses) and hypotheses[0].confidence >= 0.3
    if not bayesian_useful and llm_gateway is not None:
        try:
            llm_hypotheses = await _generate_hypotheses_with_llm(state, llm_gateway)
            hypotheses = llm_hypotheses
            result["hypotheses"] = hypotheses
            result["llm_fallback_hypotheses"] = True
        except Exception as e:
            # LLM 兜底也失败 → 维持原结果
            import logging
            logging.getLogger(__name__).warning(f"LLM 假设生成兜底失败: {e}")

    if not hypotheses:
        return result

    # 仅对 Top-5 检索（性能考虑）
    top5 = hypotheses[:5]
    all_evidence_ids: list[str] = []
    all_evidences: list = []

    # 表型关键词
    profile = state.phenotype_profile if hasattr(state, "phenotype_profile") else state.get("phenotype_profile")
    pheno_terms = [v.term_name for v in profile.vectors[:3]] if profile else []

    for hypo in top5:
        query = f"{hypo.disease_name} {' '.join(pheno_terms)} 诊断"
        try:
            evidences = await knows_client.search(
                sources=LAYER_SOURCES["layer2"],
                query=query,
                retrieved_layer="layer2",
                top_k=3,
            )
            if evidences:
                # 每个假设只保留前 3 条，避免 30 条混在一起
                hypo.evidence_ids = [ev.id for ev in evidences[:3]]
                all_evidence_ids.extend(hypo.evidence_ids)
                # 仅取前 3 条加入全局证据池
                all_evidences.extend(evidences[:3])

                # 计算证据强度
                letter, score = compute_evidence_strength(evidences)
                hypo.reasoning_chain += f" | 证据强度={letter}({score:.2f})"
        except Exception:
            # KnowS 失败：保留纯贝叶斯结果
            pass

    if all_evidence_ids:
        result["current_layer_evidence_ids"] = all_evidence_ids
        result["current_layer_evidences"] = all_evidences

    # ===== LLM 鉴别诊断解释（Top-3）=====
    if llm_gateway is not None and hypotheses:
        try:
            explanations = await _generate_differential_with_llm(
                hypotheses[:3], profile, llm_gateway
            )
            for hypo in hypotheses[:3]:
                if hypo.disease_id in explanations:
                    hypo.reasoning_chain += f" | LLM鉴别: {explanations[hypo.disease_id]}"
            result["llm_differential"] = True
        except Exception:
            # LLM 失败不阻断推理
            result["llm_differential"] = False

    # ===== 日志：假设生成统计 =====
    import logging
    _logger = logging.getLogger(__name__)
    _logger.info("hypothesis_layer2_generation", extra={
        "session_id": getattr(state, "session_id", "") if hasattr(state, "session_id") else state.get("session_id", ""),
        "bayesian_hit": bayesian_useful,
        "llm_fallback": not bayesian_useful,
        "hypothesis_count": len(hypotheses),
        "top1_disease": hypotheses[0].disease_name if hypotheses else None,
    })

    return result


# ========== LLM 假设生成兜底 ==========

_HYPOTHESIS_GEN_PROMPT = """你是罕见病诊断专家。基于患者表型向量，直接生成 Top-5 候选疾病假设。

## 输出要求
输出 JSON 对象：{"hypotheses": [{"disease_id": "...", "disease_name": "...", "supporting_phenotypes": [...], "reasoning": "..."}]}
- disease_id: 用 ORPHA:xxx 或 OMIM:xxxxxx 格式；不确定时用 ORPHA:UNKNOWN
- disease_name: 中文疾病名
- supporting_phenotypes: 支持该诊断的表型术语名列表
- reasoning: 1-2句说明为何该病与表型匹配

## 规则
1. 必须返回 3-5 个候选疾病，按可能性降序
2. 优先选择能解释多个表型的系统性疾病
3. 不要确诊语气，保留不确定性
4. 输出纯 JSON，不要解释文字

## 示例
输入: 表型=[头痛, 鼻窦炎, 鼻出血, 咯血, 咳痰增多, 体重减轻]
输出: {"hypotheses": [
  {"disease_id": "ORPHA:439", "disease_name": "肉芽肿性多血管炎", "supporting_phenotypes": ["鼻窦炎","鼻出血","咯血"], "reasoning": "上下呼吸道受累+头痛+消瘦高度契合GPA"},
  {"disease_id": "ORPHA:502", "disease_name": "鼻硬结病", "supporting_phenotypes": ["鼻窦炎","鼻充血","鼻出血"], "reasoning": "慢性鼻部肉芽肿性病变"}
]}
"""


async def _generate_hypotheses_with_llm(
    state: dict | Any,
    llm_gateway: LLMGateway,
) -> list[DiseaseHypothesis]:
    """LLM 直接基于表型生成候选疾病假设（贝叶斯无命中时兜底）。

    Raises:
        RuntimeError: LLM 调用失败
        ValueError: 输出无法解析
    """
    profile = (
        state.phenotype_profile
        if hasattr(state, "phenotype_profile")
        else state.get("phenotype_profile")
    )
    if not profile or not profile.vectors:
        return []

    # 表型摘要喂给 LLM
    pheno_summary = "、".join(
        f"{v.term_name}({v.hpo_id})" for v in profile.vectors[:8]
    ) or "未提供表型"

    messages = [
        {"role": "system", "content": _HYPOTHESIS_GEN_PROMPT},
        {"role": "user", "content": f"## 患者表型\n{pheno_summary}\n\n请生成 Top-5 候选疾病假设。"},
    ]

    result = await llm_gateway.chat_json("hypothesis_generator", messages, temperature=0.2)

    # 兼容多种返回形态
    items: list[dict] = []
    if isinstance(result, dict):
        for key in ("hypotheses", "data", "result", "items"):
            val = result.get(key)
            if isinstance(val, list):
                items = val
                break
        else:
            if any(k in result for k in ("disease_id", "disease_name", "supporting_phenotypes")):
                items = [result]
    elif isinstance(result, list):
        items = result

    hypotheses: list[DiseaseHypothesis] = []
    for rank, item in enumerate(items[:5], start=1):
        if not isinstance(item, dict):
            continue
        did = item.get("disease_id", "") or "ORPHA:UNKNOWN"
        dname = item.get("disease_name", "") or did
        supp = item.get("supporting_phenotypes", []) or []
        reasoning = item.get("reasoning", "") or ""

        hypotheses.append(DiseaseHypothesis(
            disease_id=did,
            disease_name=dname,
            bayesian_score=0.0,  # LLM 兜底无贝叶斯分
            supporting_phenotypes=supp,
            contradicting_phenotypes=[],
            rank=rank,
            evidence_ids=[],
            confidence=0.5 - rank * 0.08,  # 衰减置信度
            reasoning_chain=f"LLM兜底生成 | {reasoning}",
        ))

    return hypotheses


# ========== LLM 鉴别诊断生成 ==========

_DIFF_SYSTEM_PROMPT = """你是罕见病鉴别诊断专家。基于患者表型和候选疾病列表，为每个候选疾病生成简洁的鉴别诊断理由。

## 输出要求
输出 JSON 对象，key 是疾病 ID，value 是该疾病的鉴别诊断说明（2-3句，含：为何匹配/为何可能不是/建议进一步检查什么）。
输出格式：{"disease_id_1": "鉴别诊断说明...", "disease_id_2": "..."}

## 规则
1. 仅基于提供的表型信息分析，不要编造未提供的临床数据
2. 说明要具体、可操作，避免空话（如"建议进一步检查"要指明查什么）
3. 客观陈述匹配与矛盾点，不要确诊语气
4. 输出纯 JSON 对象，不要解释文字

## 示例
输入: 候选=[Leigh综合征(支持:肌张力低下/乳酸酸中毒, 矛盾:无), Gitelman(支持:无, 矛盾:乳酸酸中毒)]
输出: {"ORPHA:520": "患者肌张力低下+乳酸酸中毒高度契合Leigh线粒体脑肌病发病模式。建议查基底节MRI异常信号与乳酸峰值。需排除其他线粒体病。", "ORPHA:380": "Gitelman以低钾低镁代谢性碱中毒为特征，与本例乳酸酸中毒矛盾，可能性低。"}
"""


async def _generate_differential_with_llm(
    hypotheses: list[DiseaseHypothesis],
    profile: PhenotypeProfile | None,
    llm_gateway: LLMGateway,
) -> dict[str, str]:
    """用 LLM 为候选疾病生成鉴别诊断解释。

    Returns:
        {disease_id: 鉴别诊断说明} 字典

    Raises:
        RuntimeError: LLM 调用失败
        ValueError: 输出无法解析
    """
    # 构造患者表型摘要
    pheno_summary = "、".join(
        f"{v.term_name}({v.presence})" for v in (profile.vectors if profile else [])[:6]
    ) or "未提供表型"

    # 构造候选疾病清单
    candidates = []
    for h in hypotheses:
        supp = "、".join(h.supporting_phenotypes[:3]) or "无"
        contra = "、".join(h.contradicting_phenotypes[:3]) or "无"
        candidates.append(
            f"- {h.disease_name} (id={h.disease_id}, 后验={h.bayesian_score:.4f}, "
            f"支持表型: {supp}, 矛盾表型: {contra})"
        )
    candidates_text = "\n".join(candidates)

    messages = [
        {"role": "system", "content": _DIFF_SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"## 患者表型\n{pheno_summary}\n\n"
            f"## 候选疾病\n{candidates_text}\n\n"
            f"请为每个疾病生成鉴别诊断说明。"
        )},
    ]

    result = await llm_gateway.chat_json("hypothesis_generator", messages, temperature=0.2)

    if not isinstance(result, dict):
        raise ValueError(f"LLM 应返回 JSON 对象，实际: {type(result)}")

    # 清理：只保留字符串值
    raw: dict[str, str] = {}
    for k, v in result.items():
        if isinstance(v, str) and v.strip():
            raw[k] = v.strip()

    # 容错匹配：flash 小模型可能损坏 key（如 'ORPHA:520' → ': '）
    # 策略：先按精确 key 匹配；未匹配的值按顺序回填到未匹配的候选 disease_id
    candidate_ids = [h.disease_id for h in hypotheses]
    cleaned: dict[str, str] = {}
    unmatched_values: list[str] = []

    for k, v in raw.items():
        if k in candidate_ids:
            cleaned[k] = v
        else:
            unmatched_values.append(v)

    # 回填：未匹配的值按顺序分给未匹配的候选 ID
    unmatched_ids = [did for did in candidate_ids if did not in cleaned]
    for did, v in zip(unmatched_ids, unmatched_values):
        cleaned[did] = v

    return cleaned
