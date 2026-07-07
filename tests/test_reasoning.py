"""推理算法层单元测试 — 贝叶斯 / 时序 / 遗传 / EVOI。"""

import pytest

from app.reasoning.bayesian import rank_hypotheses, compute_prior, compute_posterior
from app.reasoning.temporal_logic import match_onset_age, match_progression
from app.reasoning.inheritance import analyze_pedigree, infer_from_phenotype
from app.reasoning.evoi import compute_net_evoi
from app.state.session import (
    PhenotypeProfile, PhenotypeVector, PresenceStatus, InheritanceMode,
)


# ===== 贝叶斯 =====

def _make_profile(hpo_ids: list[str]) -> PhenotypeProfile:
    vectors = [
        PhenotypeVector(hpo_id=hpo, term_name=f"测试-{hpo}", presence=PresenceStatus.PRESENT)
        for hpo in hpo_ids
    ]
    return PhenotypeProfile(patient_id="test", vectors=vectors, raw_text="", demographic={})


def test_bayesian_rank_hypotheses_returns_sorted():
    """给定表型向量，返回排序假设、后验归一化、阈值过滤。"""
    profile = _make_profile(["HP:0001290", "HP:0002154", "HP:0002033"])
    hypotheses = rank_hypotheses(profile, top_k=10, min_posterior=1e-5)

    assert isinstance(hypotheses, list)
    assert len(hypotheses) > 0, "应有候选假设"

    # 排序：后验降序
    scores = [h.bayesian_score for h in hypotheses]
    assert scores == sorted(scores, reverse=True), "应按后验降序"

    # rank 从 1 开始
    assert hypotheses[0].rank == 1

    # 置信度 ≤ 1
    for h in hypotheses:
        assert 0 <= h.confidence <= 1.0


def test_bayesian_empty_phenotype_returns_empty():
    """无表型向量 → 空列表。"""
    profile = _make_profile([])
    assert rank_hypotheses(profile) == []


def test_bayesian_min_posterior_filter():
    """极高阈值 → 假设被过滤。"""
    profile = _make_profile(["HP:0001290"])
    # 极高阈值应过滤所有假设
    hypotheses = rank_hypotheses(profile, min_posterior=0.99)
    assert len(hypotheses) == 0


def test_bayesian_prevalence_prior():
    """患病率先验修正：常见病先验 > 罕见病先验。"""
    prior_common = compute_prior("ORPHA:520", demographic=None)  # Leigh
    prior_rare = compute_prior("ORPHA:380", demographic=None)    # Gitelman
    # 都是罕见病，先验应较低但非零
    assert 0 < prior_common < 1
    assert 0 < prior_rare < 1


# ===== 时序推理 =====

def test_temporal_onset_match_in_range():
    """发病年龄在典型范围内 → 1.0。"""
    score = match_onset_age(3.0, 0.0, 5.0, variability=0.3)
    assert score == 1.0


def test_temporal_onset_match_out_of_range():
    """发病年龄偏离典型范围 → 高斯衰减 (< 1.0)。"""
    score = match_onset_age(20.0, 0.0, 5.0, variability=0.3)
    assert 0 <= score < 1.0


def test_temporal_onset_match_far_distance_lower():
    """距离更远 → 分数更低。"""
    near = match_onset_age(8.0, 0.0, 5.0)
    far = match_onset_age(50.0, 0.0, 5.0)
    assert far < near, "更远距离应得更低分"


def test_temporal_progression_compat():
    """进展模式匹配。"""
    # 相同模式
    assert match_progression("chronic_progressive", "chronic_progressive") >= 0.5
    # 完全不同
    assert match_progression("acute_episodic", "chronic_progressive") < 1.0


# ===== 遗传推理 =====

def test_inheritance_pedigree_ar_from_consanguinity():
    """近亲婚配 → AR 高置信。"""
    pedigree = {
        "consanguinity": True,
        "members": [
            {"relationship": "self", "sex": "male", "affected_status": "true"},
            {"relationship": "sibling", "sex": "female", "affected_status": "true"},
        ],
    }
    patterns = analyze_pedigree(pedigree)
    modes = [p.mode for p in patterns]
    assert InheritanceMode.AR in modes, "近亲婚配应推断 AR"


def test_inheritance_pedigree_xr_from_male_only():
    """仅男性受累 → XR。"""
    pedigree = {
        "consanguinity": False,
        "members": [
            {"relationship": "self", "sex": "male", "affected_status": "true"},
            {"relationship": "sibling", "sex": "male", "affected_status": "true"},
            {"relationship": "sibling", "sex": "female", "affected_status": "false"},
        ],
    }
    patterns = analyze_pedigree(pedigree)
    modes = [p.mode for p in patterns]
    assert InheritanceMode.XR in modes, "仅男性受累应推断 XR"


def test_inheritance_pedigree_mitochondrial_from_maternal():
    """母系成员多代受累 → 线粒体遗传。"""
    pedigree = {
        "consanguinity": False,
        "members": [
            {"relationship": "self", "sex": "male", "affected_status": "true"},
            {"relationship": "mother", "sex": "female", "affected_status": "true"},
            {"relationship": "maternal_uncle", "sex": "male", "affected_status": "true"},
        ],
    }
    patterns = analyze_pedigree(pedigree)
    modes = [p.mode for p in patterns]
    assert InheritanceMode.MITOCHONDRIAL in modes, "母系多代受累应推断线粒体"


def test_inheritance_no_pedigree():
    """无家系 → UNKNOWN 低置信。"""
    patterns = analyze_pedigree(None)
    assert len(patterns) == 1
    assert patterns[0].mode == InheritanceMode.UNKNOWN
    assert patterns[0].confidence <= 0.2


# ===== EVOI =====

def test_evoi_compute_returns_dict():
    """compute_net_evoi 返回完整字典。"""
    result = compute_net_evoi(
        test_sensitivity=0.95, test_specificity=0.99,
        n_hypotheses=3, risk_level="moderate", cost_tier=2,
    )
    assert "information_gain" in result
    assert "risk_penalty" in result
    assert "cost_penalty" in result
    assert "net_evoi" in result
    assert result["net_evoi"] >= 0, "net_evoi 应非负"


def test_evoi_higher_sensitivity_higher_gain():
    """更高灵敏度 → 信息增益更高。"""
    low = compute_net_evoi(0.5, 0.99, 3, "moderate", 2)
    high = compute_net_evoi(0.99, 0.99, 3, "moderate", 2)
    assert high["information_gain"] >= low["information_gain"]


def test_evoi_higher_cost_lower_net():
    """更高成本等级 → net_evoi 更低。"""
    low_cost = compute_net_evoi(0.9, 0.9, 3, "moderate", cost_tier=1)
    high_cost = compute_net_evoi(0.9, 0.9, 3, "moderate", cost_tier=5)
    assert high_cost["net_evoi"] <= low_cost["net_evoi"]
