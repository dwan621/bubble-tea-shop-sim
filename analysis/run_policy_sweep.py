"""Experiment 1 - policy sweep over load, headcount and the 2x2 policy matrix.

Design
------
* workers ``1..5``;
* arrival rate ``0.30 .. 1.30`` customers/min in steps of ``0.05``
  (for a single clerk the run is truncated at ``lambda = 0.50`` because the
  single-server capacity is only ``1 / 2.117 = 0.472`` customers/min: above that
  every configuration is unstable and the numbers stop being decision-grade);
* the four policies ``{Synchro, Split} x {FCFS, Fast priority}``;
* ``200`` replicates per cell, reduced to ``60`` once the theoretical utilisation
  reaches ``0.95`` (near overload the queue tail dominates and extra replicates
  buy very little);
* identical seeds across the four policies (common random numbers), so the
  paired differences stored in ``pairs`` are low-variance.  They are computed
  from the retained per-replicate rows instead of re-running the engine.

Output: ``results/policy_sweep.json`` (also carries the Lecture 1-4 theory block
used by the report to validate the simulation).

Run from the repository root::

    python analysis/run_policy_sweep.py
"""

from __future__ import annotations

import argparse
import time
from typing import Dict, List, Sequence, Tuple

import common
from bubble_tea_sim import scenarios, stats
from bubble_tea_sim.params import Economics, OrderMix, ServiceTimes

#: Workers 1 has a capacity of 1/p_bar = 0.472 customers/min.
LAMBDA_GRID: Tuple[float, ...] = tuple(round(0.30 + 0.05 * index, 2) for index in range(21))
WORKERS: Tuple[int, ...] = (1, 2, 3, 4, 5)
WORKERS_ONE_MAX_LAMBDA = 0.50

#: Pair keys and their human-readable meaning (a - b).
PAIR_SPECS: Tuple[Tuple[str, Tuple[bool, bool], Tuple[bool, bool], str], ...] = (
    (
        "split_minus_synchro",
        (True, False),
        (False, False),
        "Split - Synchro (FCFS, fast priority off)",
    ),
    (
        "fast_minus_fcfs",
        (False, True),
        (False, False),
        "Fast priority - FCFS (synchronised delivery)",
    ),
    (
        "combo_minus_baseline",
        (True, True),
        (False, False),
        "Split + fast priority - Synchro FCFS",
    ),
)


def lambdas_for(workers: int) -> List[float]:
    """Load grid for one headcount (single clerk is capped at 0.50)."""
    if workers == 1:
        return [lam for lam in LAMBDA_GRID if lam <= WORKERS_ONE_MAX_LAMBDA + 1e-9]
    return list(LAMBDA_GRID)


def _record(
    summary: stats.ReplicateSummary,
    *,
    workers: int,
    lam: float,
    split_mix: bool,
    fast_priority: bool,
    base_reps: int,
) -> Dict[str, object]:
    config = summary.config
    return {
        "workers": workers,
        "arrival_rate": lam,
        "split_mix": split_mix,
        "fast_priority": fast_priority,
        "policy_key": common.policy_key(split_mix, fast_priority),
        "policy_label": common.policy_label(split_mix, fast_priority),
        "config": config.describe(),
        "reps": summary.reps,
        "reduced_reps": summary.reps != base_reps,
        "theory_util": config.utilization(),
        "overload": config.utilization() >= common.OVERLOAD_UTIL,
        "means": {key: summary.means[key] for key in sorted(summary.means)},
        "ci95": {
            key: summary.ci95[key] for key in common.KEY_METRICS if key in summary.ci95
        },
    }


