import pytest

from app.services.billing.agent_pricing import (
    MAX_AGENTS,
    estimate_simulation_cost,
)


def test_estimate_basic():
    est = estimate_simulation_cost(1000, 5)
    assert est.agent_count == 1000
    assert est.rounds == 5
    assert est.agent_rounds == 5000
    assert est.actual_cost_usd > 0
    assert est.retail_cost_usd > est.actual_cost_usd
    assert est.margin_pct == 75.0


def test_estimate_markup_is_4x():
    est = estimate_simulation_cost(10000, 5)
    ratio = est.retail_cost_usd / est.actual_cost_usd
    assert abs(ratio - 4.0) < 0.01


def test_estimate_scales_linearly():
    est1 = estimate_simulation_cost(1000, 5)
    est2 = estimate_simulation_cost(2000, 5)
    ratio = est2.retail_cost_usd / est1.retail_cost_usd
    assert abs(ratio - 2.0) < 0.01


def test_estimate_max_agents():
    est = estimate_simulation_cost(MAX_AGENTS, 1)
    assert est.agent_count == MAX_AGENTS


def test_estimate_exceeds_max_raises():
    with pytest.raises(ValueError, match="cannot exceed"):
        estimate_simulation_cost(MAX_AGENTS + 1, 1)


def test_estimate_zero_raises():
    with pytest.raises(ValueError):
        estimate_simulation_cost(0, 5)


def test_estimate_negative_raises():
    with pytest.raises(ValueError):
        estimate_simulation_cost(-100, 5)
