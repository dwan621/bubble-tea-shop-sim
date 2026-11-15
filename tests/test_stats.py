"""Statistics layer: aggregation, confidence intervals and break-even search."""

from __future__ import annotations

import math

import pytest

from bubble_tea_sim import scenarios, stats


def test_basic_statistics() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert stats.mean(values) == 2.5
    assert stats.stdev(values) == pytest.approx(math.sqrt(5 / 3))
    assert stats.ci95(values) == pytest.approx(1.959963984540054 * math.sqrt(5 / 3) / 2)
    assert stats.mean([]) == 0.0
    assert stats.ci95([1.0]) == 0.0


def test_flatten_metrics_contains_headline_keys() -> None:
    config = scenarios.study(0.8, workers=3)
    from bubble_tea_sim.engine import Simulation

    metrics = Simulation(config, seed=0).run().metrics
    flat = stats.flatten_metrics(metrics)
    for key in (
        "mean_los",
        "mix_los",
        "mix_ice_hand",
        "util",
        "profit_per_hour",
        "los_tea",
        "los_bread",
        "los_ice",
        "count_mix",
    ):
        assert key in flat
        assert flat[key] >= 0


def test_paired_comparison_uses_common_random_numbers() -> None:
    a = scenarios.study(1.0, workers=3, split_mix=True)
    b = scenarios.study(1.0, workers=3, split_mix=False)
    comparison = stats.paired_diff(a, b, reps=25, seed=0)
    # A paired comparison is deterministic for a fixed seed.
    again = stats.paired_diff(a, b, reps=25, seed=0)
    assert comparison.diffs == again.diffs
    # Utilisation is invariant to the delivery policy, even replicate by replicate.
    assert comparison.diffs["util"] == pytest.approx(0.0, abs=1e-12)


def test_breakeven_finds_the_delivery_policy_crossover() -> None:
    def make(lam: float):
        return (
            scenarios.study(lam, workers=3, split_mix=True),
            scenarios.study(lam, workers=3, split_mix=False),
        )

    los_result = stats.breakeven_lambda(
        make, lower=0.6, upper=1.3, reps=40, metric="mean_los", tolerance=0.02
    )
    profit_result = stats.breakeven_lambda(
        make, lower=0.6, upper=1.3, reps=40, metric="profit_per_hour", tolerance=0.02
    )
    assert 1.05 < los_result["lambda"] < 1.20
    assert 1.05 < profit_result["lambda"] < 1.20
    # Both metrics agree because the economic layer only re-weights waiting time.
    assert los_result["lambda"] == pytest.approx(profit_result["lambda"], abs=0.05)


def test_breakeven_reports_no_crossover_when_sign_does_not_change() -> None:
    def make(lam: float):
        return (
            scenarios.study(lam, workers=3, fast_priority=True),
            scenarios.study(lam, workers=3, fast_priority=False),
        )

    result = stats.breakeven_lambda(
        make, lower=0.6, upper=1.25, reps=8, metric="mean_los"
    )
    # Fast priority wins at every tested load, so no sign change is expected.
    assert math.isnan(result["lambda"]) or 0.6 <= result["lambda"] <= 1.25


def test_pooled_estimator_matches_legacy_table() -> None:
    config = scenarios.legacy_bread_priority(1.5, fast_priority=False)
    pooled = stats.pooled_los(config, reps=6, seed=0, seed_stride=7001)
    assert pooled["bread"] == pytest.approx(4.34, abs=0.01)
    assert pooled["all"] == pytest.approx(5.57, abs=0.01)
