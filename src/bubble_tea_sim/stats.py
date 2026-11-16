"""Statistics helpers: replicates, confidence intervals and paired comparisons.

All studies use *common random numbers*: the same seed is reused across the
policies being compared, so policy differences are paired and much less noisy
than independent runs. ``replicate`` returns per-replicate metrics, while
``paired_diff`` returns the paired difference with a 95% confidence interval.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from .engine import Metrics, Simulation, SimulationResult
from .params import SimConfig

Z_95 = 1.959963984540054


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def ci95(values: Sequence[float]) -> float:
    """Half-width of the 95% confidence interval for the mean."""
    if len(values) < 2:
        return 0.0
    return Z_95 * stdev(values) / math.sqrt(len(values))


def flatten_metrics(metrics: Metrics) -> Dict[str, float]:
    """Turn a :class:`Metrics` object into a flat ``{name: number}`` dict."""
    flat: Dict[str, float] = {
        "served": float(metrics.served),
        "mean_los": metrics.mean_los,
        "mix_los": metrics.mix_los,
        "mix_ice_hand": metrics.mix_ice_hand,
        "util": metrics.util,
        "busy_minutes": metrics.busy_minutes,
        "flow_time_total": metrics.flow_time_total,
        "revenue_total": metrics.revenue_total,
        "revenue_per_hour": metrics.revenue_per_hour,
        "wage_per_hour": metrics.wage_per_hour,
        "waiting_cost_total": metrics.waiting_cost_total,
        "profit_per_hour": metrics.profit_per_hour,
        "balked": float(metrics.balked),
        "reneged": float(metrics.reneged),
        "stranded": float(metrics.stranded),
        "los_p50": metrics.los_p50,
        "los_p90": metrics.los_p90,
        "los_p95": metrics.los_p95,
        "sla_attainment": metrics.sla_attainment or 0.0,
        "sla_compensation_total": metrics.sla_compensation_total,
        "stockout_losses": float(metrics.stockout_losses),
        "waste_units": metrics.waste_units,
        "purchase_cost": metrics.purchase_cost,
        "ingredient_cost_per_hour": metrics.ingredient_cost_per_hour,
        "starvation_events": float(metrics.starvation_events),
        "fairness_gap": metrics.fairness_gap or 0.0,
        "mean_price_factor": metrics.mean_price_factor,
        "staff_minutes_available": metrics.staff_minutes_available,
    }
    if metrics.fill_rate is not None:
        flat["fill_rate"] = metrics.fill_rate
    for name, values in metrics.by_class.items():
        flat[f"class_{name}_mean_los"] = values.get("mean_los", 0.0)
        flat[f"class_{name}_p95_los"] = values.get("p95_los", 0.0)
        flat[f"class_{name}_served"] = values.get("served", 0.0)
    for name, value in metrics.station_util.items():
        flat[f"station_{name}_util"] = value
    for kind, value in metrics.los_by_kind.items():
        flat[f"los_{kind}"] = value
    for kind, value in metrics.counts.items():
        flat[f"count_{kind}"] = float(value)
    return flat


@dataclass
class ReplicateSummary:
    """Aggregated metrics over several replicates of the same configuration."""

    config: SimConfig
    reps: int
    means: Dict[str, float] = field(default_factory=dict)
    ci95: Dict[str, float] = field(default_factory=dict)
    per_rep: List[Dict[str, float]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "config": self.config.describe(),
            "reps": self.reps,
            "means": dict(self.means),
            "ci95": dict(self.ci95),
        }


def replicate(
    config: SimConfig,
    reps: int = 100,
    *,
    seed: int = 0,
    seed_stride: int = 1,
) -> ReplicateSummary:
    """Run ``reps`` replicates and aggregate the metrics.

    Seeds are ``seed + i * seed_stride``. The original course scripts used
    ``stride=9001`` (mixed order) and ``stride=7001`` (bread priority).
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    rows: List[Dict[str, float]] = []
    for rep in range(reps):
        run_seed = seed + rep * seed_stride
        result: SimulationResult = Simulation(config, seed=run_seed).run()
        rows.append(flatten_metrics(result.metrics))
    keys = sorted(rows[0].keys())
    summary = ReplicateSummary(config=config, reps=reps, per_rep=rows)
    for key in keys:
        values = [row[key] for row in rows]
        summary.means[key] = mean(values)
        summary.ci95[key] = ci95(values)
    return summary


@dataclass
class PairedComparison:
    """Paired difference ``a - b`` with a 95% confidence interval."""

    config_a: SimConfig
    config_b: SimConfig
    reps: int
    diffs: Dict[str, float] = field(default_factory=dict)
    ci95: Dict[str, float] = field(default_factory=dict)
    per_rep: List[Dict[str, float]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "config_a": self.config_a.describe(),
            "config_b": self.config_b.describe(),
            "reps": self.reps,
            "diff": dict(self.diffs),
            "ci95": dict(self.ci95),
        }


