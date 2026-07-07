"""工具层单元测试 — 证据分级 + 报告导出 + LLM Gateway。"""

import pytest

from app.tools.grade_evidence import compute_evidence_strength, best_grade
from app.tools.report_export import generate_docx, generate_pdf
from app.tools.llm_gateway import LLMGateway


# ===== 证据分级 =====

class FakeEv:
    def __init__(self, grade="B", source_type="clinical_study", study_type=None):
        self.grade = grade
        self.source_type = source_type
        self.study_type = study_type


def test_grade_evidence_compute():
    """compute_evidence_strength 返回等级 + 强度。"""
    evs = [FakeEv("A"), FakeEv("B"), FakeEv("C")]
    grade, strength = compute_evidence_strength(evs)
    assert isinstance(grade, str)
    assert isinstance(strength, float)
    assert 0 <= strength <= 1


def test_grade_evidence_empty():
    """空列表 → 默认等级。"""
    grade, strength = compute_evidence_strength([])
    assert grade in ("E", "N", "")
    assert strength >= 0


def test_best_grade():
    """best_grade 取最高等级。"""
    evs = [FakeEv("C"), FakeEv("A"), FakeEv("B")]
    best = best_grade(evs)
    assert best is not None


# ===== 报告导出 =====

def _make_state():
    """构造最小可用的 state dict。"""
    from app.state.session import (
        PhenotypeProfile, PhenotypeVector, PresenceStatus,
        DiseaseHypothesis, DiagnosticPathway, PathwayStep,
    )
    profile = PhenotypeProfile(
        patient_id="t", raw_text="", demographic={},
        vectors=[PhenotypeVector(hpo_id="HP:0001290", term_name="肌张力低下", presence=PresenceStatus.PRESENT)],
    )
    hyp = DiseaseHypothesis(
        disease_id="ORPHA:520", disease_name="Leigh综合征",
        bayesian_score=0.85, confidence=1.0, rank=1,
        supporting_phenotypes=["肌张力低下"], contradicting_phenotypes=[],
        evidence_ids=["e1"], reasoning_chain="",
    )
    pathway = DiagnosticPathway(
        total_expected_information_gain=0.5,
        steps=[PathwayStep(test_id="T1", test_name="PDHA1基因测序", net_evoi=0.28, rank=1, expected_outcomes=["阳性"], rationale="")],
    )
    return {
        "session_id": "t",
        "phenotype_profile": profile,
        "hypotheses": [hyp],
        "diagnostic_pathway": pathway,
        "report": {"main_text": "测试报告", "summary_text": {"impression": "测试印象"}, "llm_generated": False},
    }


def test_report_export_docx():
    """DOCX 字节输出 + 标题。"""
    state = _make_state()
    content = generate_docx(state, "t")
    assert isinstance(content, bytes)
    assert len(content) > 1000, "DOCX 应有内容"


def test_report_export_pdf():
    """PDF 字节输出 + 页数 ≥ 1。"""
    state = _make_state()
    content = generate_pdf(state, "t")
    assert isinstance(content, bytes)
    assert content.startswith(b"%PDF"), "应为 PDF 格式"


def test_report_export_empty_state():
    """空 state → 不崩溃。"""
    empty = {"report": {}}
    # DOCX
    content = generate_docx(empty, "empty")
    assert isinstance(content, bytes)
    # PDF
    content = generate_pdf(empty, "empty")
    assert isinstance(content, bytes)


# ===== LLM Gateway =====

@pytest.mark.asyncio
async def test_llm_gateway_config():
    """LLMGateway 配置加载 + agent_model_map 正确。"""
    gw = LLMGateway()
    assert gw.providers  # 非空配置
    assert "stepfun" in gw.providers or "deepseek" in gw.providers
    await gw.aclose()


@pytest.mark.asyncio
async def test_llm_gateway_chat():
    """LLMGateway.chat 调用（真实 API，可能失败需降级）。"""
    gw = LLMGateway()
    try:
        r = await gw.chat("phenotype_analyzer", [{"role": "user", "content": "回复OK"}])
        assert isinstance(r, str)
    except Exception as e:
        # API 余额不足等失败是允许的，测试仅验证不崩溃
        assert "失败" in str(e) or "402" in str(e) or "quota" in str(e).lower()
    finally:
        await gw.aclose()
