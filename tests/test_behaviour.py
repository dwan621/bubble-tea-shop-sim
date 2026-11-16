"""Behaviour mechanisms: balking, reneging and melt-risk dynamic priority.

The numbers here are *study* values (unified engine), not original anchors. They
test that each mechanism exists, moves in the expected direction and keeps the
customer accounting consistent.
"""

from __future__ import annotations

import pytest

from bubble_tea_sim import scenarios, stats, simulate


def test_balking_removes_customers_from_the_system() -> None:
    baseline = scenarios.study(1.25, workers=3, split_mix=True)
    balky = scenarios.study(1.25, workers=3, split_mix=True, balk_threshold=3.0)
    base_summary = stats.replicate(baseline, reps=40, seed=0)
    balk_summary = stats.replicate(balky, reps=40, seed=0)
    assert base_summary.means["balked"] == 0.0
    assert balk_summary.means["balked"] > 10.0
    assert balk_summary.means["served"] < base_summary.means["served"]
    # Customers who stay are the ones who arrived to a short queue.
    assert balk_summary.means["mean_los"] < base_summary.means["mean_los"]


def test_reneging_removes_customers_from_the_system() -> None:
    baseline = scenarios.study(1.25, workers=3, split_mix=True)
    impatient = scenarios.study(1.25, workers=3, split_mix=True, renege_threshold=5.0)
    base_summary = stats.replicate(baseline, reps=40, seed=0)
    renege_summary = stats.replicate(impatient, reps=40, seed=0)
    assert renege_summary.means["reneged"] > 0.0
    assert renege_summary.means["served"] < base_summary.means["served"]


def test_dynamic_priority_sits_between_jump_and_fcfs() -> None:
    jump = scenarios.study(1.25, workers=3, split_mix=True, mix_ice_priority="jump")
    fcfs = scenarios.study(1.25, workers=3, split_mix=True, mix_ice_priority="fcfs")
    dynamic = scenarios.study(
        1.25,
        workers=3,
        split_mix=True,
        mix_ice_priority="dynamic",
        dynamic_priority_threshold=2.0,
    )
    jump_ice = stats.replicate(jump, reps=80, seed=0).means["mix_ice_hand"]
    fcfs_ice = stats.replicate(fcfs, reps=80, seed=0).means["mix_ice_hand"]
    dynamic_ice = stats.replicate(dynamic, reps=80, seed=0).means["mix_ice_hand"]
    assert jump_ice < dynamic_ice < fcfs_ice
    # ... and the store-wide waiting time moves in the opposite direction.
    jump_los = stats.replicate(jump, reps=80, seed=0).means["mean_los"]
    fcfs_los = stats.replicate(fcfs, reps=80, seed=0).means["mean_los"]
    dynamic_los = stats.replicate(dynamic, reps=80, seed=0).means["mean_los"]
    assert jump_los > dynamic_los > fcfs_los


def test_mix_ice_priority_is_ignored_without_split_delivery() -> None:
    synchro_jump = scenarios.study(1.25, workers=3, split_mix=False, mix_ice_priority="jump")
    synchro_fcfs = scenarios.study(1.25, workers=3, split_mix=False, mix_ice_priority="fcfs")
    first = simulate(synchro_jump, seed=1).metrics.as_dict()
    second = simulate(synchro_fcfs, seed=1).metrics.as_dict()
    assert first["mean_los"] == second["mean_los"]
    assert first["mix_ice_hand"] == second["mix_ice_hand"]


def test_behaviour_metrics_are_consistent() -> None:
    config = scenarios.study(
        1.25,
        workers=2,
        split_mix=True,
        balk_threshold=8.0,
        renege_threshold=12.0,
        mix_ice_priority="dynamic",
        dynamic_priority_threshold=2.5,
    )
    result = simulate(config, seed=2)
    metrics = result.metrics
    assert metrics.balked + metrics.reneged + metrics.served <= len(result.customers)
    assert 0.0 <= metrics.util <= 1.0
    assert metrics.mix_ice_hand > 0.0
    assert metrics.mean_los > 0.0
