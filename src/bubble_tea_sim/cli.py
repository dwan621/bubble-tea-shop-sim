"""Command-line interface for the bubble-tea shop study.

Examples
--------
Run one configuration and print its metrics::

    python -m bubble_tea_sim run --lam 1.25 --split

Reproduce the legacy anchors used in the report::

    python -m bubble_tea_sim reproduce --out results/legacy_anchors.json

Inspect the policy sweep used by the README/figures (the committed
``results/policy_sweep.json`` is produced by ``analysis/run_policy_sweep.py``,
which adds provenance metadata and paired differences)::

    python -m bubble_tea_sim sweep --workers-list 1,2,3,4,5 \
        --lambdas 0.4,0.6,0.8,1.0,1.2,1.25 --reps 200

The CLI only uses the standard library and writes JSON so downstream scripts
(report generation, figures) never need to re-run the simulation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Sequence

from . import __version__, scenarios, stats
from .engine import Simulation
from .params import SimConfig


def _json_dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    print(f"wrote {path}")


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--reps", type=int, default=100, help="replicates (default 100)")
    parser.add_argument("--seed", type=int, default=0, help="first replicate seed")
    parser.add_argument(
        "--seed-stride",
        type=int,
        default=1,
        help="increment between replicate seeds (legacy: 9001 / 7001)",
    )
    parser.add_argument("--out", type=Path, default=None, help="optional JSON output")


def _policy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lam", type=float, default=1.25, help="arrival rate customers/min")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--split", action="store_true", help="split delivery for mixed orders")
    parser.add_argument("--fast", action="store_true", help="fast-item priority")
    parser.add_argument("--balk", type=float, default=None, help="balk threshold (minutes)")
    parser.add_argument("--renege", type=float, default=None, help="renege threshold (minutes)")
    parser.add_argument(
        "--dyn-prio", type=float, default=None, help="dynamic priority threshold (minutes)"
    )
    parser.add_argument("--name", default=None)


def _config_from_args(args: argparse.Namespace) -> SimConfig:
    return scenarios.study(
        args.lam,
        workers=args.workers,
        split_mix=args.split,
        fast_priority=args.fast,
        balk_threshold=args.balk,
        renege_threshold=args.renege,
        dynamic_priority_threshold=args.dyn_prio,
        name=args.name,
    )


def _fmt_metrics(metrics) -> str:
    return (
        f"served={metrics.served} util={metrics.util:.1%} "
        f"LOS={metrics.mean_los:.2f} mix={metrics.mix_los:.2f} "
        f"ice_hand={metrics.mix_ice_hand:.2f} profit/h={metrics.profit_per_hour:.1f} "
        f"balk={metrics.balked} renege={metrics.reneged}"
    )


def cmd_run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    result = Simulation(config, seed=args.seed).run()
    print(json.dumps(result.metrics.as_dict(), indent=2, ensure_ascii=False))
    print(_fmt_metrics(result.metrics))
    if args.out:
        _json_dump(args.out, result.metrics.as_dict())
    return 0


def cmd_reproduce(args: argparse.Namespace) -> int:
    """Recompute the legacy anchor tables recorded in the report/experiment log."""
    payload: Dict[str, object] = {"mixed_order": {}, "bread_priority": {}}
    print(
        f"Mixed-order M2 anchors (per-replicate means, {args.reps} reps, stride 9001)"
    )
    for lam in (0.5, 0.8, 1.1, 1.25):
        for split in (False, True):
            config = scenarios.legacy_mixed_order(lam, split_mix=split)
            summary = stats.replicate(
                config, reps=args.reps, seed=0, seed_stride=9001
            )
            key = f"lam{lam:g}-{'split' if split else 'synchro'}"
            payload["mixed_order"][key] = summary.as_dict()
            print(
                f"  lam={lam:>4} {key.split('-')[-1]:>8} all={summary.means['mean_los']:.2f} "
                f"mix={summary.means['mix_los']:.2f} ice={summary.means['mix_ice_hand']:.2f} "
                f"bread={summary.means['los_bread']:.2f} util={summary.means['util']:.1%}"
            )
    print("Bread-priority P-series anchors (pooled means, 6 reps, stride 7001)")
    for lam in (1.0, 1.3, 1.5):
        for fast in (False, True):
            config = scenarios.legacy_bread_priority(lam, fast_priority=fast)
            summary = stats.pooled_summary(
                config, reps=6, seed=0, seed_stride=7001
            )
            key = f"lam{lam:g}-{'fast' if fast else 'fcfs'}"
            payload["bread_priority"][key] = summary
            los = summary["los"]
            print(
                f"  lam={lam:>4} {key.split('-')[-1]:>5} bread={los['bread']:.2f} "
                f"ice={los['ice']:.2f} tea={los['tea']:.2f} all={los['all']:.2f} "
                f"util={summary['util']:.1%}"
            )
    if args.out:
        _json_dump(args.out, payload)
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    lambdas = [float(value) for value in args.lambdas.split(",")]
    workers = [int(value) for value in args.workers_list.split(",")]
    records: List[Dict[str, object]] = []
    for worker_count in workers:
        for lam in lambdas:
            for config in scenarios.four_policies(lam, workers=worker_count):
                summary = stats.replicate(
                    config,
                    reps=args.reps,
                    seed=args.seed,
                    seed_stride=args.seed_stride,
                )
                record = summary.as_dict()
                record["workers"] = worker_count
                records.append(record)
                print(
                    f"workers={worker_count} lam={lam:g} {config.policy.describe():>22} "
                    f"LOS={summary.means['mean_los']:.2f} profit/h="
                    f"{summary.means['profit_per_hour']:.1f}"
                )
    payload = {"version": __version__, "records": records}
    if args.out:
        _json_dump(args.out, payload)
    return 0


def cmd_breakeven(args: argparse.Namespace) -> int:
    def make(lam: float):
        synchro = scenarios.study(lam, workers=args.workers, split_mix=False)
        split = scenarios.study(lam, workers=args.workers, split_mix=True)
        return split, synchro

    result = stats.breakeven_lambda(
        make,
        lower=args.lower,
        upper=args.upper,
        reps=args.reps,
        seed=args.seed,
        seed_stride=args.seed_stride,
        metric=args.metric,
        tolerance=args.tolerance,
    )
    print(json.dumps(result, indent=2))
    if args.out:
        _json_dump(args.out, result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bubble-tea",
        description="Bubble-tea shop discrete-event simulation study.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run one configuration")
    _policy_args(run_parser)
    run_parser.add_argument("--seed", type=int, default=0)
    run_parser.add_argument("--out", type=Path, default=None)
    run_parser.set_defaults(func=cmd_run)

    reproduce_parser = sub.add_parser("reproduce", help="recompute legacy anchor tables")
    reproduce_parser.add_argument("--reps", type=int, default=200)
    reproduce_parser.add_argument("--out", type=Path, default=None)
    reproduce_parser.set_defaults(func=cmd_reproduce)

    sweep_parser = sub.add_parser("sweep", help="policy sweep over loads and worker counts")
    _add_common(sweep_parser)
    sweep_parser.add_argument("--workers-list", default="1,2,3,4,5")
    sweep_parser.add_argument("--lambdas", default="0.4,0.6,0.8,1.0,1.2,1.25")
    sweep_parser.set_defaults(func=cmd_sweep)

    breakeven_parser = sub.add_parser("breakeven", help="solve the split/synchro break-even load")
    _add_common(breakeven_parser)
    breakeven_parser.add_argument("--workers", type=int, default=3)
    breakeven_parser.add_argument("--lower", type=float, default=0.5)
    breakeven_parser.add_argument("--upper", type=float, default=1.3)
    breakeven_parser.add_argument("--metric", default="profit_per_hour")
    breakeven_parser.add_argument("--tolerance", type=float, default=0.01)
    breakeven_parser.set_defaults(func=cmd_breakeven)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
