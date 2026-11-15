"""Regression anchors: the unified engine must reproduce the legacy scripts.

The expected values are copied from ``docs/experiment_log.md`` (the table the
course report cites) and from the original scripts' own output. The mixed-order
study averaged *per-replicate* means, while the bread-priority study averaged a
*pooled* customer list; both estimators are pinned here.
"""

from __future__ import annotations

import pytest

from bubble_tea_sim import scenarios, stats

# lam -> (all LOS, mixed LOS, ice handoff, bread LOS, utilisation) for synchro/split
MIXED_ORDER_GOLDEN = {
    (0.50, False): (2.20, 2.91, 2.91, 0.74, 0.354),
    (0.50, True): (2.06, 2.23, 0.88, 0.75, 0.354),
    (0.80, False): (2.44, 3.15, 3.15, 1.00, 0.566),
    (0.80, True): (2.34, 2.59, 0.98, 1.02, 0.566),
    (1.10, False): (3.30, 4.02, 4.02, 1.85, 0.776),
    (1.10, True): (3.28, 3.58, 1.13, 1.93, 0.776),
    (1.25, False): (4.93, 5.65, 5.65, 3.49, 0.882),
    (1.25, True): (5.05, 5.35, 1.24, 3.72, 0.882),
}

# (lam, fast_priority) -> pooled (bread, ice, tea, all) LOS and utilisation
BREAD_PRIORITY_GOLDEN = {
    (1.0, False): (1.04, 1.22, 2.92, 2.30, 0.636),
    (1.0, True): (0.89, 1.05, 2.95, 2.26, 0.636),
    (1.3, False): (1.88, 2.11, 3.70, 3.11, 0.825),
    (1.3, True): (1.11, 1.26, 3.85, 2.93, 0.825),
    (1.5, False): (4.34, 4.46, 6.21, 5.57, 0.936),
    (1.5, True): (1.32, 1.45, 6.70, 4.84, 0.936),
}


@pytest.mark.parametrize("lam,split", sorted(MIXED_ORDER_GOLDEN))
def test_mixed_order_anchor(lam: float, split: bool) -> None:
    config = scenarios.legacy_mixed_order(lam, split_mix=split)
    summary = stats.replicate(config, reps=200, seed=0, seed_stride=9001)
    expected_all, expected_mix, expected_ice, expected_bread, expected_util = (
        MIXED_ORDER_GOLDEN[(lam, split)]
    )
    means = summary.means
    assert means["mean_los"] == pytest.approx(expected_all, abs=0.006)
    assert means["mix_los"] == pytest.approx(expected_mix, abs=0.006)
    assert means["mix_ice_hand"] == pytest.approx(expected_ice, abs=0.006)
    assert means["los_bread"] == pytest.approx(expected_bread, abs=0.006)
    assert means["util"] == pytest.approx(expected_util, abs=0.001)


@pytest.mark.parametrize("lam,fast", sorted(BREAD_PRIORITY_GOLDEN))
def test_bread_priority_anchor(lam: float, fast: bool) -> None:
    config = scenarios.legacy_bread_priority(lam, fast_priority=fast)
    summary = stats.pooled_summary(config, reps=6, seed=0, seed_stride=7001)
    expected_bread, expected_ice, expected_tea, expected_all, expected_util = (
        BREAD_PRIORITY_GOLDEN[(lam, fast)]
    )
    los = summary["los"]
    assert los["bread"] == pytest.approx(expected_bread, abs=0.006)
    assert los["ice"] == pytest.approx(expected_ice, abs=0.006)
    assert los["tea"] == pytest.approx(expected_tea, abs=0.006)
    assert los["all"] == pytest.approx(expected_all, abs=0.006)
    assert summary["util"] == pytest.approx(expected_util, abs=0.001)


def test_mixed_order_conclusions_hold() -> None:
    """The two headline statements of the report, as executable assertions."""
    low_sync = stats.replicate(
        scenarios.legacy_mixed_order(0.5, split_mix=False), reps=100, seed_stride=9001
    )
    low_split = stats.replicate(
        scenarios.legacy_mixed_order(0.5, split_mix=True), reps=100, seed_stride=9001
    )
    high_sync = stats.replicate(
        scenarios.legacy_mixed_order(1.25, split_mix=False), reps=100, seed_stride=9001
    )
    high_split = stats.replicate(
        scenarios.legacy_mixed_order(1.25, split_mix=True), reps=100, seed_stride=9001
    )
    assert low_split.means["mean_los"] < low_sync.means["mean_los"]
    assert high_split.means["mean_los"] > high_sync.means["mean_los"]
