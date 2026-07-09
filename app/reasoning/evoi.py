"""EVOI（Expected Value of Information）计算器。"""

from __future__ import annotations


def compute_information_gain(
    test_sensitivity: float,
    test_specificity: float,
    n_hypotheses: int,
) -> float:
    accuracy = (test_sensitivity + test_specificity) / 2
    if n_hypotheses <= 1:
        return 0.0
    max_gain = 1 - 1 / n_hypotheses
    return accuracy * max_gain


def compute_risk_penalty(risk_level: str) -> float:
    return {"low": 0.1, "medium": 0.3, "high": 0.6}.get(risk_level, 0.3)


def compute_cost_penalty(cost_tier: int) -> float:
    return cost_tier / 5.0


def compute_net_evoi(
    hypotheses: list[DiseaseHypothesis],
    test_catalog: list[dict[str, Any]],
    profile: PhenotypeProfile,
) -> DiagnosticPathway:
    print(f"[evoi] compute_net_evoi start hypotheses={len(hypotheses)} tests={len(test_catalog)}", flush=True)
    test_sensitivity: float,
    test_specificity: float,
    n_hypotheses: int,
    risk_level: str,
    cost_tier: int,
    weights: tuple[float, float, float] = (0.6, 0.2, 0.2),
) -> dict:
    ig = compute_information_gain(test_sensitivity, test_specificity, n_hypotheses)
    rp = compute_risk_penalty(risk_level)
    cp = compute_cost_penalty(cost_tier)
    net = weights[0] * ig - weights[1] * rp - weights[2] * cp
    return {
        "information_gain": ig,
        "risk_penalty": rp,
        "cost_penalty": cp,
        "net_evoi": max(0.0, net),
    }
