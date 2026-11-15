"""Documented edge cases: overload arithmetic and empty order classes."""

from __future__ import annotations

from bubble_tea_sim import OrderMix, scenarios, simulate


def test_overload_utilisation_is_a_window_ratio_above_one() -> None:
    """A backed-up queue can do more work than the window's nominal capacity.

    ``util = busy / (workers * sim_minutes)`` mirrors the legacy scripts, so an
    overloaded configuration can exceed 1. This test documents the convention so
    a future contributor does not "fix" it.
    """
    config = scenarios.study(2.0, workers=2, warmup_minutes=0.0)
    metrics = simulate(config, seed=1).metrics
    assert metrics.util > 1.0
    assert metrics.mean_los > 5.0


def test_order_mix_without_mixed_orders() -> None:
    config = scenarios.study(
        1.0,
        workers=3,
        mix=OrderMix(tea=0.70, bread=0.20, ice=0.10, mix=0.0),
    )
    result = simulate(config, seed=0)
    assert result.metrics.counts["mix"] == 0
    assert result.metrics.mix_los == 0.0


def test_all_mixed_orders_use_split_handoff() -> None:
    config = scenarios.study(
        0.5,
        workers=3,
        split_mix=True,
        mix=OrderMix(tea=0.0, bread=0.0, ice=0.0, mix=1.0),
    )
    result = simulate(config, seed=0)
    assert result.metrics.counts["mix"] > 0
    assert result.metrics.counts["tea"] == 0
    assert result.metrics.mix_ice_hand > 0.0
