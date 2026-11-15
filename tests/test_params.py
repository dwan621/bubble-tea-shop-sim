"""Configuration and analytical-layer checks (Lecture 2 / Lecture 3 numbers)."""

from __future__ import annotations

import pytest

from bubble_tea_sim import OrderMix, SimConfig, scenarios
from bubble_tea_sim.params import Economics, Policy, ServiceTimes


def test_order_mix_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        OrderMix(tea=0.9, bread=0.2, ice=0.05, mix=0.2).validate()


def test_default_mean_service_time_and_capacity() -> None:
    config = SimConfig()
    # p_bar = 0.55*2.5 + 0.20*0.667 + 0.05*0.833 + 0.20*2.833 = 2.1167 min
    assert config.mean_service_time() == pytest.approx(2.1167, abs=5e-4)
    # capacity = 3 / 2.1167 = 1.4172 customers/min
    assert 3 / config.mean_service_time() == pytest.approx(1.417, abs=1e-3)


@pytest.mark.parametrize(
    "lam,expected_util",
    [(1.00, 0.7055), (1.25, 0.8818)],
)
def test_lecture2_utilization(lam: float, expected_util: float) -> None:
    config = scenarios.study(lam, workers=3)
    assert config.utilization() == pytest.approx(expected_util, abs=1e-3)


def test_economic_parameters() -> None:
    economics = Economics()
    mix = OrderMix()
    # weighted price = 0.55*8 + 0.20*6 + 0.05*2 + 0.20*10 = 7.70
    assert economics.weighted_price(mix) == pytest.approx(7.70)
    assert economics.price_for("mix") == 10.0
    assert economics.waiting_cost_per_customer_minute == 0.5


def test_policy_validation() -> None:
    with pytest.raises(ValueError):
        Policy(mix_ice_priority="sometimes")
    with pytest.raises(ValueError):
        Policy(mix_ice_priority="dynamic")  # threshold missing
    policy = Policy(
        split_mix=True, mix_ice_priority="dynamic", dynamic_priority_threshold=2.0
    )
    assert "dyn" in policy.describe()


def test_invalid_configs_are_rejected() -> None:
    with pytest.raises(ValueError):
        SimConfig(workers=0)
    with pytest.raises(ValueError):
        SimConfig(arrival_rate=0)
    with pytest.raises(ValueError):
        SimConfig(warmup_minutes=500)
    with pytest.raises(ValueError):
        ServiceTimes().for_kind("sushi", split_mix=False)
