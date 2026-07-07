"""Agent 层单元测试 — 6 个 Agent 的同步 run() 接口。"""

import pytest

from app.agents.phenotype_analyzer import extract_phenotypes, extract_demographic, run as l1_run
from app.agents.hypothesis_generator import run as l2_run
from app.agents.temporal_reasoner import run as l3_run
from app.agents.genetic_reasoner import run as l4_run
from app.agents.pathway_planner import run as l5_run
from app.agents.report_synthesizer import run as l6_run


# ===== Layer 1: 表型分析 =====

def test_phenotype_extract_basic():
    """词典提取 HPO 表型（含修饰符/阴性）。"""
    text = "男婴3月龄进行性肌张力低下喂养困难乳酸性酸中毒眼球震颤"
    vectors = extract_phenotypes(text)
    assert len(vectors) > 0, "应提取到表型"
    hpo_ids = [v.hpo_id for v in vectors]
    # 至少含肌张力低下或乳酸酸中毒
    assert any("HP:" in h for h in hpo_ids)


def test_phenotype_extract_empty_input():
    """空输入 → 空列表。"""
    assert extract_phenotypes("") == []
    assert extract_phenotypes("今天天气真好") == []


def test_phenotype_demographic():
    """提取人口学信息（年龄/性别）。"""
    demo = extract_demographic("男婴3月龄")
    assert isinstance(demo, dict)
    # 应包含性别或年龄信息
    assert demo.get("sex") or demo.get("age") is not None


def test_phenotype_run_returns_profile():
    """run() 返回 phenotype_profile 字段。"""
    state = {"current_user_message": "男婴3月龄肌张力低下乳酸酸中毒", "session_id": "t"}
    result = l1_run(state)
    assert "phenotype_profile" in result
    assert result["phenotype_profile"].vectors  # 非空


# ===== Layer 2: 假设生成 =====

def test_hypothesis_generate_returns_sorted():
    """基于表型 → 返回排序假设。"""
    state = {
        "current_user_message": "男婴3月龄肌张力低下乳酸酸中毒眼球震颤",
        "session_id": "t",
    }
    state = l1_run(state)
    result = l2_run(state)
    assert "hypotheses" in result
    assert len(result["hypotheses"]) > 0
    # 排序验证
    scores = [h.bayesian_score for h in result["hypotheses"]]
    assert scores == sorted(scores, reverse=True)


# ===== Layer 3: 时序推理 =====

def test_temporal_run_returns_matches():
    """假设+表型 → 各疾病时序分数。"""
    state = {
        "current_user_message": "男婴3月龄肌张力低下乳酸酸中毒",
        "session_id": "t",
    }
    state = l1_run(state)
    state.update(l2_run(state))
    result = l3_run(state)
    assert "temporal_matches" in result
    assert len(result["temporal_matches"]) > 0


# ===== Layer 4: 遗传推理 =====

def test_genetic_run_returns_constraint():
    """假设 → 推断遗传模式 + 兼容/不兼容列表。"""
    state = {
        "current_user_message": "男婴3月龄肌张力低下乳酸酸中毒",
        "session_id": "t",
    }
    state = l1_run(state)
    state.update(l2_run(state))
    state.update(l3_run(state))
    result = l4_run(state)
    assert "genetic_constraint" in result
    gc = result["genetic_constraint"]
    assert gc.inheritance_patterns  # 非空


# ===== Layer 5: 路径规划 =====

def test_pathway_evoi_sorting():
    """EVOI 降序排列。"""
    state = {
        "current_user_message": "男婴3月龄肌张力低下乳酸酸中毒",
        "session_id": "t",
    }
    state = l1_run(state)
    state.update(l2_run(state))
    state.update(l3_run(state))
    state.update(l4_run(state))
    result = l5_run(state)
    assert "diagnostic_pathway" in result
    pw = result["diagnostic_pathway"]
    if pw.steps:
        evois = [s.net_evoi for s in pw.steps]
        assert evois == sorted(evois, reverse=True), "应按 EVOI 降序"


# ===== Layer 6: 报告合成 =====

def test_report_contains_disclaimer():
    """报告含免责声明。"""
    state = {
        "current_user_message": "男婴3月龄肌张力低下乳酸酸中毒",
        "session_id": "t",
    }
    state = l1_run(state)
    state.update(l2_run(state))
    state.update(l3_run(state))
    state.update(l4_run(state))
    state.update(l5_run(state))
    result = l6_run(state)
    report = result["report"]
    # main_text 或 uncertainty_notes 中应含免责声明关键词
    content = report.get("main_text", "") + report.get("uncertainty_notes", "")
    assert "仅供" in content or "临床" in content or "参考" in content, "应含免责声明"


def test_report_empty_state_not_crash():
    """空 state → 报告不崩溃。"""
    result = l6_run({"session_id": "empty"})
    assert "report" in result
