"""Invariants that must hold for every configuration and every replicate."""

from __future__ import annotations

import pytest

from bubble_tea_sim import scenarios, simulate
from bubble_tea_sim.engine import Simulation


def test_flow_conservation_without_behaviour() -> None:
    config = scenarios.study(1.25, workers=3, split_mix=True)
    result = Simulation(config, seed=7).run()
    served = sum(1 for customer in result.customers if customer.served)
    assert served == len(result.customers)
    assert result.metrics.served == sum(
        1
        for customer in result.customers
        if customer.served and customer.arrival >= config.warmup_minutes
    )


def test_flow_conservation_with_behaviour() -> None:
    config = scenarios.study(
        1.25,
        workers=3,
        split_mix=True,
        balk_threshold=10.0,
        renege_threshold=8.0,
        mix_ice_priority="dynamic",
        dynamic_priority_threshold=2.0,
    )
    result = Simulation(config, seed=11).run()
    abandoned = sum(1 for customer in result.customers if customer.abandoned)
    served = sum(1 for customer in result.customers if customer.served)
    assert served + abandoned == len(result.customers)
    assert result.metrics.balked + result.metrics.reneged == abandoned
    assert result.metrics.balked > 0
    assert result.metrics.reneged > 0


def test_no_negative_or_nan_timings() -> None:
    result = simulate(scenarios.study(1.0, workers=2), seed=3)
    for customer in result.customers:
        if not customer.served:
            continue
        assert customer.departure >= customer.arrival
        assert customer.departure >= 0
        if customer.tea_done is not None:
            assert customer.tea_done >= customer.arrival
        if customer.ice_done is not None:
            assert customer.ice_done >= customer.arrival


def test_seed_makes_runs_deterministic() -> None:
    config = scenarios.study(1.25, workers=3)
    first = simulate(config, seed=42).metrics.as_dict()
    second = simulate(config, seed=42).metrics.as_dict()
    third = simulate(config, seed=43).metrics.as_dict()
    assert first == second
    assert first != third


def test_utilization_invariant_to_delivery_policy() -> None:
    """Split vs synchro shuffle waiting; they must not change total workload."""
    base = scenarios.study(1.25, workers=3, split_mix=False)
    split = scenarios.study(1.25, workers=3, split_mix=True)
    synchro_metrics = Simulation(base, seed=5).run().metrics
    split_metrics = Simulation(split, seed=5).run().metrics
    assert split_metrics.util == pytest.approx(synchro_metrics.util, abs=1e-9)
    assert split_metrics.busy_minutes == pytest.approx(
        synchro_metrics.busy_minutes, abs=1e-9
    )


def test_warmup_is_excluded_from_statistics() -> None:
    config = scenarios.study(0.8, workers=3, split_mix=False)
    result = Simulation(config, seed=9).run()
    early = [
        customer
        for customer in result.customers
        if customer.served and customer.arrival < config.warmup_minutes
    ]
    assert early  # there are customers in the warm-up period
    assert result.metrics.served == len(result.customers) - len(early)
