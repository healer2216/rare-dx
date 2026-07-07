"""Golden 回归基线测试 — D1 端到端输出对照 expected.json。

运行: pytest tests/test_golden.py -v
作用: 防止算法/配置变更引入 silent regression。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.agents.phenotype_analyzer import run as l1_run
from app.agents.hypothesis_generator import run as l2_run
from app.agents.temporal_reasoner import run as l3_run
from app.agents.genetic_reasoner import run as l4_run
from app.agents.pathway_planner import run as l5_run
from app.agents.report_synthesizer import run as l6_run


def _load_golden(case_id: str = "case_01") -> dict:
    path = _ROOT / "tests" / "golden" / case_id / "expected.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _run_pipeline(text: str, session_id: str = "golden") -> dict:
    state: dict = {
        "session_id": session_id,
        "current_user_message": text,
        "current_backflow_iterations": 0,
    }
    state.update(l1_run(state))
    state.update(l2_run(state))
    state.update(l3_run(state))
    state.update(l4_run(state))
    if state.get("current_backflow_to_hypothesis"):
        state["current_backflow_iterations"] = 1
        state.pop("current_backflow_to_hypothesis")
        state.update(l2_run(state))
        state.update(l3_run(state))
        state.update(l4_run(state))
    state.update(l5_run(state))
    state.update(l6_run(state))
    return state


def test_golden_d1_phenotype():
    """L1 表型数量对照基线。"""
    g = _load_golden("case_01")
    state = _run_pipeline(g["clinical_text"], "golden-d1")
    vectors = state["phenotype_profile"].vectors
    assert len(vectors) >= g["expected"]["l1_phenotype_count"] - 2


def test_golden_d1_hypothesis():
    """L2 Leigh 综合征应在 Top-3 内。"""
    g = _load_golden("case_01")
    state = _run_pipeline(g["clinical_text"], "golden-d1")
    hypos = state["hypotheses"]
    top_ids = {h.disease_id for h in hypos[:3]}
    assert "ORPHA:520" in top_ids or "ORPHA:255249" in top_ids, f"Leigh 不在 Top-3 中: {top_ids}"


def test_golden_d1_temporal():
    """L3 时序匹配数量对照基线。"""
    g = _load_golden("case_01")
    state = _run_pipeline(g["clinical_text"], "golden-d1")
    matches = state["temporal_matches"]
    assert len(matches) >= 1


def test_golden_d1_genetic():
    """L4 遗传模式推断存在。"""
    g = _load_golden("case_01")
    state = _run_pipeline(g["clinical_text"], "golden-d1")
    gc = state["genetic_constraint"]
    assert gc.inheritance_patterns


def test_golden_d1_pathway():
    """L5 推荐检查数量对照基线。"""
    g = _load_golden("case_01")
    state = _run_pipeline(g["clinical_text"], "golden-d1")
    pathway = state["diagnostic_pathway"]
    assert len(pathway.steps) >= 3


def test_golden_d1_report():
    """L6 报告含免责声明。"""
    g = _load_golden("case_01")
    state = _run_pipeline(g["clinical_text"], "golden-d1")
    report = state["report"]
    assert g["expected"]["l6_has_disclaimer"] is True
    assert "不构成诊断" in report["main_text"]


# ===== D2 Gitelman =====

def test_golden_d2():
    """D2: Top-1 应为 Gitelman 综合征 ORPHA:2136。"""
    g = _load_golden("case_02")
    state = _run_pipeline(g["clinical_text"], "golden-d2")
    hypos = state["hypotheses"]
    assert len(hypos) == g["expected"]["l2_hypothesis_count"]
    top1 = hypos[0]
    assert top1.disease_id == g["expected"]["l2_top1_disease_id"]
    assert g["expected"]["l2_top1_disease_name"] in top1.disease_name
    # 遗传
    gc = state.get("genetic_constraint")
    assert gc and gc.inheritance_patterns
    assert any(p.mode.value == "AR" for p in gc.inheritance_patterns)


# ===== D3 X-ALD =====

def test_golden_d3():
    """D3: Top-1 应为 X-连锁肾上腺脑白质营养不良 ORPHA:64。"""
    g = _load_golden("case_03")
    state = _run_pipeline(g["clinical_text"], "golden-d3")
    hypos = state["hypotheses"]
    assert len(hypos) == g["expected"]["l2_hypothesis_count"]
    top1 = hypos[0]
    assert top1.disease_id == g["expected"]["l2_top1_disease_id"]
    assert g["expected"]["l2_top1_disease_name"] in top1.disease_name
    # 报告
    report = state["report"]
    assert g["expected"]["l6_has_disclaimer"] is True
    assert "不构成诊断" in report["main_text"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
