"""Experiment 2 - where does split delivery stop paying for itself?

The break-even question
-----------------------
Split delivery hands the ice cream of a mixed order over immediately instead of
waiting for the tea.  Total clerk work is unchanged, so revenue is unchanged;
the only economic difference is *who waits*.  Two metrics are searched:

* ``profit_per_hour`` - money, with waiting priced at 0.5 per customer-minute
  and wages at 25 per worker-hour;
* ``mean_los`` - the all-store average time in system (the operational view).

Inside the paired design the two are algebraically equivalent for this model
(revenue is policy-invariant and waiting cost is linear in total flow time), so
the two ``lambda*`` values are expected to agree; the experiment reports both and
checks that expectation instead of assuming it.

Method
------
1. A paired ``split - synchro`` difference curve on a load grid per headcount
   (common random numbers, 200 replicates, 60 near overload).
2. :func:`bubble_tea_sim.stats.breakeven_lambda` - a bisection root search on the
   same difference - for the formal ``lambda*``.
3. An identification band derived from the 95% CI of the grid points: the
   largest load at which split is still significantly better and the smallest
   load at which it is significantly worse.

Output: ``results/breakeven.json``.

    python analysis/run_breakeven.py
"""

from __future__ import annotations

import argparse
import math
import time
from typing import Dict, List, Optional, Sequence, Tuple

import common
from bubble_tea_sim import stats
from bubble_tea_sim.params import OrderMix, ServiceTimes

#: Demand-weighted mean service time of the shipped default order mix.
P_BAR = common.service_mixture(OrderMix(), ServiceTimes())["p_bar"]

#: Load grid per headcount, centred on the expected crossing point.
GRID_BY_WORKERS: Dict[int, Tuple[float, float, float]] = {
    2: (0.40, 1.20, 0.05),
    3: (0.70, 1.50, 0.05),
    4: (1.00, 1.90, 0.05),
}

#: Bisection bracket; widened for 4 clerks (break-even sits above 1.30 there).
BRACKETS: Dict[int, Tuple[Tuple[float, float], ...]] = {
    2: ((0.40, 1.30),),
    3: ((0.50, 1.30),),
    4: ((0.50, 1.30), (1.30, 1.90)),
}

METRICS = ("profit_per_hour", "mean_los")
TOLERANCE = 0.01


def load_grid(workers: int) -> List[float]:
    low, high, step = GRID_BY_WORKERS[workers]
    count = int(round((high - low) / step)) + 1
    return [round(low + index * step, 2) for index in range(count)]


def make_configs(lam: float, workers: int):
    """``(split, synchro)`` pair at the same load (both FCFS, no behaviour)."""
    split = common.build_config(lam, workers=workers, split_mix=True, fast_priority=False)
    synchro = common.build_config(lam, workers=workers, split_mix=False, fast_priority=False)
    return split, synchro


def difference_curve(workers: int, *, reps: int) -> List[Dict[str, object]]:
    """Paired ``split - synchro`` differences on the load grid."""
    curve: List[Dict[str, object]] = []
    for lam in load_grid(workers):
        split, synchro = make_configs(lam, workers)
        cell_reps = common.reps_for(split, default=reps)
        comparison = stats.paired_diff(
            split,
            synchro,
            reps=cell_reps,
            seed=common.SEED,
            seed_stride=common.SEED_STRIDE,
        )
        curve.append(
            {
                "workers": workers,
                "arrival_rate": lam,
                "theory_util": split.utilization(),
                "reps": cell_reps,
                "diff": {key: comparison.diffs[key] for key in sorted(comparison.diffs)},
                "ci95": {
                    key: comparison.ci95[key]
                    for key in common.KEY_METRICS
                    if key in comparison.ci95
                },
            }
        )
        print(
            f"  w={workers} lam={lam:4.2f} util={split.utilization():5.3f} "
            f"dprofit={comparison.diffs['profit_per_hour']:+8.2f} "
            f"dlos={comparison.diffs['mean_los']:+7.3f}",
            flush=True,
        )
    return curve


def solve(
    workers: int, metric: str, *, reps: int
) -> Dict[str, object]:
    """Run the bisection for one (workers, metric), widening the bracket if needed."""
    attempts: List[Dict[str, object]] = []
    solved: Optional[Dict[str, object]] = None

    def make(lam: float):
        return make_configs(lam, workers)

    for index, (lower, upper) in enumerate(BRACKETS[workers]):
        result = stats.breakeven_lambda(
            make,
            lower=lower,
            upper=upper,
            reps=reps,
            seed=common.SEED,
            seed_stride=common.SEED_STRIDE,
            metric=metric,
            tolerance=TOLERANCE,
        )
        attempt = {
            "bracket": [lower, upper],
            "lambda": result.get("lambda"),
            "lower_difference": result.get("lower_difference"),
            "upper_difference": result.get("upper_difference"),
            "note": result.get("note"),
            "wider_bracket": index > 0,
        }
        attempts.append(attempt)
        if not math.isnan(float(attempt["lambda"])):
            solved = attempt
            break

    entry: Dict[str, object] = {
        "workers": workers,
        "metric": metric,
        "tolerance": TOLERANCE,
        "attempts": attempts,
    }
    if solved is None:
        entry.update(
            {
                "lambda_star": float("nan"),
                "solved": False,
                "note": (
                    "no sign change over any bracketing interval: split delivery "
                    "is still (or already) preferred at every tested load, so the "
                    "break-even load lies outside the simulated range"
                ),
            }
        )
        return entry

    lam = float(solved["lambda"])
    util = lam * P_BAR / workers
    entry.update(
        {
            "lambda_star": lam,
            "solved": True,
            "utilization_star": util,
            "bracket": solved["bracket"],
            "bracket_extension": bool(solved["wider_bracket"]),
            "difference_at_star": 0.0,
        }
    )
    return entry