def paired_diff(
    config_a: SimConfig,
    config_b: SimConfig,
    reps: int = 100,
    *,
    seed: int = 0,
    seed_stride: int = 1,
) -> PairedComparison:
    """Compare two configurations on common random numbers (``a - b``)."""
    comparison = PairedComparison(config_a=config_a, config_b=config_b, reps=reps)
    rows: List[Dict[str, float]] = []
    for rep in range(reps):
        run_seed = seed + rep * seed_stride
        a = flatten_metrics(Simulation(config_a, seed=run_seed).run().metrics)
        b = flatten_metrics(Simulation(config_b, seed=run_seed).run().metrics)
        rows.append({key: a[key] - b[key] for key in a})
    comparison.per_rep = rows
    for key in sorted(rows[0].keys()):
        values = [row[key] for row in rows]
        comparison.diffs[key] = mean(values)
        comparison.ci95[key] = ci95(values)
    return comparison


def pooled_los(
    config: SimConfig,
    reps: int = 100,
    *,
    seed: int = 0,
    seed_stride: int = 1,
) -> Dict[str, float]:
    """Pool every served customer across replicates and average by order class.

    The original ``bread_priority_sim.py`` averaged a pooled customer list, while
    ``mixed_order_sim.py`` averaged per-replicate means. Both estimators are
    legitimate; this helper exists so the regression tests can pin either one.
    """
    buckets: Dict[str, List[float]] = {}
    for rep in range(reps):
        result = Simulation(config, seed=seed + rep * seed_stride).run()
        for customer in result.customers:
            if not customer.served or customer.arrival < config.warmup_minutes:
                continue
            buckets.setdefault(customer.kind, []).append(
                customer.departure - customer.arrival
            )
    pooled = {kind: mean(values) for kind, values in buckets.items()}
    pooled["all"] = mean([value for values in buckets.values() for value in values])
    return pooled


def pooled_summary(
    config: SimConfig,
    reps: int = 100,
    *,
    seed: int = 0,
    seed_stride: int = 1,
) -> Dict[str, object]:
    """Pooled LOS plus replicate-averaged utilisation and abandonment counts."""
    summary = replicate(config, reps=reps, seed=seed, seed_stride=seed_stride)
    return {
        "config": config.describe(),
        "reps": reps,
        "los": pooled_los(config, reps=reps, seed=seed, seed_stride=seed_stride),
        "util": summary.means["util"],
        "served": summary.means["served"],
        "balked": summary.means["balked"],
        "reneged": summary.means["reneged"],
    }


def sweeps(
    configs: Iterable[SimConfig],
    reps: int = 100,
    *,
    seed: int = 0,
    seed_stride: int = 1,
) -> List[ReplicateSummary]:
    """Replicate every configuration independently (same seeds for all)."""
    return [
        replicate(config, reps=reps, seed=seed, seed_stride=seed_stride)
        for config in configs
    ]


def breakeven_lambda(
    make_config: Callable[[float], SimConfig],
    *,
    lower: float = 0.5,
    upper: float = 1.3,
    reps: int = 60,
    seed: int = 0,
    seed_stride: int = 1,
    metric: str = "profit_per_hour",
    tolerance: float = 0.01,
    max_iterations: int = 40,
) -> Dict[str, float]:
    """Find the arrival rate where two policies break even.

    ``make_config`` must return ``(config_split, config_synchro)``... instead it
    returns a tuple of the two configurations for a given arrival rate. The
    search assumes the sign of ``metric(split) - metric(synchro)`` is monotone
    over ``[lower, upper]``, which holds for the queueing experiments here.
    """

    def difference(lam: float) -> float:
        configs = make_config(lam)
        if not isinstance(configs, tuple) or len(configs) != 2:
            raise TypeError("make_config must return a (config_a, config_b) tuple")
        config_a, config_b = configs
        comparison = paired_diff(
            config_a, config_b, reps=reps, seed=seed, seed_stride=seed_stride
        )
        return comparison.diffs[metric]

    low_value = difference(lower)
    high_value = difference(upper)
    result: Dict[str, float] = {
        "metric": metric,
        "lower_lambda": lower,
        "lower_difference": low_value,
        "upper_lambda": upper,
        "upper_difference": high_value,
    }
    if low_value == 0.0:
        result["lambda"] = lower
        return result
    if high_value == 0.0:
        result["lambda"] = upper
        return result
    if (low_value > 0) == (high_value > 0):
        result["lambda"] = float("nan")
        result["note"] = "no sign change over the bracketing interval"
        return result
    lower_value, upper_value = low_value, high_value
    mid = 0.5 * (lower + upper)
    for _ in range(max_iterations):
        mid = 0.5 * (lower + upper)
        if upper - lower < tolerance:
            break
        mid_value = difference(mid)
        if (mid_value > 0) == (lower_value > 0):
            lower, lower_value = mid, mid_value
        else:
            upper, upper_value = mid, mid_value
    result["lambda"] = mid
    return result
