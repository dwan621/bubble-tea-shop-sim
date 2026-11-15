"""Experiment 3 - one-at-a-time sensitivity of the profit / waiting trade-off.

Baseline: ``lambda = 1.25`` customers/min, 3 clerks, the shipped default order
mix and economics (88.2% utilisation - the load the course report treats as the
"busy but feasible" operating point).

Each dimension is varied on its own, everything else held at the baseline:

======================  ==========================================
dimension               values
======================  ==========================================
wage per worker-hour    ``15, 20, 25, 30, 35``
waiting cost per        ``0.20, 0.35, 0.50, 0.75, 1.00``
customer-minute
mixed-order share       ``0.10 ... 0.30`` (tea share absorbs the
                        difference, bread 0.20 and ice 0.05 fixed)
tea make time           ``1.5, 2.0, 2.5`` min
======================  ==========================================

Two policy arms are simulated (Synchro FCFS and Split FCFS) so the report can
say whether the sensitivity ranking depends on the delivery strategy.

A useful structural fact falls out of this design and is recorded in the JSON:
``wage_per_worker_hour`` and ``waiting_cost_per_customer_minute`` enter *only*
in the post-processing economics (they do not change the event schedule), so
those two sweeps are exact linear transforms of the same run and their slopes
can be derived in closed form.  The mix-share and tea-time sweeps, by contrast,
change the dynamics and therefore carry genuine simulated variation.

Output: ``results/sensitivity.json``.

    python analysis/run_sensitivity.py
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from typing import Dict, List, Sequence

import common
from bubble_tea_sim import scenarios, stats
from bubble_tea_sim.params import OrderMix, ServiceTimes

BASELINE_LAMBDA = 1.25
BASELINE_WORKERS = 3
BASE_MIX = OrderMix()
BASE_TIMES = ServiceTimes()

#: (key, label, values, unit)
DIMENSIONS = (
    (
        "wage_per_worker_hour",
        "Wage per worker-hour",
        (15.0, 20.0, 25.0, 30.0, 35.0),
        "currency units / worker-hour",
    ),
    (
        "waiting_cost_per_customer_minute",
        "Waiting cost",
        (0.20, 0.35, 0.50, 0.75, 1.00),
        "currency units / customer-minute",
    ),
    (
        "mixed_order_share",
        "Mixed-order share",
        (0.10, 0.15, 0.20, 0.25, 0.30),
        "share of arrivals",
    ),
    (
        "tea_make_time",
        "Tea make time",
        (1.5, 2.0, 2.5),
        "minutes",
    ),
)

BASELINE_VALUES = {
    "wage_per_worker_hour": 25.0,
    "waiting_cost_per_customer_minute": 0.50,
    "mixed_order_share": BASE_MIX.mix,
    "tea_make_time": BASE_TIMES.tea,
}

POLICIES = ((False, False), (True, False))


def variant(
    key: str, value: float, *, split_mix: bool, workers: int = BASELINE_WORKERS
):
    """Baseline configuration with exactly one parameter changed."""
    base = scenarios.study(
        BASELINE_LAMBDA, workers=workers, split_mix=split_mix, fast_priority=False
    )
    suffix = common.policy_key(split_mix, False)
    if key == "wage_per_worker_hour":
        config = replace(
            base, economics=replace(base.economics, wage_per_worker_hour=value)
        )
    elif key == "waiting_cost_per_customer_minute":
        config = replace(
            base,
            economics=replace(base.economics, waiting_cost_per_customer_minute=value),
        )
    elif key == "mixed_order_share":
        config = replace(
            base,
            mix=OrderMix(tea=round(1.0 - 0.20 - 0.05 - value, 10), bread=0.20, ice=0.05, mix=value),
        )
    elif key == "tea_make_time":
        config = replace(base, times=replace(base.times, tea=value))
    else:  # pragma: no cover - defence against typos in DIMENSIONS
        raise ValueError(f"unknown sensitivity dimension: {key}")
    return replace(config, name=f"study-lam{BASELINE_LAMBDA:g}-w{workers}-{suffix}-{key}={value:g}")


def analytical_slope(key: str, baseline_means: Dict[str, float], workers: int) -> Dict[str, object]:
    """Closed-form slope of ``profit_per_hour`` for the economics-only knobs."""
    if key == "wage_per_worker_hour":
        return {
            "per_unit": -float(workers),
            "formula": "dProfit/dWage = -workers (an extra currency unit per worker-hour "
            "costs workers currency units per hour)",
            "affected_by_noise": False,
        }
    if key == "waiting_cost_per_customer_minute":
        hours = 8.0
        return {
            "per_unit": -baseline_means["flow_time_total"] / hours,
            "formula": "dProfit/dWaitingCost = -flow_time_total / hours = -mean "
            "customers in system per hour",
            "affected_by_noise": False,
        }
    return {
        "per_unit": None,
        "formula": "not available in closed form: this knob changes the event schedule",
        "affected_by_noise": True,
    }


def run(*, reps: int = common.DEFAULT_REPS) -> Dict[str, object]:
    baseline: Dict[str, object] = {}
    for split_mix, fast_priority in POLICIES:
        config = scenarios.study(
            BASELINE_LAMBDA,
            workers=BASELINE_WORKERS,
            split_mix=split_mix,
            fast_priority=fast_priority,
        )
        summary = stats.replicate(
            config, reps=reps, seed=common.SEED, seed_stride=common.SEED_STRIDE
        )
        key = common.policy_key(split_mix, fast_priority)
        baseline[key] = {
            "policy_label": common.policy_label(split_mix, fast_priority),
            "config": config.describe(),
            "reps": reps,
            "means": {name: summary.means[name] for name in sorted(summary.means)},
            "ci95": summary.ci95,
        }
        print(
            f"baseline {key}: profit/h={summary.means['profit_per_hour']:.1f} "
            f"los={summary.means['mean_los']:.3f} util={summary.means['util']:.4f}",
            flush=True,
        )

    dimensions: List[Dict[str, object]] = []
    for key, label, values, unit in DIMENSIONS:
        series: List[Dict[str, object]] = []
        for split_mix, fast_priority in POLICIES:
            policy = common.policy_key(split_mix, fast_priority)
            base_means = baseline[policy]["means"]
            points: List[Dict[str, object]] = []
            for value in values:
                config = variant(key, value, split_mix=split_mix)
                summary = stats.replicate(
                    config,
                    reps=reps,
                    seed=common.SEED,
                    seed_stride=common.SEED_STRIDE,
                )
                points.append(
                    {
                        "value": value,
                        "config": config.describe(),
                        "reps": reps,
                        "means": {name: summary.means[name] for name in sorted(summary.means)},
                        "ci95": {
                            name: summary.ci95[name]
                            for name in common.KEY_METRICS
                            if name in summary.ci95
                        },
                        "delta_profit_per_hour": (
                            summary.means["profit_per_hour"] - base_means["profit_per_hour"]
                        ),
                        "delta_mean_los": (
                            summary.means["mean_los"] - base_means["mean_los"]
                        ),
                    }
                )
            profits = [point["means"]["profit_per_hour"] for point in points]
            losses = [point["means"]["mean_los"] for point in points]
            series.append(
                {
                    "policy_key": policy,
                    "policy_label": common.policy_label(split_mix, fast_priority),
                    "baseline_value": BASELINE_VALUES[key],
                    "analytical": analytical_slope(key, base_means, BASELINE_WORKERS),
                    "points": points,
                    "profit_range": max(profits) - min(profits),
                    "los_range": max(losses) - min(losses),
                }
            )
            print(
                f"  {label}/{policy}: profit "
                + ", ".join(f"{value:g}->{point['means']['profit_per_hour']:.1f}" for value, point in zip(values, points)),
                flush=True,
            )
        dimensions.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "values": list(values),
                "baseline_value": BASELINE_VALUES[key],
                "series": series,
            }
        )

    # Verify that the two economics-only sweeps are exactly linear.
    linearity: List[Dict[str, object]] = []
    for dimension in dimensions:
        if dimension["key"] not in (
            "wage_per_worker_hour",
            "waiting_cost_per_customer_minute",
        ):
            continue
        for series in dimension["series"]:
            slope = series["analytical"]["per_unit"]
            base_value = series["baseline_value"]
            base_profit = next(
                point["means"]["profit_per_hour"]
                for point in series["points"]
                if abs(point["value"] - base_value) < 1e-12
            )
            residuals = [
                point["means"]["profit_per_hour"]
                - (base_profit + slope * (point["value"] - base_value))
                for point in series["points"]
            ]
            linearity.append(
                {
                    "dimension": dimension["key"],
                    "policy": series["policy_key"],
                    "analytical_slope": slope,
                    "max_abs_residual": max(abs(value) for value in residuals),
                    "is_exactly_linear": max(abs(value) for value in residuals) < 1e-9,
                }
            )

    return {
        "meta": common.meta(
            "sensitivity",
            extra={
                "baseline": {
                    "arrival_rate": BASELINE_LAMBDA,
                    "workers": BASELINE_WORKERS,
                    "mix": BASE_MIX.as_dict(),
                    "service_times": {
                        "order": BASE_TIMES.order,
                        "tea": BASE_TIMES.tea,
                        "bread": BASE_TIMES.bread,
                        "ice": BASE_TIMES.ice,
                    },
                    "economics": {
                        "wage_per_worker_hour": 25.0,
                        "waiting_cost_per_customer_minute": 0.5,
                        "prices": {"tea": 8.0, "bread": 6.0, "ice": 2.0, "mix": 10.0},
                    },
                    "theory_utilization": BASELINE_LAMBDA * common.service_mixture(BASE_MIX, BASE_TIMES)["p_bar"] / BASELINE_WORKERS,
                },
                "reps": reps,
                "design": "one-at-a-time (OAT); every other parameter held at baseline",
                "policy_arms": [common.policy_key(*policy) for policy in POLICIES],
            },
        ),
        "baseline": baseline,
        "dimensions": dimensions,
        "linearity_check": linearity,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=common.DEFAULT_REPS)
    parser.add_argument("--out", default="sensitivity.json")
    args = parser.parse_args(argv)
    payload = run(reps=args.reps)
    common.write_json(args.out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
