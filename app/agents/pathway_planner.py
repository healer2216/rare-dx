"""Layer 5 · 诊断路径规划 Agent。基于 EVOI 推荐最优下一步检查。

KnowS 策略（PRD §4.2 Layer 5）：
- 源：guide + trial
- 查询：检查项目名 + 疾病名
- 目的：检查方法学证据
"""

from __future__ import annotations

from typing import Any

from ..reasoning.evoi import compute_net_evoi
from ..state.session import DiagnosticPathway, PathwayStep
from ..tools.knows_client import KnowsClient, LAYER_SOURCES
from ..tools.llm_gateway import LLMGateway


# 检查项目库（围绕 D1/D2/D3 演示剧本）
TEST_CATALOG: list[dict[str, Any]] = [
    {
        "test_id": "T001",
        "test_name": "线粒体基因组全长测序",
        "category": "genetic",
        "sensitivity": 0.85, "specificity": 0.95,
        "risk_level": "low", "cost_tier": 3, "turnaround_days": 14,
        "target_diseases": ["ORPHA:520", "ORPHA:254881"],
    },
    {
        "test_id": "T002",
        "test_name": "血乳酸/丙酮酸比值",
        "category": "biochemical",
        "sensitivity": 0.75, "specificity": 0.70,
        "risk_level": "low", "cost_tier": 1, "turnaround_days": 1,
        "target_diseases": ["ORPHA:520", "ORPHA:289", "ORPHA:254881"],
    },
    {
        "test_id": "T003",
        "test_name": "PDHA1 基因测序",
        "category": "genetic",
        "sensitivity": 0.90, "specificity": 0.98,
        "risk_level": "low", "cost_tier": 2, "turnaround_days": 10,
        "target_diseases": ["ORPHA:289"],
    },
    {
        "test_id": "T004",
        "test_name": "SLC12A3 基因测序",
        "category": "genetic",
        "sensitivity": 0.95, "specificity": 0.99,
        "risk_level": "low", "cost_tier": 2, "turnaround_days": 10,
        "target_diseases": ["ORPHA:2136"],
    },
    {
        "test_id": "T005",
        "test_name": "ABCD1 基因测序",
        "category": "genetic",
        "sensitivity": 0.99, "specificity": 0.99,
        "risk_level": "low", "cost_tier": 2, "turnaround_days": 10,
        "target_diseases": ["ORPHA:64", "ORPHA:101"],
    },
    {
        "test_id": "T006",
        "test_name": "血浆极长链脂肪酸 (VLCFA)",
        "category": "biochemical",
        "sensitivity": 0.98, "specificity": 0.95,
        "risk_level": "low", "cost_tier": 1, "turnaround_days": 3,
        "target_diseases": ["ORPHA:64", "ORPHA:101"],
    },
    {
        "test_id": "T007",
        "test_name": "头颅MRI + 磁共振波谱",
        "category": "imaging",
        "sensitivity": 0.90, "specificity": 0.80,
        "risk_level": "low", "cost_tier": 2, "turnaround_days": 2,
        "target_diseases": ["ORPHA:520", "ORPHA:64", "ORPHA:101"],
    },
    {
        "test_id": "T008",
        "test_name": "肌肉活检 + 呼吸链酶活性",
        "category": "histopathological",
        "sensitivity": 0.80, "specificity": 0.85,
        "risk_level": "medium", "cost_tier": 4, "turnaround_days": 21,
        "target_diseases": ["ORPHA:520", "ORPHA:254881"],
    },
    {
        "test_id": "T009",
        "test_name": "血镁 + 24h 尿钾",
        "category": "biochemical",
        "sensitivity": 0.95, "specificity": 0.90,
        "risk_level": "low", "cost_tier": 1, "turnaround_days": 1,
        "target_diseases": ["ORPHA:2136", "ORPHA:112"],
    },
    {
        "test_id": "T010",
        "test_name": "全外显子测序 (WES)",
        "category": "genetic",
        "sensitivity": 0.85, "specificity": 0.95,
        "risk_level": "low", "cost_tier": 5, "turnaround_days": 28,
        "target_diseases": ["*"],  # 通用
    },
]