def interpolation(curve: Sequence[Dict[str, object]], metric: str) -> Dict[str, object]:
    """Linear interpolation of the first sign change on the grid."""
    points = [(float(row["arrival_rate"]), float(row["diff"][metric])) for row in curve]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if y0 == 0:
            return {"lambda": x0, "method": "grid point is exactly zero"}
        if (y0 > 0) != (y1 > 0):
            fraction = y0 / (y0 - y1)
            return {
                "lambda": x0 + fraction * (x1 - x0),
                "method": "linear interpolation between grid points",
                "between": [x0, x1],
            }
    return {"lambda": float("nan"), "method": "no sign change on the grid"}


def identification_band(curve: Sequence[Dict[str, object]], metric: str) -> Dict[str, object]:
    """Loads where split is still significantly better / already significantly worse.

    The sign convention flips with the metric: a positive paired difference means
    "split is better" for profit but "split is worse" for a waiting time.
    """
    sign = 1.0 if metric == "profit_per_hour" else -1.0
    still_better: List[float] = []
    already_worse: List[float] = []
    for row in curve:
        diff = float(row["diff"][metric])
        half_width = float(row["ci95"].get(metric, 0.0))
        if sign * diff - half_width > 0:
            still_better.append(float(row["arrival_rate"]))
        if sign * diff + half_width < 0:
            already_worse.append(float(row["arrival_rate"]))
    return {
        "last_significantly_better": max(still_better) if still_better else None,
        "first_significantly_worse": min(already_worse) if already_worse else None,
    }


def run(*, reps: int = common.DEFAULT_REPS) -> Dict[str, object]:
    started = time.perf_counter()
    workers = sorted(GRID_BY_WORKERS)
    curve: List[Dict[str, object]] = []
    for worker_count in workers:
        print(f"difference curve, workers={worker_count}", flush=True)
        curve.extend(difference_curve(worker_count, reps=reps))

    print("bisection search", flush=True)
    breakeven: List[Dict[str, object]] = []
    for worker_count in workers:
        for metric in METRICS:
            entry = solve(worker_count, metric, reps=reps)
            entry["interpolated_lambda"] = interpolation(
                [row for row in curve if row["workers"] == worker_count], metric
            )
            entry["identification_band"] = identification_band(
                [row for row in curve if row["workers"] == worker_count], metric
            )
            breakeven.append(entry)
            print(
                f"  w={worker_count} {metric}: lambda*={entry['lambda_star']:.4f} "
                f"(interp {entry['interpolated_lambda']['lambda']:.4f}, "
                f"band {entry['identification_band']})",
                flush=True,
            )

    # Cross-check: do the money and time views agree, as the algebra says?
    crosscheck: List[Dict[str, object]] = []
    for worker_count in workers:
        money = next(
            row
            for row in breakeven
            if row["workers"] == worker_count and row["metric"] == "profit_per_hour"
        )
        time_view = next(
            row
            for row in breakeven
            if row["workers"] == worker_count and row["metric"] == "mean_los"
        )
        gap = money["lambda_star"] - time_view["lambda_star"]
        crosscheck.append(
            {
                "workers": worker_count,
                "profit_lambda": money["lambda_star"],
                "los_lambda": time_view["lambda_star"],
                "absolute_gap": abs(gap),
                "relative_gap": abs(gap) / max(abs(money["lambda_star"]), 1e-9),
                "agree_within_tolerance": abs(gap) <= 2 * max(TOLERANCE, 0.0) + 1e-9,
                "explanation": (
                    "Revenue is identical under both delivery strategies (the same "
                    "arrivals are served) and waiting cost is linear in total flow "
                    "time, so d(profit) = -(waiting cost rate) * d(total flow time). "
                    "The two break-even loads must therefore coincide; a gap of one "
                    "bisection tolerance is numerical, not economic."
                ),
            }
        )

    elapsed = time.perf_counter() - started
    print(f"break-even search finished in {elapsed:.1f}s", flush=True)
    return {
        "meta": common.meta(
            "breakeven",
            extra={
                "workers": workers,
                "metrics": list(METRICS),
                "tolerance": TOLERANCE,
                "reps_default": reps,
                "reps_overload": common.OVERLOAD_REPS,
                "overload_util_threshold": common.OVERLOAD_UTIL,
                "grid_by_workers": {
                    str(key): list(value) for key, value in GRID_BY_WORKERS.items()
                },
                "brackets": {
                    str(key): [list(pair) for pair in value]
                    for key, value in BRACKETS.items()
                },
                "p_bar": P_BAR,
                "definition": (
                    "Split delivery versus synchronised delivery, both FCFS, "
                    "identical seeds (common random numbers); positive difference "
                    "means split is better on that metric."
                ),
            },
        ),
        "curve": curve,
        "breakeven": breakeven,
        "crosscheck": crosscheck,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=common.DEFAULT_REPS)
    parser.add_argument("--out", default="breakeven.json")
    args = parser.parse_args(argv)
    payload = run(reps=args.reps)
    common.write_json(args.out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
