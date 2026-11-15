"""Policy-effect tests: the study's headlines as executable assertions.

These use paired comparisons on common random numbers, so the confidence
intervals are tight even with a moderate number of replicates.
"""

from __future__ import annotations

import pytest

from bubble_tea_sim import scenarios, stats


def test_split_helps_at_low_load() -> None:
    synchro = scenarios.study(0.50, workers=3, split_mix=False)
    split = scenarios.study(0.50, workers=3, split_mix=True)
    comparison = stats.paired_diff(split, synchro, reps=80, seed=0)
    expected = -0.134  # from docs/experiment_log.md (paired M2 table)
    assert comparison.diffs["mean_los"] == pytest.approx(expected, abs=0.03)
    assert comparison.diffs["mean_los"] + comparison.ci95["mean_los"] < 0


def test_split_hurts_at_high_load() -> None:
    synchro = scenarios.study(1.25, workers=3, split_mix=False)
    split = scenarios.study(1.25, workers=3, split_mix=True)
    comparison = stats.paired_diff(split, synchro, reps=80, seed=0)
    expected = +0.116
    assert comparison.diffs["mean_los"] == pytest.approx(expected, abs=0.04)
    assert comparison.diffs["mean_los"] - comparison.ci95["mean_los"] > 0


def test_split_hands_ice_cream_earlier() -> None:
    synchro = scenarios.study(1.25, workers=3, split_mix=False)
    split = scenarios.study(1.25, workers=3, split_mix=True)
    comparison = stats.paired_diff(split, synchro, reps=60, seed=0)
    assert comparison.diffs["mix_ice_hand"] < -3.5  # minutes earlier


def test_fast_priority_is_a_strong_lever_at_high_load() -> None:
    fcfs = scenarios.study(1.25, workers=3, split_mix=False, fast_priority=False)
    fast = scenarios.study(1.25, workers=3, split_mix=False, fast_priority=True)
    comparison = stats.paired_diff(fast, fcfs, reps=80, seed=0)
    # bread LOS falls sharply, tea LOS rises only slightly
    assert comparison.diffs["los_bread"] < -1.5
    assert comparison.diffs["los_tea"] > 0
    assert comparison.diffs["los_tea"] < 0.3
    assert comparison.diffs["mean_los"] < 0


def test_fast_priority_has_little_footprint_at_low_load() -> None:
    fcfs = scenarios.study(0.50, workers=3, split_mix=False, fast_priority=False)
    fast = scenarios.study(0.50, workers=3, split_mix=False, fast_priority=True)
    comparison = stats.paired_diff(fast, fcfs, reps=80, seed=0)
    assert abs(comparison.diffs["mean_los"]) < 0.05
    assert comparison.diffs["los_bread"] <= 0


def test_more_workers_reduce_waiting() -> None:
    two = scenarios.study(1.25, workers=2).utilization()
    three = scenarios.study(1.25, workers=3).utilization()
    four = scenarios.study(1.25, workers=4).utilization()
    assert two > three > four
    los_two = stats.replicate(scenarios.study(1.25, workers=2), reps=30).means["mean_los"]
    los_three = stats.replicate(scenarios.study(1.25, workers=3), reps=30).means["mean_los"]
    assert los_two > los_three