def run(state: dict | Any) -> dict:
    """Layer 5 入口：基于 EVOI 推荐检查路径。"""
    if hasattr(state, "hypotheses"):
        hypotheses = state.hypotheses
    else:
        hypotheses = state.get("hypotheses", []) if isinstance(state, dict) else []

    if not hypotheses:
        return {"diagnostic_pathway": None, "current_backflow_to_phenotype": False}

    # 收集 Top-5 假设疾病 ID
    top_disease_ids = {h.disease_id for h in hypotheses[:5]}

    # 筛选相关检查项目
    candidate_tests: list[dict] = []
    for t in TEST_CATALOG:
        targets = t.get("target_diseases", [])
        if "*" in targets or (set(targets) & top_disease_ids):
            candidate_tests.append(t)

    # 兜底：LLM 假设全不在 TEST_CATALOG → 至少保留通用检查（WES/影像）
    if not candidate_tests:
        candidate_tests = [t for t in TEST_CATALOG if "*" in t.get("target_diseases", [])]

    # 计算 EVOI 并排序
    scored: list[tuple[dict, dict]] = []
    n_hypotheses = min(len(hypotheses), 5)
    for test in candidate_tests:
        evoi = compute_net_evoi(
            test_sensitivity=test["sensitivity"],
            test_specificity=test["specificity"],
            n_hypotheses=n_hypotheses,
            risk_level=test["risk_level"],
            cost_tier=test["cost_tier"],
        )
        scored.append((test, evoi))

    scored.sort(key=lambda x: x[1]["net_evoi"], reverse=True)

    # 构造 PathwayStep 列表
    steps: list[PathwayStep] = []
    for rank, (test, evoi) in enumerate(scored[:5], start=1):
        # 找该检查能区分的 Top-3 假设
        target_diseases = test.get("target_diseases", [])
        relevant_hypos = [
            h for h in hypotheses[:3]
            if "*" in target_diseases or h.disease_id in target_diseases
        ]
        expected = [
            f"阳性: 支持 {h.disease_name} (rank {h.rank})"
            for h in relevant_hypos
        ] or [f"辅助鉴别 Top-{n_hypotheses} 假设"]

        alternatives = [t["test_id"] for t, _ in scored[:5] if t["test_id"] != test["test_id"]][:2]

        steps.append(PathwayStep(
            test_id=test["test_id"],
            test_name=test["test_name"],
            information_gain=evoi["information_gain"],
            net_evoi=evoi["net_evoi"],
            rank=rank,
            rationale=(
                f"EVOI={evoi['net_evoi']:.3f}, "
                f"信息增益={evoi['information_gain']:.3f}, "
                f"风险={test['risk_level']}, 成本等级={test['cost_tier']}"
            ),
            expected_outcomes=expected,
            alternative_tests=alternatives,
        ))

    pathway = DiagnosticPathway(
        steps=steps,
        current_step=0,
        total_expected_information_gain=sum(s.net_evoi for s in steps),
    )

    # 回流：演示剧本第1轮通常不触发（无新表型）
    return {
        "diagnostic_pathway": pathway,
        "current_backflow_to_phenotype": False,
    }


async def run_with_knows(
    state: dict | Any,
    knows_client: KnowsClient,
    llm_gateway: LLMGateway | None = None,
) -> dict:
    """Layer 5 异步版：EVOI 推荐 + KnowS 检索检查方法学证据。

    若传入 llm_gateway，对 Top-3 推荐检查生成 LLM 自然语言推荐理由（写入 rationale）。
    """
    result = run(state)
    pathway: DiagnosticPathway | None = result.get("diagnostic_pathway")

    if not pathway or not pathway.steps:
        return result

    all_evidence_ids: list[str] = []
    all_evidences: list = []

    # 对 Top-3 推荐检查检索证据
    for step in pathway.steps[:3]:
        query = f"{step.test_name} diagnostic sensitivity specificity"
        try:
            evidences = await knows_client.search(
                sources=LAYER_SOURCES["layer5"],
                query=query,
                retrieved_layer="layer5",
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

    # ===== LLM 推荐理由增强 =====
    if llm_gateway is not None and pathway and pathway.steps:
        try:
            rationales = await _explain_pathway_with_llm(
                pathway.steps[:3], hypotheses[:3] if hypotheses else [], llm_gateway
            )
            for step in pathway.steps[:3]:
                if step.test_id in rationales:
                    step.rationale += f" | LLM理由: {rationales[step.test_id]}"
            result["llm_explained"] = True
        except Exception:
            result["llm_explained"] = False

    return result


# ========== LLM 推荐理由生成 ==========

_PATHWAY_SYSTEM_PROMPT = """你是罕见病诊断检查路径规划专家。基于推荐检查清单与候选疾病，为每项检查生成简明推荐理由（1-2句）。

含：该检查能解决什么鉴别问题、为何优先级高、阳性/阴性结果指向哪个诊断。
面向执业医师，禁止确诊语气，基于提供数据不编造。
输出格式：每项检查一行，"检查ID: 理由说明"，不要JSON，不要额外解释。"""


async def _explain_pathway_with_llm(
    steps: list,
    hypotheses: list,
    llm_gateway: LLMGateway,
) -> dict[str, str]:
    """用 LLM 为 Top-3 推荐检查生成推荐理由（单次文本输出，flash 最稳）。

    Returns: {test_id: 理由说明}
    """
    # 构造输入
    parts: list[str] = []
    for s in steps:
        parts.append(
            f"#{s.rank} {s.test_id}({s.test_name}) EVOI={s.net_evoi:.2f} "
            f"预期={s.expected_outcomes[:2]}"
        )
    for h in hypotheses[:3]:
        parts.append(f"候选: {h.disease_name}({h.disease_id}) 后验={h.bayesian_score:.2f}")

    input_text = "\n".join(parts) if parts else "推荐检查为空"
    messages = [
        {"role": "system", "content": _PATHWAY_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 推荐检查与候选假设\n{input_text}\n\n请为每项检查生成推荐理由。"},
    ]
    # 单次文本输出（非 json_mode），按行解析
    result = await llm_gateway.chat("pathway_planner", messages, temperature=0.2)
    if not isinstance(result, str):
        return {}

    # 解析 "检查ID: 理由" 格式
    rationales: dict[str, str] = {}
    for line in result.strip().splitlines():
        line = line.strip()
        if ":" in line:
            tid, reason = line.split(":", 1)
            tid = tid.strip().strip("*#")
            if tid and reason.strip():
                rationales[tid] = reason.strip()
    return rationales