def run(
    *,
    workers: Sequence[int] = WORKERS,
    lambdas: Sequence[float] = LAMBDA_GRID,
    base_reps: int = common.DEFAULT_REPS,
    overload_reps: int = common.OVERLOAD_REPS,
) -> Dict[str, object]:
    started = time.perf_counter()
    records: List[Dict[str, object]] = []
    pairs: List[Dict[str, object]] = []

    for worker_count in workers:
        group = [
            lam for lam in lambdas_for(worker_count) if any(abs(lam - x) < 1e-9 for x in lambdas)
        ]
        cell_started = time.perf_counter()
        for lam in group:
            summaries: Dict[Tuple[bool, bool], stats.ReplicateSummary] = {}
            for split_mix, fast_priority in common.POLICY_MATRIX:
                config = common.build_config(
                    lam,
                    workers=worker_count,
                    split_mix=split_mix,
                    fast_priority=fast_priority,
                )
                reps = (
                    overload_reps
                    if config.utilization() >= common.OVERLOAD_UTIL
                    else base_reps
                )
                summary = stats.replicate(
                    config, reps=reps, seed=common.SEED, seed_stride=common.SEED_STRIDE
                )
                summaries[(split_mix, fast_priority)] = summary
                records.append(
                    _record(
                        summary,
                        workers=worker_count,
                        lam=lam,
                        split_mix=split_mix,
                        fast_priority=fast_priority,
                        base_reps=base_reps,
                    )
                )
            for pair_key, side_a, side_b, label in PAIR_SPECS:
                summary_a = summaries[side_a]
                summary_b = summaries[side_b]
                diffs, half_widths = common.paired_from_rows(
                    summary_a.per_rep, summary_b.per_rep
                )
                pairs.append(
                    {
                        "workers": worker_count,
                        "arrival_rate": lam,
                        "pair_key": pair_key,
                        "label": label,
                        "reps": summary_a.reps,
                        "diff": diffs,
                        "ci95": half_widths,
                    }
                )
        elapsed = time.perf_counter() - cell_started
        print(
            f"  workers={worker_count}: {len(group)} load points x 4 policies "
            f"in {elapsed:.1f}s",
            flush=True,
        )

    theory = common.theory_block(
        mix=OrderMix(),
        times=ServiceTimes(),
        workers_list=list(workers),
        lambdas=list(lambdas),
        weighted_price=Economics().weighted_price(OrderMix()),
    )
    elapsed = time.perf_counter() - started
    print(f"policy sweep finished in {elapsed:.1f}s", flush=True)

    return {
        "meta": common.meta(
            "policy_sweep",
            extra={
                "workers": list(workers),
                "lambdas": list(lambdas),
                "workers_one_max_lambda": WORKERS_ONE_MAX_LAMBDA,
                "policies": [
                    {
                        "split_mix": split,
                        "fast_priority": fast,
                        "key": common.policy_key(split, fast),
                        "label": common.policy_label(split, fast),
                    }
                    for split, fast in common.POLICY_MATRIX
                ],
                "reps_default": base_reps,
                "reps_overload": overload_reps,
                "overload_util_threshold": common.OVERLOAD_UTIL,
                "sim_minutes": scenarios.study(1.0).sim_minutes,
                "warmup_minutes": scenarios.study(1.0).warmup_minutes,
                "common_random_numbers": True,
                "pair_specs": [spec[3] for spec in PAIR_SPECS],
            },
        ),
        "theory": theory,
        "records": records,
        "pairs": pairs,
    }


def print_headline(payload: Dict[str, object]) -> None:
    """Print a compact eyeball table for the terminal."""
    print("\nworkers=3 profit/hour (FCFS synchro vs split vs fast vs combo)")
    print("  lam   util  synchro   split    fast   combo   d_split  d_fast")
    by_cell: Dict[Tuple[int, float], Dict[str, float]] = {}
    for record in payload["records"]:  # type: ignore[index]
        if record["workers"] != 3:
            continue
        cell = by_cell.setdefault((record["workers"], record["arrival_rate"]), {})
        cell[record["policy_key"]] = record["means"]["profit_per_hour"]
        cell["util"] = record["means"]["util"]
    pair_index = {
        (pair["workers"], pair["arrival_rate"], pair["pair_key"]): pair
        for pair in payload["pairs"]  # type: ignore[index]
    }
    for (_, lam), cell in sorted(by_cell.items()):
        d_split = pair_index[(3, lam, "split_minus_synchro")]["diff"]["profit_per_hour"]
        d_fast = pair_index[(3, lam, "fast_minus_fcfs")]["diff"]["profit_per_hour"]
        print(
            f"  {lam:4.2f}  {cell['util']:5.3f}  {cell['synchro+fcfs']:8.1f} "
            f"{cell['split+fcfs']:8.1f} {cell['synchro+fast']:7.1f} "
            f"{cell['split+fast']:7.1f} {d_split:8.2f} {d_fast:7.2f}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=common.DEFAULT_REPS)
    parser.add_argument("--overload-reps", type=int, default=common.OVERLOAD_REPS)
    parser.add_argument("--out", default="policy_sweep.json")
    args = parser.parse_args(argv)

    payload = run(base_reps=args.reps, overload_reps=args.overload_reps)
    common.write_json(args.out, payload)
    print_headline(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
