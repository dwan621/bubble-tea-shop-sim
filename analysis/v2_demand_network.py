"""v2 Layer 1 (demand) and Layer 2 (supply network) experiments.

This script produces three files in ``results/v2/``:

* ``scenario_library.json`` - every scenario in ``data/scenarios/`` with its
  provenance, the configuration the loader built, and 100-replicate means and
  confidence intervals for the core metrics;
* ``demand_study.json`` - peak-vs-flat, peak-shape, service-variability,
  patience and batch-arrival experiments (Layer 1);
* ``network_study.json`` - tea-station capacity and bottleneck migration,
  strategy x bottleneck paired comparisons, the skill matrix and shift/break
  staffing experiments (Layer 2).

Every number is produced by re-running the engine from ``data/scenarios/`` and
the dataclass overrides in this file; nothing is typed in by hand. All runs use
common seeds (first replicate 0, stride 1) so paired comparisons on common
random numbers are valid wherever the arrival stream is unchanged.

Usage
-----
    python analysis/v2_demand_network.py                # all three stages
    python analysis/v2_demand_network.py --stage demand  # one stage
    python analysis/v2_demand_network.py --reps 20       # quick smoke test

Flow conservation (``served + balked + reneged + stockout + stranded ==
arrivals``) and finiteness are asserted for every single replicate, so a broken
configuration fails the run instead of leaking a number into the report.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _candidate in (ROOT / "src", ROOT / "analysis"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import v2_common  # noqa: E402  (path bootstrap above)
from bubble_tea_sim import data_spec as ds, library, stats  # noqa: E402
from bubble_tea_sim.engine import Simulation  # noqa: E402
from bubble_tea_sim.params import SimConfig  # noqa: E402

REPS = 100
OVERLOAD_REPS = 60
SEED = 0
SEED_STRIDE = 1

#: Metrics whose confidence interval is kept in the scenario library file.
CORE_METRICS = (
    "arrivals",
    "served",
    "util",
    "mean_los",
    "los_p50",
    "los_p90",
    "los_p95",
    "balk_rate",
    "renege_rate",
    "stockout_rate",
    "abandon_rate",
    "revenue_per_hour",
    "profit_per_hour",
    "wage_per_hour",
    "peak_busy_ratio",
    "mean_busy_ratio",
    "peak_hour_los",
    "mix_los",
    "fill_rate",
    "waste_units",
    "sla_attainment",
    "fairness_gap",
)

#: Demand profile used to force the v2 event-driven dispatch path while keeping
#: a perfectly flat arrival intensity. The legacy path is only taken when every
#: v2 layer is off, so a two-segment unit profile is the smallest honest trick
#: that makes fixed / exponential / lognormal service-time cells comparable on
#: exactly the same arrival stream.
FLAT_PROFILE = ds.DemandProfile(
    segments=(ds.DemandSegment(0.0, 1.0), ds.DemandSegment(240.0, 1.0))
)


# ---------------------------------------------------------------------------
# Generic harness
# ---------------------------------------------------------------------------
def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _round(value: float, digits: int = 6) -> float:
    if value is None:
        return value  # type: ignore[return-value]
    return round(float(value), digits)


def _rate_multiplier(config: SimConfig, minute: float) -> float:
    multiplier = config.demand.multiplier_at(minute)
    if config.pricing is not None:
        multiplier *= config.pricing.demand_multiplier_at(minute)
    return multiplier


def expected_batch_size(config: SimConfig) -> float:
    batches = config.batches
    weighted = sum(size * weight for size, weight in batches.sizes)
    return (1.0 - batches.probability) + batches.probability * weighted


def estimated_peak_load(config: SimConfig) -> float:
    """Rough peak-hour load used only to decide 100 vs 60 replicates."""
    candidates = [0.0] + [segment.start_minute for segment in config.demand.segments]
    if config.pricing is not None:
        candidates += [start for start, _end in config.pricing.peak_windows]
    peak_multiplier = max(_rate_multiplier(config, minute) for minute in candidates)
    peak_rate = config.arrival_rate * peak_multiplier * expected_batch_size(config)
    if config.network is None or not config.network.stations:
        return peak_rate * config.mean_service_time() / max(1, config.workers)

    mix = config.mix.as_dict()
    times = config.times
    component_work = {
        "order": times.order,
        "tea": mix["tea"] * times.tea + mix["mix"] * times.tea,
        "bread": mix["bread"] * times.bread,
        "ice": mix["ice"] * times.ice + mix["mix"] * times.ice,
    }
    routes = config.network.route_map()
    loads: List[float] = []
    for station in config.network.stations:
        station_work = sum(
            work for component, work in component_work.items()
            if routes.get(component, component) == station.name
        )
        loads.append(peak_rate * station_work / max(1, station.capacity))
    staff_units = (
        sum(config.network.staff.counts) if config.network.staff is not None else config.workers
    )
    loads.append(peak_rate * config.mean_service_time() / max(1, staff_units))
    return max(loads)


def reps_for(config: SimConfig) -> int:
    return OVERLOAD_REPS if estimated_peak_load(config) > 0.95 else REPS


def pool_work_per_customer(config: SimConfig) -> Dict[str, float]:
    """Clerk-minutes per customer split by station skill (flat-mix approximation)."""
    mix = config.mix.as_dict()
    times = config.times
    return {
        "barista": (
            mix["tea"] * times.tea
            + mix["mix"] * (times.tea + times.ice)
            + mix["ice"] * times.ice
        ),
        "cashier": times.order + mix["bread"] * times.bread,
    }


def theoretical_pool_load(config: SimConfig) -> Dict[str, float]:
    """Steady-state load of every labour pool at the quoted rate (no peaks)."""
    if config.network is None or config.network.staff is None:
        return {}
    work = pool_work_per_customer(config)
    staff = config.network.staff
    counts: Dict[str, int] = {}
    for _role, count, skills in zip(staff.roles, staff.counts, staff.skills):
        for skill in work:
            if "all" in skills or skill in skills:
                counts[skill] = counts.get(skill, 0) + count
    return {
        skill: config.arrival_rate * amount / max(1, counts.get(skill, 0))
        for skill, amount in work.items()
    }


def common_reps(configs: Sequence[SimConfig]) -> int:
    """One replicate count for a family of cells that will be plotted together."""
    return min(reps_for(config) for config in configs)


def pool_utilisation(config: SimConfig, metrics) -> Dict[str, float]:
    """Utilisation of each *labour pool* (staff that share a station skill).

    Station utilisation is reported per station; this helper aggregates the
    stations that the same skill can operate so the study can show when the
    binding resource stops being a station and becomes the people who run it.
    Availability uses pre-break shift windows, so pool utilisation is a lower
    bound when breaks exist.
    """
    if config.network is None or config.network.staff is None:
        return {}
    skills = sorted({station.skill for station in config.network.stations if station.skill})
    staff = config.network.staff
    result: Dict[str, float] = {}
    for skill in skills:
        stations = [station for station in config.network.stations if station.skill == skill]
        busy = sum(
            metrics.station_util.get(station.name, 0.0) * station.capacity * config.sim_minutes
            for station in stations
        )
        available = 0.0
        for role, count, role_skills in zip(staff.roles, staff.counts, staff.skills):
            if not ("all" in role_skills or skill in role_skills):
                continue
            windows = [window for window in staff.windows if window.role == role]
            if windows:
                available += sum(window.end_minute - window.start_minute for window in windows)
            else:
                available += count * config.sim_minutes
        result[skill] = busy / available if available > 0 else 0.0
    return result


def _flatten_with_extras(config: SimConfig, result) -> Dict[str, float]:
    metrics = result.metrics
    flat = stats.flatten_metrics(metrics)
    arrivals = len(result.customers)
    served_all = sum(1 for customer in result.customers if customer.served)
    accounted = (
        served_all + metrics.balked + metrics.reneged
        + metrics.stockout_losses + metrics.stranded
    )
    if accounted != arrivals:
        raise AssertionError(
            f"flow conservation broken for {config.name!r}: {accounted} != {arrivals}"
        )
    if metrics.balked + metrics.reneged + metrics.stockout_losses + metrics.stranded > arrivals:
        raise AssertionError(f"abandonment exceeds arrivals for {config.name!r}")

    flat["arrivals"] = float(arrivals)
    flat["served_all"] = float(served_all)
    flat["served_rate"] = served_all / arrivals if arrivals else 0.0
    flat["balk_rate"] = metrics.balked / arrivals if arrivals else 0.0
    flat["renege_rate"] = metrics.reneged / arrivals if arrivals else 0.0
    flat["stockout_rate"] = metrics.stockout_losses / arrivals if arrivals else 0.0
    flat["abandon_rate"] = (
        (metrics.balked + metrics.reneged + metrics.stockout_losses) / arrivals
        if arrivals else 0.0
    )

    warmup = config.warmup_minutes
    measured = [row for row in metrics.hourly if row["hour_start"] >= warmup]
    flat["peak_busy_ratio"] = max((row["busy_ratio"] for row in measured), default=0.0)
    flat["mean_busy_ratio"] = _mean([row["busy_ratio"] for row in measured])
    flat["peak_hour_arrivals"] = max((row["arrivals"] for row in measured), default=0.0)
    los_rows = [row for row in measured if row["served"] > 0]
    flat["peak_hour_los"] = max((row["mean_los"] for row in los_rows), default=0.0)

    if metrics.station_util:
        flat["top_station_util"] = max(metrics.station_util.values())
    for skill, value in pool_utilisation(config, metrics).items():
        flat[f"pool_{skill}_util"] = value

    for key, value in flat.items():
        if not math.isfinite(value):
            raise AssertionError(f"non-finite metric {key}={value} for {config.name!r}")
    return flat


def run_cell(
    config: SimConfig,
    reps: Optional[int] = None,
    *,
    label: str = "cell",
    keep_rows: bool = False,
    keep_hourly: bool = False,
) -> Dict[str, object]:
    """Run one configuration ``reps`` times and summarise means + 95% CI."""
    reps = reps if reps is not None else reps_for(config)
    if reps < 2:
        raise ValueError("reps must be at least 2 for confidence intervals")
    rows: List[Dict[str, float]] = []
    hourly_reps: List[List[Dict[str, float]]] = []
    last_metrics = None
    started = time.perf_counter()
    for index in range(reps):
        run_seed = SEED + index * SEED_STRIDE
        result = Simulation(config, seed=run_seed).run()
        last_metrics = result.metrics
        rows.append(_flatten_with_extras(config, result))
        if keep_hourly:
            hourly_reps.append([dict(row) for row in result.metrics.hourly])
    elapsed = time.perf_counter() - started

    keys = sorted(rows[0])
    cell: Dict[str, object] = {
        "label": label,
        "reps": reps,
        "seed": SEED,
        "seed_stride": SEED_STRIDE,
        "elapsed_seconds": round(elapsed, 2),
        "config": config.describe(),
        "means": {key: _round(_mean([row[key] for row in rows])) for key in keys},
        "ci95": {key: _round(stats.ci95([row[key] for row in rows])) for key in keys},
    }
    station_means = {
        name: cell["means"][f"station_{name}_util"]  # type: ignore[index]
        for name in sorted(
            config.network.station_map() if config.network is not None else {}
        )
        if config.network is not None and f"station_{name}_util" in rows[0]
    }
    if station_means:
        cell["station_util"] = {name: _round(value) for name, value in station_means.items()}
        cell["top_station"] = max(station_means, key=station_means.get)
        assert last_metrics is not None
        cell["pool_util"] = {
            skill: cell["means"][f"pool_{skill}_util"]  # type: ignore[index]
            for skill in sorted(pool_utilisation(config, last_metrics))
        }
        cell["tea_util"] = station_means.get("tea")
        cell["ice_util"] = station_means.get("ice")
        cell["order_util"] = station_means.get("order")
        cell["bread_util"] = station_means.get("bread")
    if config.network is not None and config.network.staff is not None:
        cell["staff"] = describe_staff(config.network)
    if keep_hourly:
        cell["hourly"] = aggregate_hourly(hourly_reps, config.warmup_minutes)
    if keep_rows:
        cell["rows"] = rows
    return cell


def aggregate_hourly(
    hourly_reps: Sequence[Sequence[Dict[str, float]]], warmup_minutes: float
) -> List[Dict[str, object]]:
    if not hourly_reps:
        return []
    rows: List[Dict[str, object]] = []
    for index in range(len(hourly_reps[0])):
        bucket = [rep[index] for rep in hourly_reps]
        included = bool(bucket[0]["hour_start"] >= warmup_minutes)
        los_values = [row["mean_los"] for row in bucket if row["served"] > 0]
        rows.append(
            {
                "hour_start": bucket[0]["hour_start"],
                "included": included,
                "arrivals": _round(_mean([row["arrivals"] for row in bucket]), 4),
                "served": _round(_mean([row["served"] for row in bucket]), 4),
                "busy_minutes": _round(_mean([row["busy_minutes"] for row in bucket]), 4),
                "busy_ratio": _round(_mean([row["busy_ratio"] for row in bucket]), 4),
                "mean_los": _round(_mean(los_values), 4) if included and los_values else None,
            }
        )
    return rows


def paired_rows(rows_a: Sequence[Dict[str, float]], rows_b: Sequence[Dict[str, float]]) -> Dict[str, object]:
    """Paired difference ``a - b`` over common seeds, with 95% CI."""
    count = min(len(rows_a), len(rows_b))
    keys = sorted(set(rows_a[0]) & set(rows_b[0]))
    diffs = {
        key: [rows_a[index][key] - rows_b[index][key] for index in range(count)]
        for key in keys
    }
    return {
        "reps": count,
        "diff": {key: _round(_mean(values)) for key, values in diffs.items()},
        "ci95": {key: _round(stats.ci95(values)) for key, values in diffs.items()},
    }


def paired_cell(cell_a: Dict[str, object], cell_b: Dict[str, object]) -> Dict[str, object]:
    return paired_rows(cell_a["rows"], cell_b["rows"])  # type: ignore[arg-type]


def public(cell: Dict[str, object]) -> Dict[str, object]:
    """Cell without the internal per-replicate rows."""
    return {key: value for key, value in cell.items() if key != "rows"}


def _delta_table(
    name: str,
    cell_a: Dict[str, object],
    cell_b: Dict[str, object],
    *,
    metrics: Iterable[str],
    note: str = "",
) -> Dict[str, object]:
    paired = paired_cell(cell_a, cell_b)
    return {
        "name": name,
        "comparison": f"{cell_a['label']} - {cell_b['label']}",
        "reps": paired["reps"],
        "metrics": {
            metric: {
                "diff": paired["diff"].get(metric),  # type: ignore[union-attr]
                "ci95": paired["ci95"].get(metric),  # type: ignore[union-attr]
            }
            for metric in metrics
            if metric in paired["diff"]  # type: ignore[operator]
        },
        "note": note,
    }


def describe_staff(network) -> Dict[str, object]:
    staff = network.staff
    return {
        "roles": list(staff.roles),
        "counts": list(staff.counts),
        "skills": [list(skill_set) for skill_set in staff.skills],
        "windows": [
            {"role": window.role, "start": window.start_minute, "end": window.end_minute}
            for window in staff.windows
        ],
        "breaks": [
            {"role": role, "start": start, "end": end} for role, start, end in staff.breaks
        ],
    }


def describe_layers(config: SimConfig) -> Dict[str, object]:
    demand = config.demand
    layers: Dict[str, object] = {
        "demand": {
            "segments": [[segment.start_minute, segment.multiplier] for segment in demand.segments],
            "peak_multiplier": demand.peak_multiplier(),
            "daily_mean_multiplier": demand.daily_mean_multiplier(config.sim_minutes),
            "flat": demand.is_flat(),
        },
        "batches": (
            {
                "probability": config.batches.probability,
                "sizes": [[size, weight] for size, weight in config.batches.sizes],
                "expected_arrival_size": expected_batch_size(config),
            }
            if config.batches.probability > 0
            else None
        ),
        "classes": [
            {
                "name": customer_class.name,
                "weight": customer_class.weight,
                "priority": customer_class.priority,
                "delivery": customer_class.delivery,
                "balk_mean": customer_class.patience.balk_mean,
                "renege_mean": customer_class.patience.renege_mean,
                "own_mix": customer_class.mix is not None,
            }
            for customer_class in config.classes.classes
        ],
        "variability": {
            "kind": config.variability.kind,
            "order_cv": config.variability.order_cv,
            "tea_cv": config.variability.tea_cv,
            "bread_cv": config.variability.bread_cv,
            "ice_cv": config.variability.ice_cv,
        },
        "network": (
            {
                "stations": [
                    {"name": station.name, "capacity": station.capacity, "skill": station.skill}
                    for station in config.network.stations
                ],
                "staff": describe_staff(config.network) if config.network.staff else None,
                "routes": [[component, station] for component, station in config.network.routes],
            }
            if config.network is not None
            else None
        ),
        "inventory": (
            {
                "stockout_policy": config.inventory.stockout_policy,
                "ingredients": [
                    {
                        "name": ingredient.name,
                        "initial_stock": ingredient.initial_stock,
                        "reorder_point": ingredient.reorder_point,
                        "order_quantity": ingredient.order_quantity,
                        "lead_time_minutes": ingredient.lead_time_minutes,
                        "unit_cost": ingredient.unit_cost,
                        "shelf_life_minutes": ingredient.shelf_life_minutes,
                    }
                    for ingredient in config.inventory.ingredients
                ],
                "recipes": [
                    {"product": recipe.product, "components": [list(pair) for pair in recipe.components]}
                    for recipe in config.inventory.recipes
                ],
            }
            if config.inventory is not None
            else None
        ),
        "pricing": (
            {
                "peak_windows": [list(window) for window in config.pricing.peak_windows],
                "peak_price_multiplier": config.pricing.peak_price_multiplier,
                "elasticity": config.pricing.elasticity,
            }
            if config.pricing is not None
            else None
        ),
        "sla": (
            {
                "target_minutes": config.sla.target_minutes,
                "compensation": config.sla.compensation,
                "fairness_cap_minutes": config.sla.fairness_cap_minutes,
            }
            if config.sla is not None
            else None
        ),
        "policy": {
            "split_mix": config.policy.split_mix,
            "fast_priority": config.policy.fast_priority,
            "starvation_cap": config.policy.starvation_cap,
            "mix_ice_priority": config.policy.mix_ice_priority,
        },
    }
    return layers


# ---------------------------------------------------------------------------
# Stage A: scenario library
# ---------------------------------------------------------------------------
def build_scenario_library() -> Dict[str, object]:
    print("[library] loading every scenario and running 100 replicates each")
    entries: List[Dict[str, object]] = []
    comparison: List[Dict[str, object]] = []
    total_runs = 0
    started = time.perf_counter()
    for name in library.scenario_names():
        raw = library.load_raw(name)
        config = library.load_scenario(name)
        cell = run_cell(config, REPS, label=name)
        total_runs += REPS
        means = cell["means"]  # type: ignore[assignment]
        ci95 = cell["ci95"]  # type: ignore[assignment]
        entry = {
            "name": name,
            "title": raw.get("title", name),
            "provenance": raw.get("provenance", {}),
            "legacy_compat": config.legacy_compat,
            "config": cell["config"],
            "layers": describe_layers(config),
            "reps": REPS,
            "means": means,
            "ci95": {key: ci95[key] for key in ci95 if key in CORE_METRICS or key.startswith("station_")},
            "validation": {"flow_conservation": True, "all_metrics_finite": True, "reps": REPS},
        }
        if "station_util" in cell:
            entry["station_util"] = cell["station_util"]
            entry["top_station"] = cell["top_station"]
            entry["pool_util"] = cell.get("pool_util")
        entries.append(entry)
        comparison.append(
            {
                "name": name,
                "title": entry["title"],
                "legacy_compat": config.legacy_compat,
                "workers": config.workers,
                "quoted_arrival_rate": config.arrival_rate,
                "sim_minutes": config.sim_minutes,
                "peak_multiplier": config.demand.peak_multiplier(),
                "peak_to_mean": (
                    config.demand.peak_multiplier()
                    / config.demand.daily_mean_multiplier(config.sim_minutes)
                ),
                "util": means["util"],  # type: ignore[index]
                "mean_los": means["mean_los"],  # type: ignore[index]
                "los_p95": means["los_p95"],  # type: ignore[index]
                "abandon_rate": means["abandon_rate"],  # type: ignore[index]
                "served": means["served"],  # type: ignore[index]
                "profit_per_hour": means["profit_per_hour"],  # type: ignore[index]
                "top_station": cell.get("top_station"),
                "top_station_util": means.get("top_station_util"),  # type: ignore[union-attr]
            }
        )
        print(
            "  %-26s util=%.3f los_p95=%5.2f abandon=%.3f profit=%7.1f  (%ss)"
            % (
                name,
                means["util"],  # type: ignore[index]
                means["los_p95"],  # type: ignore[index]
                means["abandon_rate"],  # type: ignore[index]
                means["profit_per_hour"],  # type: ignore[index]
                cell["elapsed_seconds"],
            )
        )
    elapsed = time.perf_counter() - started
    print(
        "[library] %d scenarios, %d runs, %.1fs"
        % (len(entries), total_runs, elapsed)
    )
    return {
        "meta": v2_common.meta(
            "scenario_library",
            notes=(
                "One block per scenario in data/scenarios/. Provenance is copied from the "
                "JSON file; config.describe() and the layer description come from the loaded "
                "SimConfig. 100 replicates per scenario, first seed 0, stride 1. Flow "
                "conservation and finiteness are asserted for every replicate, so a scenario "
                "that fails would abort this script instead of appearing here. The balk "
                "decision uses the engine's wait estimate divided by the number of staff "
                "units ON SHIFT at the arrival instant (shift windows and breaks are "
                "coverage-checked), so scenarios with late shift starts, breaks or a "
                "mid-shift joiner are not credited with absent staff; the stationary legacy "
                "path keeps the full worker count so the v1 anchors stay bit-identical. "
                "Note: sla.fairness_cap_minutes in a scenario file is an alias for the "
                "policy starvation cap, so peak_pricing/strict_sla_fairness behave as their "
                "provenance describes."
            ),
            reps=REPS,
            seed=SEED,
            seed_stride=SEED_STRIDE,
            scenario_count=len(entries),
            total_replicates=total_runs,
            elapsed_seconds=round(elapsed, 1),
        ),
        "tables": {"scenarios": entries, "comparison": comparison},
        "series": {
            "demand_profiles": {
                entry["name"]: entry["layers"]["demand"]["segments"]  # type: ignore[index]
                for entry in entries
            },
            "scenario_curve": [
                {
                    "name": row["name"],
                    "util": row["util"],
                    "los_p95": row["los_p95"],
                    "abandon_rate": row["abandon_rate"],
                    "profit_per_hour": row["profit_per_hour"],
                }
                for row in comparison
            ],
        },
    }


# ---------------------------------------------------------------------------
# Stage B: Layer 1 demand experiments
# ---------------------------------------------------------------------------
def build_peak_vs_flat() -> Tuple[Dict[str, object], Dict[str, object]]:
    print("[demand] peak vs flat")
    rush = library.load_scenario("campus_rush")
    daily_mean_rate = rush.arrival_rate * rush.demand.daily_mean_multiplier(rush.sim_minutes)
    peak_cell = run_cell(rush, label="campus_rush_demand_shape", keep_rows=True, keep_hourly=True)
    flat_config = replace(rush, demand=ds.DemandProfile(), arrival_rate=daily_mean_rate)
    flat_cell = run_cell(
        flat_config, label="campus_rush_flat_same_daily_mean", keep_rows=True, keep_hourly=True
    )
    metrics = (
        "util", "mean_busy_ratio", "peak_busy_ratio", "peak_hour_arrivals",
        "peak_hour_los", "mean_los", "los_p50", "los_p90", "los_p95",
        "balk_rate", "renege_rate", "abandon_rate", "served", "arrivals",
        "revenue_per_hour", "profit_per_hour", "wage_per_hour",
    )
    table = [
        {
            "label": "peak_shape",
            "profile": "campus_rush piecewise demand",
            "quoted_daily_mean_rate": daily_mean_rate,
            "effective_arrival_rate": rush.arrival_rate,
            "peak_to_mean": (
                rush.demand.peak_multiplier()
                / rush.demand.daily_mean_multiplier(rush.sim_minutes)
            ),
            "reps": peak_cell["reps"],
            "metrics": {key: peak_cell["means"][key] for key in metrics},  # type: ignore[index]
            "ci95": {key: peak_cell["ci95"][key] for key in metrics},  # type: ignore[index]
            "hourly": peak_cell["hourly"],
        },
        {
            "label": "flat_same_daily_mean",
            "profile": "flat demand at the same daily mean",
            "quoted_daily_mean_rate": daily_mean_rate,
            "effective_arrival_rate": daily_mean_rate,
            "peak_to_mean": 1.0,
            "reps": flat_cell["reps"],
            "metrics": {key: flat_cell["means"][key] for key in metrics},  # type: ignore[index]
            "ci95": {key: flat_cell["ci95"][key] for key in metrics},  # type: ignore[index]
            "hourly": flat_cell["hourly"],
        },
    ]
    delta = _delta_table(
        "peak_shape_minus_flat",
        peak_cell,
        flat_cell,
        metrics=metrics,
        note=(
            "peak shape - flat profile at the same daily mean. The two arrival streams are "
            "not identical event-by-event, so the difference of means is reported with the "
            "95% CI of the paired difference on common seeds; it is a common-random-number "
            "comparison, not an exact coupling."
        ),
    )
    return {
        "table": table,
        "delta": delta,
        "series": {
            "hourly": {
                "peak_shape": peak_cell["hourly"],
                "flat_same_daily_mean": flat_cell["hourly"],
            },
            "daily_mean_rate": daily_mean_rate,
            "peak_multiplier": rush.demand.peak_multiplier(),
        },
    }


def build_peak_factor_scan() -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    print("[demand] peak-factor scan")
    rush = library.load_scenario("campus_rush")
    quoted_rate = rush.arrival_rate * rush.demand.daily_mean_multiplier(rush.sim_minutes)
    segments = [(segment.start_minute, segment.multiplier) for segment in rush.demand.segments]
    factors = (1.0, 1.2, 1.4, 1.6, 1.8, 2.0)
    prepared = []
    for factor in factors:
        scaled = ds.DemandProfile(
            segments=tuple(
                ds.DemandSegment(start, multiplier ** factor) for start, multiplier in segments
            )
        )
        daily_mean = scaled.daily_mean_multiplier(rush.sim_minutes)
        config = replace(rush, demand=scaled, arrival_rate=quoted_rate / daily_mean)
        prepared.append((factor, scaled, daily_mean, config))
    # One replicate count for the whole curve so the plotted points share noise.
    scan_reps = common_reps([entry[3] for entry in prepared])
    rows: List[Dict[str, object]] = []
    cells: List[Dict[str, object]] = []
    for factor, scaled, daily_mean, config in prepared:
        label = f"peak_factor_{factor:g}"
        cell = run_cell(config, scan_reps, label=label, keep_rows=True)
        cells.append(cell)
        rows.append(
            {
                "factor": factor,
                "label": label,
                "peak_multiplier": scaled.peak_multiplier(),
                "daily_mean_multiplier": daily_mean,
                "peak_to_mean": scaled.peak_multiplier() / daily_mean,
                "peak_arrival_rate": config.arrival_rate * scaled.peak_multiplier()
                * expected_batch_size(config),
                "quoted_daily_mean_rate": quoted_rate,
                "reps": cell["reps"],
                "metrics": {
                    key: cell["means"][key]  # type: ignore[index]
                    for key in (
                        "util", "peak_busy_ratio", "mean_busy_ratio", "los_p50", "los_p90",
                        "los_p95", "mean_los", "balk_rate", "abandon_rate", "served",
                        "arrivals", "profit_per_hour", "revenue_per_hour",
                    )
                },
                "ci95": {
                    key: cell["ci95"][key]  # type: ignore[index]
                    for key in ("util", "los_p95", "balk_rate", "served", "profit_per_hour")
                },
            }
        )
    baseline = cells[0]
    deltas = []
    for factor, cell in zip(factors, cells):
        if factor == 1.0:
            continue
        deltas.append(
            _delta_table(
                f"peak_factor_{factor:g}_minus_baseline",
                cell,
                baseline,
                metrics=(
                    "mean_busy_ratio", "peak_busy_ratio", "los_p95", "balk_rate",
                    "util", "served", "profit_per_hour",
                ),
                note=(
                    "peak_factor cell minus the factor=1.0 (campus_rush) cell at the same "
                    "daily mean rate; demand shape is the only difference."
                ),
            )
        )
    series = {
        "curve": [
            {
                "factor": row["factor"],
                "peak_to_mean": row["peak_to_mean"],
                "util": row["metrics"]["util"],  # type: ignore[index]
                "los_p95": row["metrics"]["los_p95"],  # type: ignore[index]
                "balk_rate": row["metrics"]["balk_rate"],  # type: ignore[index]
                "profit_per_hour": row["metrics"]["profit_per_hour"],  # type: ignore[index]
                "served": row["metrics"]["served"],  # type: ignore[index]
            }
            for row in rows
        ],
        "baseline_peak_to_mean": rows[0]["peak_to_mean"],
        "definition": "multiplier_i(f) = multiplier_i ** f, daily mean rescaled back to the quoted rate",
    }
    return rows, {"rows": rows, "deltas": deltas, "series": series}


def build_variability_scan() -> Dict[str, object]:
    print("[demand] service-variability scan")
    base = library.load_scenario("baseline_flat")
    variants = (
        ("fixed", ds.ServiceVariability(kind="fixed"),
         "deterministic make times (v1 assumption)"),
        ("exponential", ds.ServiceVariability(
            kind="exponential", order_cv=1.0, tea_cv=1.0, bread_cv=1.0, ice_cv=1.0),
         "exponential make times; the cell declares CV 1.0, which is the exponential "
         "distribution's own CV. The engine draws an exponential for kind='exponential' "
         "regardless of the declared component CV, so the cell is genuinely exponential."),
        ("lognormal_cv0.25", ds.ServiceVariability(
            kind="lognormal", order_cv=0.25, tea_cv=0.25, bread_cv=0.25, ice_cv=0.25),
         "lognormal, CV 0.25 on every component"),
        ("lognormal_cv0.50", ds.ServiceVariability(
            kind="lognormal", order_cv=0.5, tea_cv=0.5, bread_cv=0.5, ice_cv=0.5),
         "lognormal, CV 0.50 on every component"),
        ("lognormal_cv0.75", ds.ServiceVariability(
            kind="lognormal", order_cv=0.75, tea_cv=0.75, bread_cv=0.75, ice_cv=0.75),
         "lognormal, CV 0.75 on every component"),
    )
    rows: List[Dict[str, object]] = []
    cells_by_lambda: Dict[str, List[Dict[str, object]]] = {}
    for lam in (1.0, 1.2):
        cells: List[Dict[str, object]] = []
        for name, variability, note in variants:
            config = replace(
                base, arrival_rate=lam, demand=FLAT_PROFILE, variability=variability
            )
            label = f"variability_{name}_lam{lam:g}"
            cell = run_cell(config, label=label, keep_rows=True)
            cells.append(cell)
            rows.append(
                {
                    "lambda": lam,
                    "theoretical_rho": config.utilization(),
                    "variant": name,
                    "note": note,
                    "reps": cell["reps"],
                    "metrics": {
                        key: cell["means"][key]  # type: ignore[index]
                        for key in (
                            "util", "mean_los", "los_p50", "los_p90", "los_p95",
                            "served", "profit_per_hour", "revenue_per_hour",
                        )
                    },
                    "ci95": {
                        key: cell["ci95"][key]  # type: ignore[index]
                        for key in ("mean_los", "los_p50", "los_p90", "los_p95", "profit_per_hour")
                    },
                }
            )
        cells_by_lambda[f"lambda_{lam:g}"] = cells
    deltas: List[Dict[str, object]] = []
    for lam in (1.0, 1.2):
        cells = cells_by_lambda[f"lambda_{lam:g}"]
        fixed_cell = cells[0]
        for variant, cell in zip(variants, cells):
            if variant[0] == "fixed":
                continue
            deltas.append(
                _delta_table(
                    f"variability_{variant[0]}_minus_fixed_lam{lam:g}",
                    cell,
                    fixed_cell,
                    metrics=("los_p95", "los_p90", "mean_los", "profit_per_hour", "util"),
                    note="same arrival stream, only the make-time distribution changes",
                )
            )
    series = {
        f"lambda_{lam:g}": [
            {
                "variant": row["variant"],
                "p50": row["metrics"]["los_p50"],  # type: ignore[index]
                "p90": row["metrics"]["los_p90"],  # type: ignore[index]
                "p95": row["metrics"]["los_p95"],  # type: ignore[index]
                "profit_per_hour": row["metrics"]["profit_per_hour"],  # type: ignore[index]
            }
            for row in rows if row["lambda"] == lam
        ]
        for lam in (1.0, 1.2)
    }
    return {"rows": rows, "deltas": deltas, "series": series}


def build_patience_scan() -> Dict[str, object]:
    print("[demand] patience scan (balk x renege)")
    base = library.load_scenario("baseline_flat")
    balk_means = (3.0, 5.0, 8.0, 12.0)
    renege_means = (10.0, 15.0, 20.0)
    rows: List[Dict[str, object]] = []
    for lam in (1.0, 1.2):
        for balk in balk_means:
            for renege in renege_means:
                patience = ds.PatienceSpec(balk_mean=balk, renege_mean=renege)
                customer_class = ds.CustomerClass(
                    name="regular", weight=1.0, patience=patience
                )
                config = replace(
                    base,
                    arrival_rate=lam,
                    demand=FLAT_PROFILE,
                    classes=ds.MixSpec(classes=(customer_class,)),
                )
                label = f"patience_balk{balk:g}_renege{renege:g}_lam{lam:g}"
                cell = run_cell(config, label=label)
                rows.append(
                    {
                        "lambda": lam,
                        "balk_mean": balk,
                        "renege_mean": renege,
                        "reps": cell["reps"],
                        "metrics": {
                            key: cell["means"][key]  # type: ignore[index]
                            for key in (
                                "balk_rate", "renege_rate", "abandon_rate", "served",
                                "mean_los", "los_p95", "profit_per_hour", "revenue_per_hour",
                            )
                        },
                        "ci95": {
                            key: cell["ci95"][key]  # type: ignore[index]
                            for key in ("abandon_rate", "mean_los", "profit_per_hour")
                        },
                    }
                )

    # Reneging only: balking switched off, so the two thresholds can be seen
    # separately (with balking on, reneging almost never binds).
    renege_only: List[Dict[str, object]] = []
    for lam in (1.0, 1.2):
        for renege in renege_means:
            patience = ds.PatienceSpec(balk_mean=None, renege_mean=renege)
            customer_class = ds.CustomerClass(
                name="regular", weight=1.0, patience=patience
            )
            config = replace(
                base,
                arrival_rate=lam,
                demand=FLAT_PROFILE,
                classes=ds.MixSpec(classes=(customer_class,)),
            )
            label = f"renege_only_{renege:g}_lam{lam:g}"
            cell = run_cell(config, label=label)
            renege_only.append(
                {
                    "lambda": lam,
                    "balk_mean": None,
                    "renege_mean": renege,
                    "reps": cell["reps"],
                    "metrics": {
                        key: cell["means"][key]  # type: ignore[index]
                        for key in (
                            "balk_rate", "renege_rate", "abandon_rate", "served",
                            "mean_los", "los_p95", "profit_per_hour",
                        )
                    },
                }
            )
    series = {
        "grid": [
            {
                "lambda": row["lambda"],
                "balk_mean": row["balk_mean"],
                "renege_mean": row["renege_mean"],
                "abandon_rate": row["metrics"]["abandon_rate"],  # type: ignore[index]
                "mean_los": row["metrics"]["mean_los"],  # type: ignore[index]
                "profit_per_hour": row["metrics"]["profit_per_hour"],  # type: ignore[index]
            }
            for row in rows
        ],
        "renege_only": [
            {
                "lambda": row["lambda"],
                "renege_mean": row["renege_mean"],
                "renege_rate": row["metrics"]["renege_rate"],  # type: ignore[index]
                "abandon_rate": row["metrics"]["abandon_rate"],  # type: ignore[index]
                "profit_per_hour": row["metrics"]["profit_per_hour"],  # type: ignore[index]
            }
            for row in renege_only
        ],
    }
    return {"rows": rows, "renege_only": renege_only, "series": series}


def build_batch_scan() -> Dict[str, object]:
    print("[demand] batch-arrival scan")
    rush = library.load_scenario("campus_rush")
    sizes = [(size, weight) for size, weight in rush.batches.sizes]
    probabilities = (0.0, 0.1, 0.2, 0.3)
    prepared = []
    for rate_policy in ("arrival_events_fixed", "customer_mean_fixed"):
        for probability in probabilities:
            config = replace(
                rush, batches=ds.BatchSpec(probability=probability, sizes=tuple(sizes))
            )
            batch_factor = expected_batch_size(config)
            if rate_policy == "customer_mean_fixed":
                config = replace(config, arrival_rate=rush.arrival_rate / batch_factor)
            prepared.append((rate_policy, probability, batch_factor, config))
    # Batch arrivals change the total demand unless the customer mean is fixed, so
    # use one replicate count for the whole family and report the arrival counts.
    batch_reps = common_reps([entry[3] for entry in prepared])
    rows: List[Dict[str, object]] = []
    for rate_policy, probability, batch_factor, config in prepared:
        label = f"batch_{rate_policy}_p{probability:g}"
        cell = run_cell(config, batch_reps, label=label)
        rows.append(
            {
                "rate_policy": rate_policy,
                "batch_probability": probability,
                "expected_arrival_size": batch_factor,
                "quoted_daily_mean_rate": rush.arrival_rate,
                "effective_arrival_rate": config.arrival_rate,
                "reps": cell["reps"],
                "metrics": {
                    key: cell["means"][key]  # type: ignore[index]
                    for key in (
                        "arrivals", "served", "balk_rate", "abandon_rate",
                        "peak_busy_ratio", "peak_hour_arrivals", "peak_hour_los",
                        "mean_los", "los_p95", "profit_per_hour",
                    )
                },
                "ci95": {
                    key: cell["ci95"][key]  # type: ignore[index]
                    for key in ("balk_rate", "los_p95", "peak_hour_los", "profit_per_hour")
                },
            }
        )
    series = {
        policy: [
            {
                "batch_probability": row["batch_probability"],
                "peak_busy_ratio": row["metrics"]["peak_busy_ratio"],  # type: ignore[index]
                "peak_hour_los": row["metrics"]["peak_hour_los"],  # type: ignore[index]
                "balk_rate": row["metrics"]["balk_rate"],  # type: ignore[index]
                "profit_per_hour": row["metrics"]["profit_per_hour"],  # type: ignore[index]
                "arrivals": row["metrics"]["arrivals"],  # type: ignore[index]
            }
            for row in rows if row["rate_policy"] == policy
        ]
        for policy in ("arrival_events_fixed", "customer_mean_fixed")
    }
    return {"rows": rows, "series": series}


def build_demand_study() -> Dict[str, object]:
    started = time.perf_counter()
    peak = build_peak_vs_flat()
    peak_table = peak["table"]
    peak_delta = peak["delta"]
    peak_series = peak["series"]
    factor_rows, factor_extra = build_peak_factor_scan()
    variability = build_variability_scan()
    patience = build_patience_scan()
    batch = build_batch_scan()
    elapsed = time.perf_counter() - started

    peak_metrics = {row["label"]: row["metrics"] for row in peak_table}
    flat_metrics = peak_metrics["flat_same_daily_mean"]
    peak_metrics = peak_metrics["peak_shape"]
    factor_curve = factor_extra["series"]["curve"]
    findings = {
        "peak_vs_flat": {
            "p95_ratio_peak_over_flat": peak_metrics["los_p95"] / flat_metrics["los_p95"],
            "peak_hour_busy_ratio_peak": peak_metrics["peak_busy_ratio"],
            "peak_hour_busy_ratio_flat": flat_metrics["peak_busy_ratio"],
            "daily_util_peak": peak_metrics["util"],
            "daily_util_flat": flat_metrics["util"],
            "balk_rate_peak": peak_metrics["balk_rate"],
            "balk_rate_flat": flat_metrics["balk_rate"],
            "profit_per_hour_peak": peak_metrics["profit_per_hour"],
            "profit_per_hour_flat": flat_metrics["profit_per_hour"],
            "note": (
                "Same daily mean demand. The peak profile raises the peak-hour busy ratio "
                "and the p95 wait while the daily utilisation actually falls, because "
                "abandonment removes work from the system."
            ),
        },
        "peak_factor_scan": {
            "baseline_factor": 1.0,
            "baseline_peak_to_mean": factor_curve[0]["peak_to_mean"],
            "max_factor": 2.0,
            "max_peak_to_mean": factor_curve[-1]["peak_to_mean"],
            "p95_change": factor_curve[-1]["los_p95"] - factor_curve[0]["los_p95"],
            "balk_rate_change": factor_curve[-1]["balk_rate"] - factor_curve[0]["balk_rate"],
            "profit_change": factor_curve[-1]["profit_per_hour"] - factor_curve[0]["profit_per_hour"],
            "served_change": factor_curve[-1]["served"] - factor_curve[0]["served"],
            "note": (
                "Daily mean demand is held fixed; the multiplier shape is raised to "
                "multiplier**factor. J-shaped cost of peakiness: p95, balking and profit "
                "move even though the daily mean is unchanged."
            ),
        },
        "variability": {
            "p95_ratio_cv075_over_fixed_lam1.2": (
                variability["rows"][9]["metrics"]["los_p95"]  # type: ignore[index]
                / variability["rows"][5]["metrics"]["los_p95"]  # type: ignore[index]
            ),
            "p95_range_lam1.0": (
                max(row["metrics"]["los_p95"] for row in variability["rows"] if row["lambda"] == 1.0)  # type: ignore[index]
                - min(row["metrics"]["los_p95"] for row in variability["rows"] if row["lambda"] == 1.0)  # type: ignore[index]
            ),
            "p95_range_lam1.2": (
                max(row["metrics"]["los_p95"] for row in variability["rows"] if row["lambda"] == 1.2)  # type: ignore[index]
                - min(row["metrics"]["los_p95"] for row in variability["rows"] if row["lambda"] == 1.2)  # type: ignore[index]
            ),
            "mean_los_range_lam1.2": (
                max(row["metrics"]["mean_los"] for row in variability["rows"] if row["lambda"] == 1.2)  # type: ignore[index]
                - min(row["metrics"]["mean_los"] for row in variability["rows"] if row["lambda"] == 1.2)  # type: ignore[index]
            ),
            "note": (
                "Make-time variability moves the upper tail much more than the mean: the "
                "p95 ratio at CV 0.75 versus deterministic grows with load while the mean "
                "wait moves only a little."
            ),
        },
        "patience": {
            "abandon_rate_balk3_lam1.2": patience["rows"][12]["metrics"]["abandon_rate"],  # type: ignore[index]
            "abandon_rate_balk12_lam1.2": patience["rows"][21]["metrics"]["abandon_rate"],  # type: ignore[index]
            "reneging_binds_in_grid": any(
                row["metrics"]["renege_rate"] > 0.005  # type: ignore[index]
                for row in patience["rows"]
            ),
            "note": (
                "With arrival-time balking active, reneging almost never binds: the "
                "balk threshold decides who leaves. The balk decision compares the "
                "customer's threshold with the engine's wait estimate divided by the "
                "number of staff units on shift at that instant (these cells have no shift "
                "windows, so that is the worker count). The reneging-only table isolates "
                "reneging by switching balking off."
            ),
        },
        "batch": {
            "balk_rate_p0": batch["rows"][0]["metrics"]["balk_rate"],  # type: ignore[index]
            "balk_rate_p0.3_arrival_events_fixed": batch["rows"][3]["metrics"]["balk_rate"],  # type: ignore[index]
            "balk_rate_p0.3_customer_mean_fixed": batch["rows"][7]["metrics"]["balk_rate"],  # type: ignore[index]
            "profit_p0": batch["rows"][0]["metrics"]["profit_per_hour"],  # type: ignore[index]
            "profit_p0.3_customer_mean_fixed": batch["rows"][7]["metrics"]["profit_per_hour"],  # type: ignore[index]
            "note": (
                "At a fixed arrival-event rate a higher batch probability is mostly a "
                "demand increase; holding the daily customer mean fixed isolates the "
                "burstiness effect, which is smaller but still negative for profit."
            ),
        },
    }
    print("[demand] finished in %.1fs" % elapsed)
    return {
        "meta": v2_common.meta(
            "demand_study",
            notes=(
                "Layer 1 experiments. Scenarios come from data/scenarios/; every other cell "
                "is a dataclass override of campus_rush or baseline_flat. Cells whose "
                "estimated peak load exceeds 0.95 use 60 replicates, the rest use 100 "
                "(first seed 0, stride 1). Paired differences use common random numbers on "
                "identical seeds. Variability and patience cells use a two-segment unit "
                "demand profile so the fixed-service cell also runs on the v2 event-driven "
                "dispatch path (a single flat segment would silently use the legacy path and "
                "confound the comparison). The balk decision compares the customer's "
                "threshold with the engine's wait estimate divided by the number of staff "
                "units ON SHIFT at the arrival instant; these cells have no shift windows, "
                "so it equals the worker count, but the library scenarios with late shift "
                "starts and breaks are not credited with absent staff."
            ),
            reps_default=REPS,
            reps_overload=OVERLOAD_REPS,
            seed=SEED,
            seed_stride=SEED_STRIDE,
            elapsed_seconds=round(elapsed, 1),
        ),
        "tables": {
            "peak_vs_flat": peak_table,
            "peak_vs_flat_paired": peak_delta,
            "peak_factor_scan": factor_rows,
            "peak_factor_deltas": factor_extra["deltas"],
            "variability_scan": variability["rows"],
            "variability_deltas": variability["deltas"],
            "patience_scan": patience["rows"],
            "patience_reneging_only": patience["renege_only"],
            "batch_scan": batch["rows"],
        },
        "series": {
            "peak_vs_flat_hourly": peak_series["hourly"],
            "peak_factor": factor_extra["series"],
            "variability": variability["series"],
            "patience": patience["series"],
            "batch": batch["series"],
        },
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Stage C: Layer 2 network experiments
# ---------------------------------------------------------------------------
def tea_capacity_config(base: SimConfig, tea_capacity: int, baristas: int, cashiers: int = 2) -> SimConfig:
    """Same shop as ``base`` but with ``tea_capacity`` tea slots / baristas."""
    network = base.network
    assert network is not None and network.staff is not None
    stations = tuple(
        ds.StationSpec(name="tea", capacity=tea_capacity, skill="barista")
        if station.name == "tea"
        else station
        for station in network.stations
    )
    windows = tuple(
        ds.ShiftWindow(role=role, start_minute=0.0, end_minute=base.sim_minutes)
        for role, count in (("cashier", cashiers), ("barista", baristas))
        for _ in range(count)
    )
    staff = ds.StaffSpec(
        roles=("cashier", "barista"),
        counts=(cashiers, baristas),
        skills=(("cashier",), ("barista",)),
        windows=windows,
    )
    return replace(
        base,
        workers=cashiers + baristas,
        network=ds.NetworkSpec(stations=stations, staff=staff, routes=network.routes),
    )


def build_tea_capacity_sweep() -> Dict[str, object]:
    print("[network] tea station capacity sweep")
    base = library.load_scenario("network_tea_bottleneck")
    capacities = (1, 2, 3, 4)
    lambdas = (0.6, 0.9, 1.2)
    rows: List[Dict[str, object]] = []
    cells: Dict[Tuple[float, int], Dict[str, object]] = {}
    for lam in lambdas:
        for capacity in capacities:
            config = tea_capacity_config(replace(base, arrival_rate=lam), capacity, capacity)
            label = f"tea_cap{capacity}_baristas{capacity}_lam{lam:g}"
            cell = run_cell(config, label=label, keep_rows=True)
            cells[(lam, capacity)] = cell
            rows.append(
                {
                    "lambda": lam,
                    "tea_capacity": capacity,
                    "baristas": capacity,
                    "reps": cell["reps"],
                    "theoretical_barista_load": config.utilization(),
                    "theoretical_pool_load": theoretical_pool_load(config),
                    "station_util": cell.get("station_util"),
                    "pool_util": cell.get("pool_util"),
                    "top_station": cell.get("top_station"),
                    "tea_util": cell.get("tea_util"),
                    "order_util": cell.get("order_util"),
                    "ice_util": cell.get("ice_util"),
                    "metrics": {
                        key: cell["means"][key]  # type: ignore[index]
                        for key in (
                            "util", "mean_los", "los_p50", "los_p95", "peak_hour_los",
                            "balk_rate", "renege_rate", "abandon_rate", "served",
                            "profit_per_hour", "wage_per_hour", "staff_minutes_available",
                        )
                    },
                    "ci95": {
                        key: cell["ci95"][key]  # type: ignore[index]
                        for key in ("mean_los", "los_p95", "balk_rate", "profit_per_hour")
                    },
                }
            )
    marginals: List[Dict[str, object]] = []
    migration: Dict[str, object] = {}
    for lam in lambdas:
        series_rows: List[Dict[str, object]] = []
        profit_stop: Optional[int] = None
        p95_stop: Optional[int] = None
        for capacity in capacities:
            if capacity == 1:
                continue
            delta = _delta_table(
                f"tea_cap{capacity}_minus_cap{capacity - 1}_lam{lam:g}",
                cells[(lam, capacity)],
                cells[(lam, capacity - 1)],
                metrics=(
                    "los_p95", "mean_los", "balk_rate", "served", "profit_per_hour",
                    "util", "staff_minutes_available",
                ),
                note=(
                    "one extra tea station and one extra barista versus the previous "
                    "capacity step; common random numbers"
                ),
            )
            marginals.append(delta)
            profit_diff = delta["metrics"]["profit_per_hour"]
            p95_diff = delta["metrics"]["los_p95"]
            if profit_stop is None and profit_diff["diff"] <= 0:  # type: ignore[index]
                profit_stop = capacity
            if p95_stop is None and p95_diff["diff"] >= -p95_diff["ci95"]:  # type: ignore[index]
                p95_stop = capacity
            series_rows.append(
                {
                    "tea_capacity": capacity,
                    "tea_util": cells[(lam, capacity)].get("tea_util"),
                    "barista_pool_util": (cells[(lam, capacity)].get("pool_util") or {}).get("barista"),
                    "order_util": cells[(lam, capacity)].get("order_util"),
                    "los_p95": cells[(lam, capacity)]["means"]["los_p95"],  # type: ignore[index]
                    "profit_per_hour": cells[(lam, capacity)]["means"]["profit_per_hour"],  # type: ignore[index]
                    "delta_profit": profit_diff["diff"],  # type: ignore[index]
                    "delta_los_p95": p95_diff["diff"],  # type: ignore[index]
                    "delta_profit_ci95": profit_diff["ci95"],  # type: ignore[index]
                }
            )
        migration[f"lambda_{lam:g}"] = {
            "tea_is_top_station_all_capacities": all(
                cells[(lam, capacity)].get("top_station") == "tea" for capacity in capacities
            ),
            "top_station_by_capacity": {
                str(capacity): cells[(lam, capacity)].get("top_station") for capacity in capacities
            },
            "tea_util_by_capacity": {
                str(capacity): cells[(lam, capacity)].get("tea_util") for capacity in capacities
            },
            "barista_pool_util_by_capacity": {
                str(capacity): (cells[(lam, capacity)].get("pool_util") or {}).get("barista")
                for capacity in capacities
            },
            "first_capacity_with_non_positive_marginal_profit": profit_stop,
            "first_capacity_with_insignificant_p95_gain": p95_stop,
            "critical_capacity": profit_stop if profit_stop is not None else max(capacities),
            "note": (
                "critical_capacity is the smallest capacity whose extra station fails to "
                "pay for itself (marginal profit/h <= 0 on common random numbers). The "
                "bottleneck answer uses station utilisation: with staff synced to stations "
                "the tea station stops being the binding *station* once its utilisation "
                "falls to the level of the shared barista pool and the order counter."
            ),
        }
    series = {
        "by_lambda": {
            f"lambda_{lam:g}": [
                {
                    "capacity": capacity,
                    "tea_util": cells[(lam, capacity)].get("tea_util"),
                    "barista_pool_util": (cells[(lam, capacity)].get("pool_util") or {}).get("barista"),
                    "order_util": cells[(lam, capacity)].get("order_util"),
                    "ice_util": cells[(lam, capacity)].get("ice_util"),
                    "los_p95": cells[(lam, capacity)]["means"]["los_p95"],  # type: ignore[index]
                    "profit_per_hour": cells[(lam, capacity)]["means"]["profit_per_hour"],  # type: ignore[index]
                }
                for capacity in capacities
            ]
            for lam in lambdas
        }
    }
    return {"rows": rows, "marginals": marginals, "migration": migration, "series": series}


def build_fixed_labour_companion() -> Dict[str, object]:
    """Tea capacity sweep with the barista count held at two.

    The main sweep syncs staff with stations, so the tea station and the barista
    pool grow together. This companion holds labour fixed: it is the clean
    picture of the bottleneck migrating from equipment to people.
    """
    print("[network] tea capacity sweep with fixed labour (2 baristas)")
    base = library.load_scenario("network_tea_bottleneck")
    rows: List[Dict[str, object]] = []
    cells: Dict[Tuple[float, int], Dict[str, object]] = {}
    for lam in (0.9, 1.2):
        for capacity in (1, 2, 3, 4):
            config = tea_capacity_config(replace(base, arrival_rate=lam), capacity, baristas=2)
            label = f"fixed_labour_cap{capacity}_lam{lam:g}"
            cell = run_cell(config, label=label, keep_rows=True)
            cells[(lam, capacity)] = cell
            rows.append(
                {
                    "lambda": lam,
                    "tea_capacity": capacity,
                    "baristas": 2,
                    "reps": cell["reps"],
                    "theoretical_barista_load": config.utilization(),
                    "theoretical_pool_load": theoretical_pool_load(config),
                    "tea_util": cell.get("tea_util"),
                    "barista_pool_util": (cell.get("pool_util") or {}).get("barista"),
                    "order_util": cell.get("order_util"),
                    "metrics": {
                        key: cell["means"][key]  # type: ignore[index]
                        for key in (
                            "util", "mean_los", "los_p95", "balk_rate", "served",
                            "profit_per_hour", "staff_minutes_available",
                        )
                    },
                }
            )
    marginals = []
    for lam in (0.9, 1.2):
        for capacity in (2, 3, 4):
            marginals.append(
                _delta_table(
                    f"fixed_labour_cap{capacity}_minus_cap{capacity - 1}_lam{lam:g}",
                    cells[(lam, capacity)],
                    cells[(lam, capacity - 1)],
                    metrics=("los_p95", "mean_los", "served", "profit_per_hour"),
                    note="one extra tea slot, no extra barista",
                )
            )
    return {"rows": rows, "marginals": marginals}


def build_strategy_bottleneck() -> Dict[str, object]:
    print("[network] strategy x bottleneck")
    scenario_names = ("network_tea_bottleneck", "ice_cream_bottleneck")
    policies = (
        ("synchro_plain", False, False),
        ("synchro_fast", False, True),
        ("split_plain", True, False),
        ("split_fast", True, True),
    )
    rows: List[Dict[str, object]] = []
    cells: Dict[Tuple[str, str], Dict[str, object]] = {}
    paired: List[Dict[str, object]] = []
    for scenario in scenario_names:
        base = library.load_scenario(scenario)
        for label, split, fast in policies:
            config = replace(
                base, policy=replace(base.policy, split_mix=split, fast_priority=fast)
            )
            cell_label = f"{scenario}_{label}"
            cell = run_cell(config, label=cell_label, keep_rows=True)
            cells[(scenario, label)] = cell
            rows.append(
                {
                    "scenario": scenario,
                    "policy": label,
                    "split_mix": split,
                    "fast_priority": fast,
                    "reps": cell["reps"],
                    "station_util": cell.get("station_util"),
                    "top_station": cell.get("top_station"),
                    "metrics": {
                        key: cell["means"][key]  # type: ignore[index]
                        for key in (
                            "mean_los", "mix_los", "mix_ice_hand", "los_p95", "balk_rate",
                            "abandon_rate", "served", "profit_per_hour", "util",
                        )
                    },
                    "ci95": {
                        key: cell["ci95"][key]  # type: ignore[index]
                        for key in ("mean_los", "los_p95", "profit_per_hour", "balk_rate")
                    },
                }
            )
        reference = cells[(scenario, "synchro_plain")]
        for label, _split, _fast in policies:
            if label == "synchro_plain":
                continue
            paired.append(
                _delta_table(
                    f"{scenario}_{label}_minus_synchro_plain",
                    cells[(scenario, label)],
                    reference,
                    metrics=(
                        "profit_per_hour", "mean_los", "mix_los", "mix_ice_hand",
                        "los_p95", "served", "balk_rate",
                    ),
                    note="policy cell minus synchro+plain on common random numbers",
                )
            )
    fast_value: List[Dict[str, object]] = []
    split_value: List[Dict[str, object]] = []
    for scenario in scenario_names:
        for split_label, split in (("synchro", False), ("split", True)):
            fast_effect = _delta_table(
                f"{scenario}_{split_label}_fast_minus_plain",
                cells[(scenario, f"{split_label}_fast")],
                cells[(scenario, f"{split_label}_plain")],
                metrics=("profit_per_hour", "mean_los", "los_p95", "balk_rate"),
                note="fast-item priority vs plain FCFS inside one split policy",
            )
            fast_value.append(
                {
                    "scenario": scenario,
                    "split_label": split_label,
                    "split_mix": split,
                    "profit_per_hour": fast_effect["metrics"]["profit_per_hour"],
                    "mean_los": fast_effect["metrics"]["mean_los"],
                    "los_p95": fast_effect["metrics"]["los_p95"],
                    "balk_rate": fast_effect["metrics"]["balk_rate"],
                }
            )
        for fast_label, fast in (("plain", False), ("fast", True)):
            split_effect = _delta_table(
                f"{scenario}_{fast_label}_split_minus_synchro",
                cells[(scenario, f"split_{fast_label}")],
                cells[(scenario, f"synchro_{fast_label}")],
                metrics=("profit_per_hour", "mean_los", "mix_los", "mix_ice_hand", "los_p95"),
                note="split vs synchronized delivery inside one triage policy",
            )
            split_value.append(
                {
                    "scenario": scenario,
                    "fast_label": fast_label,
                    "fast_priority": fast,
                    "profit_per_hour": split_effect["metrics"]["profit_per_hour"],
                    "mean_los": split_effect["metrics"]["mean_los"],
                    "mix_ice_hand": split_effect["metrics"]["mix_ice_hand"],
                    "los_p95": split_effect["metrics"]["los_p95"],
                }
            )
    series = {
        "profit_by_policy": [
            {
                "scenario": row["scenario"],
                "policy": row["policy"],
                "profit_per_hour": row["metrics"]["profit_per_hour"],  # type: ignore[index]
                "mean_los": row["metrics"]["mean_los"],  # type: ignore[index]
                "los_p95": row["metrics"]["los_p95"],  # type: ignore[index]
            }
            for row in rows
        ],
        "fast_priority_value": fast_value,
        "split_value": split_value,
    }
    return {"rows": rows, "paired": paired, "fast_value": fast_value, "split_value": split_value, "series": series}


def build_skill_matrix() -> Dict[str, object]:
    print("[network] skill matrix")
    base = library.load_scenario("network_tea_bottleneck")
    network = base.network
    assert network is not None
    stations = (
        ds.StationSpec("order", 2, "cashier"),
        ds.StationSpec("tea", 3, "barista"),
        ds.StationSpec("ice", 2, "barista"),
        ds.StationSpec("bread", 2, "cashier"),
    )
    sim_minutes = base.sim_minutes

    def all_day_windows(roles_counts: Sequence[Tuple[str, int]]):
        return tuple(
            ds.ShiftWindow(role=role, start_minute=0.0, end_minute=sim_minutes)
            for role, count in roles_counts
            for _ in range(count)
        )

    specs = {
        "dedicated": ds.StaffSpec(
            roles=("cashier", "barista"),
            counts=(2, 2),
            skills=(("cashier",), ("barista",)),
            windows=all_day_windows((("cashier", 2), ("barista", 2))),
        ),
        "generalist": ds.StaffSpec(
            roles=("clerk",),
            counts=(4,),
            skills=(("all",),),
            windows=all_day_windows((("clerk", 4),)),
        ),
        "cross_trained": ds.StaffSpec(
            roles=("cashier", "barista"),
            counts=(2, 2),
            skills=(("cashier",), ("barista", "cashier")),
            windows=all_day_windows((("cashier", 2), ("barista", 2))),
        ),
    }
    descriptions = {
        "dedicated": "2 cashiers + 2 baristas, no shared skills",
        "generalist": "4 generalists, every staff unit has the 'all' skill",
        "cross_trained": "2 cashiers + 2 baristas where baristas can also cashier",
    }
    rows: List[Dict[str, object]] = []
    cells: Dict[str, Dict[str, object]] = {}
    for name, staff in specs.items():
        config = replace(
            base,
            arrival_rate=1.2,
            workers=4,
            network=ds.NetworkSpec(stations=stations, staff=staff, routes=network.routes),
        )
        label = f"skill_{name}"
        cell = run_cell(config, label=label, keep_rows=True)
        cells[name] = cell
        rows.append(
            {
                "configuration": name,
                "description": descriptions[name],
                "headcount": sum(staff.counts),
                "skills": [list(skill_set) for skill_set in staff.skills],
                "reps": cell["reps"],
                "station_util": cell.get("station_util"),
                "pool_util": cell.get("pool_util"),
                "metrics": {
                    key: cell["means"][key]  # type: ignore[index]
                    for key in (
                        "wage_per_hour", "util", "mean_los", "los_p95", "balk_rate",
                        "served", "profit_per_hour", "revenue_per_hour",
                        "staff_minutes_available",
                    )
                },
                "ci95": {
                    key: cell["ci95"][key]  # type: ignore[index]
                    for key in ("mean_los", "los_p95", "profit_per_hour", "balk_rate")
                },
            }
        )
    paired = [
        _delta_table(
            f"skill_{name}_minus_dedicated",
            cells[name],
            cells["dedicated"],
            metrics=("mean_los", "los_p95", "profit_per_hour", "served", "util", "wage_per_hour", "balk_rate"),
            note="same headcount and the same wage bill; only the skill matrix changes",
        )
        for name in ("generalist", "cross_trained")
    ]
    series = {
        "profit": [
            {
                "configuration": row["configuration"],
                "profit_per_hour": row["metrics"]["profit_per_hour"],  # type: ignore[index]
                "mean_los": row["metrics"]["mean_los"],  # type: ignore[index]
                "los_p95": row["metrics"]["los_p95"],  # type: ignore[index]
                "wage_per_hour": row["metrics"]["wage_per_hour"],  # type: ignore[index]
            }
            for row in rows
        ]
    }
    return {"rows": rows, "paired": paired, "series": series}


def build_shift_experiment() -> Dict[str, object]:
    print("[network] shift / break experiment")
    base = library.load_scenario("campus_rush")
    network = base.network
    assert network is not None
    sim_minutes = base.sim_minutes

    def windows(role: str, count: int, start: float = 0.0):
        return tuple(
            ds.ShiftWindow(role=role, start_minute=start, end_minute=sim_minutes)
            for _ in range(count)
        )

    specs = {
        "no_shift": ds.StaffSpec(
            roles=("cashier", "barista"),
            counts=(2, 3),
            skills=(("cashier",), ("barista",)),
            windows=windows("cashier", 2) + windows("barista", 3),
        ),
        "staggered_break": ds.StaffSpec(
            roles=("cashier", "barista"),
            counts=(2, 3),
            skills=(("cashier",), ("barista",)),
            windows=windows("cashier", 2) + windows("barista", 3),
            breaks=(("cashier", 240.0, 270.0), ("barista", 300.0, 330.0)),
        ),
        "mid_shift_barista": ds.StaffSpec(
            roles=("cashier", "barista"),
            counts=(2, 4),
            skills=(("cashier",), ("barista",)),
            windows=windows("cashier", 2) + windows("barista", 3) + windows("barista", 1, 240.0),
        ),
    }
    descriptions = {
        "no_shift": "5 staff, everyone on shift for the whole day, no breaks",
        "staggered_break": "same 5 staff with staggered 30-minute breaks (index-shifted)",
        "mid_shift_barista": "same 5 staff plus a 6th barista joining at minute 240",
    }
    rows: List[Dict[str, object]] = []
    cells: Dict[str, Dict[str, object]] = {}
    for name, staff in specs.items():
        config = replace(
            base, network=ds.NetworkSpec(stations=network.stations, staff=staff, routes=network.routes)
        )
        label = f"shift_{name}"
        cell = run_cell(config, label=label, keep_rows=True, keep_hourly=True)
        cells[name] = cell
        rows.append(
            {
                "configuration": name,
                "description": descriptions[name],
                "headcount": sum(staff.counts),
                "reps": cell["reps"],
                "station_util": cell.get("station_util"),
                "pool_util": cell.get("pool_util"),
                "metrics": {
                    key: cell["means"][key]  # type: ignore[index]
                    for key in (
                        "wage_per_hour", "util", "mean_los", "los_p95", "peak_hour_los",
                        "balk_rate", "abandon_rate", "served", "profit_per_hour",
                        "revenue_per_hour", "staff_minutes_available",
                    )
                },
                "ci95": {
                    key: cell["ci95"][key]  # type: ignore[index]
                    for key in ("mean_los", "los_p95", "peak_hour_los", "served", "profit_per_hour")
                },
                "hourly": cell["hourly"],
            }
        )
    segments = [(segment.start_minute, segment.multiplier) for segment in base.demand.segments]
    peak_windows: List[Tuple[float, float]] = []
    for index, (start, multiplier) in enumerate(segments):
        if multiplier < 1.5:
            continue
        end = segments[index + 1][0] if index + 1 < len(segments) else base.sim_minutes
        peak_windows.append((start, end))

    def window_los(hourly_rows) -> Dict[str, Optional[float]]:
        """Served-weighted mean LOS inside each demand peak, from the hourly series."""
        result: Dict[str, Optional[float]] = {}
        for window_start, window_end in peak_windows:
            inside = [
                row for row in hourly_rows
                if window_start <= row["hour_start"] < window_end
                and row["mean_los"] is not None
            ]
            weight = sum(row["served"] for row in inside)
            key = f"min{window_start:g}-{window_end:g}"
            result[key] = (
                _round(sum(row["mean_los"] * row["served"] for row in inside) / weight, 4)
                if weight > 0 else None
            )
        return result

    for row in rows:
        row["peak_window_los"] = window_los(cells[row["configuration"]]["hourly"])
    peak_hours = sorted({int(start // 60) for start, _end in peak_windows})
    paired = [
        _delta_table(
            f"shift_{name}_minus_no_shift",
            cells[name],
            cells["no_shift"],
            metrics=(
                "mean_los", "los_p95", "peak_hour_los", "served", "profit_per_hour",
                "wage_per_hour", "balk_rate",
            ),
            note=(
                "versus the no-shift/no-break baseline on common random numbers; the "
                "mid-shift variant has one more barista and therefore a higher wage bill"
            ),
        )
        for name in ("staggered_break", "mid_shift_barista")
    ]
    series = {
        "hourly_los": {
            name: [row["mean_los"] for row in cells[name]["hourly"]]  # type: ignore[index]
            for name in specs
        },
        "hourly_busy_ratio": {
            name: [row["busy_ratio"] for row in cells[name]["hourly"]]  # type: ignore[index]
            for name in specs
        },
        "hourly_arrivals": [row["arrivals"] for row in cells["no_shift"]["hourly"]],  # type: ignore[index]
        "peak_hours": peak_hours,
        "peak_windows": [list(window) for window in peak_windows],
        "peak_window_los": {
            name: window_los(cells[name]["hourly"])  # type: ignore[arg-type]
            for name in specs
        },
        "peak_hour_los": {
            name: cells[name]["means"]["peak_hour_los"]  # type: ignore[index]
            for name in specs
        },
    }
    return {"rows": rows, "paired": paired, "series": series}


def build_network_study() -> Dict[str, object]:
    started = time.perf_counter()
    capacity = build_tea_capacity_sweep()
    fixed_labour = build_fixed_labour_companion()
    strategy = build_strategy_bottleneck()
    skills = build_skill_matrix()
    shifts = build_shift_experiment()
    elapsed = time.perf_counter() - started

    migration = capacity["migration"]
    fixed_labour_flat: Dict[str, Optional[int]] = {}
    for lam in (0.9, 1.2):
        rows_lam = sorted(
            (row for row in fixed_labour["rows"] if row["lambda"] == lam),
            key=lambda row: row["tea_capacity"],
        )
        fixed_labour_flat[f"lambda_{lam:g}"] = next(
            (
                row["tea_capacity"]
                for row, following in zip(rows_lam, rows_lam[1:])
                if abs(row["metrics"]["los_p95"] - following["metrics"]["los_p95"]) < 1e-9
            ),
            None,
        )
    fast_value = strategy["fast_value"]
    findings = {
        "bottleneck_migration": {
            "critical_capacity_by_lambda": {
                key: value["critical_capacity"] for key, value in migration.items()
            },
            "tea_remains_top_station_by_lambda": {
                key: value["tea_is_top_station_all_capacities"] for key, value in migration.items()
            },
            "fixed_labour_tea_util_by_capacity": {
                f"lambda_{lam:g}": {
                    str(capacity_value): next(
                        row["tea_util"] for row in fixed_labour["rows"]
                        if row["lambda"] == lam and row["tea_capacity"] == capacity_value
                    )
                    for capacity_value in (1, 2, 3, 4)
                }
                for lam in (0.9, 1.2)
            },
            "fixed_labour_first_capacity_with_no_further_los_gain": fixed_labour_flat,
            "note": (
                "With staff synced to stations the tea station stays the busiest station "
                "for every capacity, but each extra station pays for itself only up to the "
                "computed critical capacity; beyond it the shared barista pool and the "
                "order counter take over the queue. The fixed-labour companion is the clean "
                "picture of the migration: with the barista count held fixed, tea station "
                "utilisation collapses as slots are added while mean waiting, p95 and "
                "profit are bit-identical, because the labour pool is now the constraint."
            ),
        },
        "strategy_by_bottleneck": {
            "fast_priority_value": fast_value,
            "note": (
                "Fast-item priority is worth much less when the tea station is the "
                "bottleneck than when the ice-cream machine is: the fast lane only helps "
                "customers whose own station has slack."
            ),
        },
        "skill_matrix": {
            "generalist_minus_dedicated_profit": skills["paired"][0]["metrics"]["profit_per_hour"],
            "cross_trained_minus_dedicated_profit": skills["paired"][1]["metrics"]["profit_per_hour"],
            "note": (
                "Same headcount and the same wage bill in all three cells, so the "
                "difference is pure queueing: a single flexible pool captures the pooling "
                "gain, one-way cross-training into the under-loaded task does not."
            ),
        },
        "shifts": {
            "peak_hour_los": shifts["series"]["peak_hour_los"],
            "peak_window_los": shifts["series"]["peak_window_los"],
            "note": (
                "Breaks near a peak cost more than they save: a staggered 30-minute break "
                "removes capacity exactly when the peak needs it, so the peak-hour wait and "
                "the p95 jump and profit falls by more than the unpaid break saves in wages. "
                "Adding a barista mid-shift raises served and lowers balking, but the "
                "afternoon peak wait is essentially unchanged because the tea station, not "
                "headcount, is the binding resource at the peak; the extra wage line "
                "therefore costs money. Before minute 240 the mid-shift variant is identical "
                "to the no-shift baseline (the extra barista is not on shift and the balk "
                "estimate only counts staff on shift), so the morning peak is unchanged by "
                "construction rather than by luck."
            ),
        },
    }
    print("[network] finished in %.1fs" % elapsed)
    return {
        "meta": v2_common.meta(
            "network_study",
            notes=(
                "Layer 2 experiments on the network scenarios. Station utilisation comes "
                "straight from the engine; labour-pool utilisation is derived by grouping "
                "the stations that share a skill and dividing their busy minutes by the "
                "pre-break shift minutes of the staff that can operate them. Cells with an "
                "estimated peak load above 0.95 use 60 replicates (the saturated tea "
                "capacities), everything else uses 100; first seed 0, stride 1. The balk "
                "decision uses the engine's Little's-Law-style wait estimate divided by the "
                "number of staff units that are ON SHIFT at the arrival instant (shift "
                "windows and breaks are coverage-checked), so a late-joining barista does "
                "not make the shop look bigger than it is; the legacy v1 path keeps the "
                "full worker count so the golden anchors stay bit-identical."
            ),
            reps_default=REPS,
            reps_overload=OVERLOAD_REPS,
            seed=SEED,
            seed_stride=SEED_STRIDE,
            elapsed_seconds=round(elapsed, 1),
        ),
        "tables": {
            "tea_capacity_sweep": capacity["rows"],
            "tea_capacity_marginals": capacity["marginals"],
            "bottleneck_migration": migration,
            "fixed_labour_companion": fixed_labour["rows"],
            "fixed_labour_marginals": fixed_labour["marginals"],
            "strategy_bottleneck": strategy["rows"],
            "strategy_bottleneck_paired": strategy["paired"],
            "strategy_fast_value": strategy["fast_value"],
            "strategy_split_value": strategy["split_value"],
            "skill_matrix": skills["rows"],
            "skill_matrix_paired": skills["paired"],
            "shifts": shifts["rows"],
            "shifts_paired": shifts["paired"],
        },
        "series": {
            "tea_capacity": capacity["series"],
            "strategy": strategy["series"],
            "skills": skills["series"],
            "shifts": shifts["series"],
        },
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("all", "library", "demand", "network"),
        default="all",
        help="which stage(s) to run (default: all three)",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=None,
        help="override the replicate count of every cell (default: 100, or 60 over the "
        "estimated overload threshold; the scenario library always uses --reps 100)",
    )
    args = parser.parse_args(argv)

    global REPS
    if args.reps is not None:
        REPS = max(2, args.reps)
        print(f"[setup] replicate override: {REPS}")

    started = time.perf_counter()
    if args.stage in ("all", "library"):
        payload = build_scenario_library()
        v2_common.save("scenario_library", payload)
    if args.stage in ("all", "demand"):
        payload = build_demand_study()
        v2_common.save("demand_study", payload)
    if args.stage in ("all", "network"):
        payload = build_network_study()
        v2_common.save("network_study", payload)
    print("[done] total wall clock %.1fs" % (time.perf_counter() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
