"""Experiment 4 - behaviour mechanisms: balking, reneging, dynamic priority.

Three operational rules are layered on top of the baseline policy and measured
at two loads (``lambda = 1.00`` and ``1.25``, 3 clerks):

Balking / 顾客看到长队直接离开
    A customer walks away at arrival when the estimated wait exceeds a threshold
    in minutes (``None`` disables the rule).  The estimate is the engine's
    Little's-Law style rule ``in_system * p_bar / m``, so a 3-minute threshold
    with 3 clerks fires when roughly 4 customers are already in the shop.

Reneging / 排队太久后离开
    A customer leaves if service has not started within the threshold minutes
    (``None`` disables the rule).  Waiting *before* service start is what counts;
    once a clerk starts, the customer stays.

Dynamic priority / 冰淇淋动态插队
    Only meaningful for split delivery: the ice-cream component of a mixed order
    jumps the queue immediately (``jump``), never (``fcfs``), or only after it has
    waited ``t`` minutes (``dynamic``).  The idea is to buy most of the melting
    benefit without unconditionally penalising the main queue.

Abandonment is measured on arrivals *after* the warm-up window (the engine's own
``balked``/``reneged`` counters cover the whole run including warm-up), so
``abandon_rate`` always has the same denominator as ``served``.

Output: ``results/behaviour.json``.

    python analysis/run_behaviour.py
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Optional, Sequence

import common
from bubble_tea_sim import scenarios, stats
from bubble_tea_sim.engine import Simulation
from bubble_tea_sim.stats import flatten_metrics

LAMBDAS = (1.0, 1.25)
WORKERS = 3

BALK_THRESHOLDS: Sequence[Optional[float]] = (None, 3.0, 5.0, 8.0, 10.0)
RENEGE_THRESHOLDS: Sequence[Optional[float]] = (None, 10.0, 15.0, 20.0)
PRIORITY_MODES: Sequence[str] = ("jump", "fcfs", "dynamic")
DYNAMIC_THRESHOLDS: Sequence[float] = (1.0, 2.0, 3.0, 5.0)

EXTRA_METRICS = (
    "arrivals_post_warmup",
    "served_post",
    "balked_post",
    "reneged_post",
    "abandon_rate",
    "served_fraction",
    "revenue_captured_per_hour",
)


def replicate_with_abandonment(
    config,
    reps: int = common.DEFAULT_REPS,
    *,
    seed: int = common.SEED,
    seed_stride: int = common.SEED_STRIDE,
) -> Dict[str, object]:
    """Replicates plus abandonment statistics on a warm-up-consistent denominator.

    ``bubble_tea_sim.stats.replicate`` reports the engine's whole-run abandonment
    counters, which include the warm-up window.  For the behaviour study the
    interesting quantity is the share of *exercised* demand that walks away, so
    the rows are rebuilt here from the simulation result.
    """
    rows: List[Dict[str, float]] = []
    for rep in range(reps):
        result = Simulation(config, seed=seed + rep * seed_stride).run()
        row = flatten_metrics(result.metrics)
        post = [c for c in result.customers if c.arrival >= config.warmup_minutes]
        arrivals = len(post)
        served = sum(1 for customer in post if customer.served)
        balked = sum(1 for customer in post if customer.abandoned == "balk")
        reneged = sum(1 for customer in post if customer.abandoned == "renege")
        row["arrivals_post_warmup"] = float(arrivals)
        row["served_post"] = float(served)
        row["balked_post"] = float(balked)
        row["reneged_post"] = float(reneged)
        row["abandon_rate"] = (balked + reneged) / arrivals if arrivals else 0.0
        row["served_fraction"] = served / arrivals if arrivals else 0.0
        hours = config.sim_minutes / 60.0
        revenue = sum(
            config.economics.price_for(customer.kind) for customer in post if customer.served
        )
        row["revenue_captured_per_hour"] = revenue / hours
        rows.append(row)

    means = {key: stats.mean([row[key] for row in rows]) for key in sorted(rows[0])}
    half_widths = {key: stats.ci95([row[key] for row in rows]) for key in sorted(rows[0])}
    return {"means": means, "ci95": half_widths, "per_rep": rows}


def summary_cell(summary: Dict[str, object]) -> Dict[str, object]:
    return {
        "means": summary["means"],
        "ci95": {
            key: summary["ci95"][key]
            for key in common.KEY_METRICS + EXTRA_METRICS
            if key in summary["ci95"]
        },
    }


def make_config(
    lam: float,
    *,
    split_mix: bool,
    balk: Optional[float] = None,
    renege: Optional[float] = None,
    mode: str = "jump",
    dynamic_threshold: Optional[float] = None,
):
    label_bits = []
    if balk is not None:
        label_bits.append(f"balk{balk:g}")
    if renege is not None:
        label_bits.append(f"renege{renege:g}")
    if split_mix and mode != "jump":
        label_bits.append(f"mixice-{mode}{dynamic_threshold:g}" if dynamic_threshold else f"mixice-{mode}")
    return scenarios.study(
        lam,
        workers=WORKERS,
        split_mix=split_mix,
        fast_priority=False,
        balk_threshold=balk,
        renege_threshold=renege,
        dynamic_priority_threshold=dynamic_threshold,
        mix_ice_priority=mode,
        name="behaviour-lam%g-%s" % (lam, "+".join(label_bits) or "baseline"),
    )


def run(*, reps: int = common.DEFAULT_REPS) -> Dict[str, object]:
    balking: List[Dict[str, object]] = []
    reneging: List[Dict[str, object]] = []
    priority: List[Dict[str, object]] = []
    reference: List[Dict[str, object]] = []

    for lam in LAMBDAS:
        print(f"lambda={lam:g}", flush=True)
        # -- reference points -------------------------------------------------
        for split_mix, label in ((False, "Synchro + FCFS"), (True, "Split + FCFS")):
            config = make_config(lam, split_mix=split_mix)
            summary = replicate_with_abandonment(config, reps=reps)
            reference.append(
                {
                    "lambda": lam,
                    "policy_label": label,
                    "policy_key": common.policy_key(split_mix, False),
                    "config": config.describe(),
                    "reps": reps,
                    **summary_cell(summary),
                }
            )

        # -- balking ----------------------------------------------------------
        for threshold in BALK_THRESHOLDS:
            config = make_config(lam, split_mix=False, balk=threshold)
            summary = replicate_with_abandonment(config, reps=reps)
            balking.append(
                {
                    "lambda": lam,
                    "threshold": threshold,
                    "threshold_label": "off" if threshold is None else f"{threshold:g} min",
                    "config": config.describe(),
                    "reps": reps,
                    **summary_cell(summary),
                }
            )
            means = summary["means"]
            print(
                f"  balk>={threshold}: served={means['served_post']:.1f} "
                f"abandon={means['abandon_rate']:.3f} los={means['mean_los']:.2f} "
                f"profit/h={means['profit_per_hour']:.1f}",
                flush=True,
            )

        # -- reneging ---------------------------------------------------------
        for threshold in RENEGE_THRESHOLDS:
            config = make_config(lam, split_mix=False, renege=threshold)
            summary = replicate_with_abandonment(config, reps=reps)
            reneging.append(
                {
                    "lambda": lam,
                    "threshold": threshold,
                    "threshold_label": "off" if threshold is None else f"{threshold:g} min",
                    "config": config.describe(),
                    "reps": reps,
                    **summary_cell(summary),
                }
            )
            means = summary["means"]
            print(
                f"  renege>={threshold}: served={means['served_post']:.1f} "
                f"abandon={means['abandon_rate']:.3f} los={means['mean_los']:.2f} "
                f"profit/h={means['profit_per_hour']:.1f}",
                flush=True,
            )

        # -- dynamic ice-cream priority --------------------------------------
        summaries: Dict[str, Dict[str, object]] = {}
        for mode in PRIORITY_MODES:
            thresholds = DYNAMIC_THRESHOLDS if mode == "dynamic" else (None,)
            for threshold in thresholds:
                config = make_config(
                    lam,
                    split_mix=True,
                    mode=mode,
                    dynamic_threshold=threshold if mode == "dynamic" else None,
                )
                summary = replicate_with_abandonment(config, reps=reps)
                key = mode if threshold is None else f"dynamic-{threshold:g}"
                summaries[key] = summary
                priority.append(
                    {
                        "lambda": lam,
                        "mode": mode,
                        "dynamic_threshold": threshold,
                        "mode_label": (
                            "Ice jumps immediately"
                            if mode == "jump"
                            else "Ice never jumps (FCFS)"
                            if mode == "fcfs"
                            else f"Ice jumps after {threshold:g} min"
                        ),
                        "config": config.describe(),
                        "reps": reps,
                        **summary_cell(summary),
                    }
                )
                means = summary["means"]
                print(
                    f"  mix-ice {key}: mix_los={means['mix_los']:.2f} "
                    f"ice_hand={means['mix_ice_hand']:.2f} los={means['mean_los']:.2f} "
                    f"profit/h={means['profit_per_hour']:.1f}",
                    flush=True,
                )

        # Paired differences against the "jump" policy (same seeds).
        baseline = summaries["jump"]
        for entry in [row for row in priority if row["lambda"] == lam]:
            key = entry["mode"] if entry["dynamic_threshold"] is None else (
                f"dynamic-{entry['dynamic_threshold']:g}"
            )
            diffs, half_widths = common.paired_from_rows(
                summaries[key]["per_rep"],
                baseline["per_rep"],
            )
            entry["delta_vs_jump"] = {
                "label": "this policy - ice jumps immediately",
                "diff": diffs,
                "ci95": half_widths,
            }

    return {
        "meta": common.meta(
            "behaviour",
            extra={
                "lambdas": list(LAMBDAS),
                "workers": WORKERS,
                "reps": reps,
                "balk_thresholds": list(BALK_THRESHOLDS),
                "renege_thresholds": list(RENEGE_THRESHOLDS),
                "priority_modes": list(PRIORITY_MODES),
                "dynamic_thresholds": list(DYNAMIC_THRESHOLDS),
                "balking_policy": "Synchro + FCFS",
                "reneging_policy": "Synchro + FCFS",
                "priority_policy": "Split + FCFS (the policy choice only matters when mixed orders are split)",
                "balk_rule": "leave at arrival when in_system * p_bar / workers exceeds the threshold",
                "renege_rule": "leave when service has not started within the threshold",
                "denominator_note": (
                    "served/abandon statistics are restricted to arrivals after the "
                    "60-minute warm-up, matching mean_los; the engine's raw counters "
                    "cover the whole run"
                ),
            },
        ),
        "reference": reference,
        "balking": balking,
        "reneging": reneging,
        "priority": priority,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=common.DEFAULT_REPS)
    parser.add_argument("--out", default="behaviour.json")
    args = parser.parse_args(argv)
    payload = run(reps=args.reps)
    common.write_json(args.out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
