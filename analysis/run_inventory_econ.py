"""Layer 3 (inventory / BOM) and Layer 4 (economics / fairness) experiments.

Two studies, one script, one shared harness (``analysis/study_common.py``) so the
JSON schema, the seeds and the provenance metadata match the other mechanism layers::

    python analysis/run_inventory_econ.py              # full run (~5 minutes)
    python analysis/run_inventory_econ.py --quick      # smoke test (~20 seconds)
    python analysis/run_inventory_econ.py --only economics

Outputs
-------
``results/inventory_study.json``
    Layer 3: (s, S) reorder-point / order-quantity grids for the perishable
    pearls and the non-perishable tea kit, lead-time scan, pearl shelf-life
    scan, shelf-life x lot-size interaction, and the lost-sale vs substitution
    policy comparison.  Baseline scenario: ``data/scenarios/inventory_lean.json``.

``results/economics_study.json``
    Layer 4: peak-pricing grid (multiplier x elasticity) on the ``campus_rush``
    peak windows, SLA target x compensation grid, the fairness (starvation-cap)
    trade-off at high load, and a combined "good manager" scenario compared with
    the shipped baseline under common random numbers.

Method
------
* Every cell is a ``study_common.replicate`` run (mean + 95% CI over the
  per-replicate metrics), seed ``0``, stride ``1``.
* ``100`` replicates per cell; cells whose theoretical utilisation exceeds
  ``0.95`` use ``60`` (the queue tail dominates and extra replicates buy very
  little) - this mirrors ``analysis/run_policy_sweep.py``.
* Paired differences are computed from the retained per-replicate rows of the
  same seeds (common random numbers), never by re-running with different seeds.
* No number in the JSON is typed by hand: every table row is produced below, and
  every "optimum" / "elbow" / "threshold" is derived from the rows at run time.

Caveats that the report must repeat (also embedded in ``meta.caveats``)
----------------------------------------------------------------------
* ``fill_rate`` is measured over *all* arrivals (the engine's denominator is
  ``len(customers)``, which includes the warm-up hour), while ``served`` and the
  money metrics are measured after ``warmup_minutes``.  Morning stock-outs are
  therefore inside ``fill_rate`` but not inside ``served``.
* ``purchase_cost`` charges every unit bought, including units still in stock at
  closing time, and it charges the opening stock again on every replicate.
  Minimising it alone rewards starving the shop; the report must read it next to
  ``fill_rate`` and ``stockout_losses``.
* ``waste_units`` only counts lots whose expiry is processed (expiry is evaluated
  lazily, when the ingredient is next touched), so it is a lower bound.
* ``profit_per_hour`` subtracts the waiting cost of the customers actually
  served.  Demand shedding (higher prices, tighter capacity) therefore looks
  profitable twice - fewer lost sales *and* less waiting cost - which is why the
  profit-maximising multiplier sits at the edge of the tested range.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:  # ``python analysis/run_inventory_econ.py`` puts analysis/ on sys.path
    import study_common as common
except ImportError:  # pragma: no cover - only when imported as a module
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import study_common as common

from bubble_tea_sim import data_spec as ds
from bubble_tea_sim import library, stats
from bubble_tea_sim.engine import Simulation

# ---------------------------------------------------------------------------
# Design constants
# ---------------------------------------------------------------------------
SEED = 0
SEED_STRIDE = 1
REPS = 100
REPS_OVERLOAD = 60
OVERLOAD_UTILISATION = 0.95

#: (s, S) factors are expressed as a share of the ingredient's opening stock.
SS_FACTORS: Tuple[float, ...] = (0.25, 0.5, 0.75, 1.0)  # order quantity S
S_FACTORS: Tuple[float, ...] = (0.1, 0.2, 0.3, 0.4)  # reorder point s
LEAD_TIMES: Tuple[float, ...] = (30.0, 60.0, 120.0, 240.0)
SHELF_LIVES: Tuple[float, ...] = (120.0, 240.0, 360.0, 480.0)
PEARLS_ORDER_CEILING: Tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0)
PEARLS_SHELF_INTERACTION: Tuple[float, ...] = (120.0, 180.0, 240.0, 360.0)

PRICE_MULTIPLIERS: Tuple[float, ...] = (1.0, 1.1, 1.2, 1.3, 1.4)
ELASTICITIES: Tuple[float, ...] = (-0.5, -1.0, -1.5, -2.0)
PRICE_REFINEMENT: Tuple[float, ...] = (1.5, 1.6, 1.8, 2.0)
PEAK_WINDOWS: Tuple[Tuple[float, float], ...] = ((60.0, 180.0), (300.0, 420.0))

SLA_TARGETS: Tuple[float, ...] = (3.0, 5.0, 8.0)
SLA_COMPENSATIONS: Tuple[float, ...] = (1.0, 2.0, 4.0)
STARVATION_CAPS: Tuple[Optional[float], ...] = (None, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
FAIRNESS_LOADS: Tuple[float, ...] = (1.10, 1.25, 1.40)
#: The load the fairness table is reported at (the brief's "lambda = 1.25").
FAIRNESS_PRIMARY: float = 1.25

#: Metric keys carried into almost every table row.
BASE_KEYS: Tuple[str, ...] = (
    "served",
    "balked",
    "reneged",
    "stranded",
    "mean_los",
    "los_p95",
    "util",
    "revenue_per_hour",
    "profit_per_hour",
    "waiting_cost_total",
)
INVENTORY_KEYS: Tuple[str, ...] = BASE_KEYS + (
    "fill_rate",
    "stockout_losses",
    "waste_units",
    "purchase_cost",
    "ingredient_cost_per_hour",
)
ECONOMIC_KEYS: Tuple[str, ...] = BASE_KEYS + (
    "revenue_total",
    "mean_price_factor",
    "fairness_gap",
    "sla_attainment",
    "sla_compensation_total",
    "starvation_events",
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _r(value: Optional[float], digits: int = 6) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _percentile(values: Sequence[float], percent: float) -> float:
    """Same linear-interpolation percentile as ``bubble_tea_sim.engine``."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def in_peak(minute: float) -> bool:
    """Is ``minute`` inside one of the pricing windows?"""
    return any(start <= minute < end for start, end in PEAK_WINDOWS)


def reps_for(config) -> int:
    """Replicate count for one cell (60 once utilisation passes 0.95)."""
    return REPS_OVERLOAD if config.utilization() > OVERLOAD_UTILISATION else REPS


def run_cell(config, peaks: bool = False) -> Dict[str, object]:
    """Run one design cell.

    With ``peaks=False`` this is exactly :func:`study_common.replicate`.  With
    ``peaks=True`` the same seeds are replayed once and the customer records are
    read as well, so the peak-window tail (``los_p95`` inside the pricing
    windows) can be separated from the off-peak tail.  The metric block is
    identical either way: it is ``stats.flatten_metrics`` aggregated with
    ``stats.mean`` / ``stats.ci95`` over the same seeds, which is what
    ``study_common.replicate`` does internally.
    """
    reps = reps_for(config)
    if not peaks:
        return common.replicate(config, reps=reps, seed=SEED, seed_stride=SEED_STRIDE)
    rows: List[Dict[str, float]] = []
    peak_p95: List[float] = []
    offpeak_p95: List[float] = []
    peak_share: List[float] = []
    for index in range(reps):
        result = Simulation(config, seed=SEED + index * SEED_STRIDE).run()
        rows.append(stats.flatten_metrics(result.metrics))
        peak_waits: List[float] = []
        offpeak_waits: List[float] = []
        for customer in result.customers:
            if not customer.served or customer.arrival < config.warmup_minutes:
                continue
            wait = customer.departure - customer.arrival
            if in_peak(customer.arrival):
                peak_waits.append(wait)
            else:
                offpeak_waits.append(wait)
        peak_p95.append(_percentile(peak_waits, 95.0))
        offpeak_p95.append(_percentile(offpeak_waits, 95.0))
        total = len(peak_waits) + len(offpeak_waits)
        peak_share.append(len(peak_waits) / total if total else 0.0)
    keys = sorted(rows[0])
    return {
        "reps": reps,
        "seed": SEED,
        "seed_stride": SEED_STRIDE,
        "means": {key: stats.mean([row[key] for row in rows]) for key in keys},
        "ci95": {key: stats.ci95([row[key] for row in rows]) for key in keys},
        "per_rep": rows,
        "peak": {
            "los_p95": {
                "mean": stats.mean(peak_p95),
                "ci95": stats.ci95(peak_p95),
            },
            "offpeak_los_p95": {
                "mean": stats.mean(offpeak_p95),
                "ci95": stats.ci95(offpeak_p95),
            },
            "served_share": stats.mean(peak_share),
        },
    }


def summarise(
    run: Dict[str, object],
    keys: Sequence[str] = BASE_KEYS,
    config=None,
) -> Dict[str, Optional[float]]:
    """Mean metrics for one cell; ``sla_attainment`` is ``None`` without an SLA.

    The engine stores ``sla_attainment = None`` when no SLA layer is active and
    ``stats.flatten_metrics`` turns that into ``0.0``.  Reporting "0 % of
    customers met the SLA" for a shop that never promised an SLA would be wrong,
    so the key is restored to ``None`` here.
    """
    means = run["means"]
    row: Dict[str, Optional[float]] = {
        key: _r(means[key]) for key in keys if key in means  # type: ignore[index]
    }
    if config is not None and config.sla is None:
        row["sla_attainment"] = None
    return row


def summarise_ci(run: Dict[str, object], keys: Sequence[str] = BASE_KEYS) -> Dict[str, float]:
    ci = run["ci95"]
    return {key: _r(ci[key]) for key in keys if key in ci}  # type: ignore[index]


def paired(run_a: Dict[str, object], run_b: Dict[str, object], keys: Sequence[str]) -> Dict[str, object]:
    """Common-random-number difference ``a - b`` with a 95% CI.

    Both runs must come from :func:`run_cell` with the same seeds, so the
    per-replicate rows line up and the difference is paired.
    """
    rows_a = run_a["per_rep"]  # type: ignore[index]
    rows_b = run_b["per_rep"]  # type: ignore[index]
    count = min(len(rows_a), len(rows_b))
    diff: Dict[str, float] = {}
    ci: Dict[str, float] = {}
    for key in keys:
        deltas = [
            rows_a[index].get(key, 0.0) - rows_b[index].get(key, 0.0)
            for index in range(count)
        ]
        diff[key] = _r(sum(deltas) / count)
        average = sum(deltas) / count
        if count > 1:
            variance = sum((value - average) ** 2 for value in deltas) / (count - 1)
            ci[key] = _r(1.959963984540054 * (variance**0.5) / (count**0.5))
        else:  # pragma: no cover - defensive
            ci[key] = 0.0
    return {"reps": count, "diff": diff, "ci95": ci}


def describe(config) -> Dict[str, object]:
    payload = config.describe()
    payload["policy"] = config.policy.describe()
    payload["reps_planned"] = reps_for(config)
    return payload


def pareto_front(
    rows: Sequence[Dict[str, object]],
    maximise: Sequence[str],
    minimise: Sequence[str],
) -> List[Dict[str, object]]:
    """Rows that no other row weakly dominates on all objectives."""
    front: List[Dict[str, object]] = []
    for row in rows:
        dominated = False
        for other in rows:
            if other is row:
                continue
            not_worse = all(
                float(other[key]) >= float(row[key]) for key in maximise  # type: ignore[index]
            ) and all(
                float(other[key]) <= float(row[key]) for key in minimise  # type: ignore[index]
            )
            strictly_better = any(
                float(other[key]) > float(row[key]) for key in maximise  # type: ignore[index]
            ) or any(
                float(other[key]) < float(row[key]) for key in minimise  # type: ignore[index]
            )
            if not_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(row)
    return front


def argmax(rows: Sequence[Dict[str, object]], key: str) -> Dict[str, object]:
    return max(rows, key=lambda row: float(row[key]))  # type: ignore[index]


def argmin(rows: Sequence[Dict[str, object]], key: str) -> Dict[str, object]:
    return min(rows, key=lambda row: float(row[key]))  # type: ignore[index]


# ---------------------------------------------------------------------------
# Inventory layer (Layer 3)
# ---------------------------------------------------------------------------
#: A deliberately ice-poor replenishment plan, used to give the substitution
#: policy something to substitute: only ``ice_mix`` is starved, so a mixed order
#: is short while its tea ingredients are fine.
SCARCE_ICE = {
    "initial_stock": 40.0,
    "reorder_point": 10.0,
    "order_quantity": 30.0,
    "lead_time_minutes": 120.0,
}
#: A pearl-poor plan: pearls are shared by tea and mixed orders, so substitution
#: cannot create the missing ingredient - it can only move demand between two
#: products that both need it.  Included to show the boundary of the lever; the
#: level is picked so the shop stays alive (fill rate ~0.75) instead of dying.
SCARCE_PEARLS = {
    "initial_stock": 60.0,
    "reorder_point": 15.0,
    "order_quantity": 40.0,
    "lead_time_minutes": 90.0,
}


def _inventory_base():
    config = library.load_scenario("inventory_lean")
    if config.inventory is None:  # pragma: no cover - the scenario always has one
        raise RuntimeError("inventory_lean lost its inventory layer")
    return config


def with_ingredients(config, changes: Dict[str, Dict[str, float]]):
    """Return a copy of ``config`` with per-ingredient field overrides."""
    ingredients = []
    for ingredient in config.inventory.ingredients:  # type: ignore[union-attr]
        patch = changes.get(ingredient.name)
        ingredients.append(replace(ingredient, **patch) if patch else ingredient)
    return replace(
        config,
        inventory=replace(config.inventory, ingredients=tuple(ingredients)),  # type: ignore[arg-type]
    )


def scale_ss(config, names: Sequence[str], s_factor: float, S_factor: float):
    """Scale reorder points / order quantities of ``names`` by opening stock."""
    changes: Dict[str, Dict[str, float]] = {}
    for ingredient in config.inventory.ingredients:  # type: ignore[union-attr]
        if ingredient.name in names:
            changes[ingredient.name] = {
                "reorder_point": ingredient.initial_stock * s_factor,
                "order_quantity": ingredient.initial_stock * S_factor,
            }
    return with_ingredients(config, changes)


def substitution_outcomes(config) -> Dict[str, float]:
    """Per-replicate substitution count and stock-out mix, from a second pass.

    ``study_common.replicate`` only returns flattened metrics, and the engine does
    not expose a "substituted units" metric, so this helper re-runs the same
    seeds to read the customer records directly.
    """
    reps = reps_for(config)
    substituted = 0.0
    lost_by_kind: Dict[str, float] = {}
    for index in range(reps):
        result = Simulation(config, seed=SEED + index * SEED_STRIDE).run()
        for customer in result.customers:
            if customer.substituted:
                substituted += 1
            if customer.abandoned == "stockout":
                lost_by_kind[customer.kind] = lost_by_kind.get(customer.kind, 0.0) + 1
    return {
        "substituted_per_rep": _r(substituted / reps),
        "stockouts_by_kind_per_rep": {
            kind: _r(value / reps) for kind, value in sorted(lost_by_kind.items())
        },
    }


def _metrics_row(config, run: Dict[str, object], keys: Sequence[str]) -> Dict[str, object]:
    return summarise(run, keys, config)


def _grid_row_meta(config, names: Sequence[str], s_factor: float, S_factor: float) -> Dict[str, object]:
    settings = {}
    for ingredient in config.inventory.ingredients:  # type: ignore[union-attr]
        if ingredient.name in names:
            settings[ingredient.name] = {
                "reorder_point": _r(ingredient.reorder_point, 3),
                "order_quantity": _r(ingredient.order_quantity, 3),
            }
    return {
        "s_factor": s_factor,
        "S_factor": S_factor,
        "settings": settings,
        "policy": config.inventory.stockout_policy,  # type: ignore[union-attr]
    }


def study_inventory(quick: bool = False) -> Dict[str, object]:
    started = time.perf_counter()
    base = _inventory_base()
    keys = INVENTORY_KEYS

    ss_factors = SS_FACTORS[:2] if quick else SS_FACTORS
    s_factors = S_FACTORS[:2] if quick else S_FACTORS
    reps_note = "quick smoke run" if quick else f"{REPS} replicates ({REPS_OVERLOAD} above 0.95 utilisation)"

    tables: Dict[str, object] = {}
    series: Dict[str, object] = {}

    # -- baseline ---------------------------------------------------------
    base_run = run_cell(base)
    tables["baseline"] = {
        "config": describe(base),
        "metrics": summarise(base_run, keys, base),
        "ci95": summarise_ci(base_run, keys),
    }

    # -- 1. (s, S) grids --------------------------------------------------
    def ss_grid(names: Sequence[str]) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for s_factor in s_factors:
            for S_factor in ss_factors:
                config = scale_ss(base, names, s_factor, S_factor)
                run = run_cell(config)
                row = _grid_row_meta(config, names, s_factor, S_factor)
                row.update(_metrics_row(config, run, keys))
                row["ci95"] = {
                    key: summarise_ci(run, keys)[key]
                    for key in ("fill_rate", "profit_per_hour", "waste_units")
                    if key in summarise_ci(run, keys)
                }
                rows.append(row)
        return rows

    both = ("pearls", "tea_kit")
    tables["ss_joint_grid"] = ss_grid(both)
    tables["ss_pearls_only"] = ss_grid(("pearls",))
    tables["ss_teakit_only"] = ss_grid(("tea_kit",))

    # Profit surface for figures: rows are reorder points, columns lot sizes.
    profit_surface: List[List[float]] = []
    waste_surface: List[List[float]] = []
    for s_factor in s_factors:
        profit_line: List[float] = []
        waste_line: List[float] = []
        for S_factor in ss_factors:
            match = next(
                row
                for row in tables["ss_joint_grid"]  # type: ignore[union-attr]
                if row["s_factor"] == s_factor and row["S_factor"] == S_factor
            )
            profit_line.append(match["profit_per_hour"])
            waste_line.append(match["waste_units"])
        profit_surface.append(profit_line)
        waste_surface.append(waste_line)
    series["ss_profit_surface"] = {
        "s_factors": list(s_factors),
        "S_factors": list(ss_factors),
        "profit_per_hour": profit_surface,
        "waste_units": waste_surface,
    }
    # Scatter data for the "fill vs waste vs profit" trade-off page.
    series["fill_vs_waste"] = [
        {
            "s_factor": row["s_factor"],
            "S_factor": row["S_factor"],
            "fill_rate": row["fill_rate"],
            "waste_units": row["waste_units"],
            "profit_per_hour": row["profit_per_hour"],
            "purchase_cost": row["purchase_cost"],
        }
        for row in tables["ss_joint_grid"]  # type: ignore[union-attr]
    ]

    # -- 2. serial lead time ----------------------------------------------
    lead_rows: List[Dict[str, object]] = []
    for lead_time in LEAD_TIMES:
        changes = {
            ingredient.name: {"lead_time_minutes": lead_time}
            for ingredient in base.inventory.ingredients  # type: ignore[union-attr]
        }
        config = with_ingredients(base, changes)
        run = run_cell(config)
        row: Dict[str, object] = {"lead_time_minutes": lead_time}
        row.update(_metrics_row(config, run, keys))
        row["ci95"] = {
            key: summarise_ci(run, keys)[key]
            for key in ("fill_rate", "profit_per_hour", "stockout_losses")
            if key in summarise_ci(run, keys)
        }
        lead_rows.append(row)
    tables["lead_time_scan"] = lead_rows
    series["lead_time"] = {
        "x": [row["lead_time_minutes"] for row in lead_rows],
        "fill_rate": [row["fill_rate"] for row in lead_rows],
        "stockout_losses": [row["stockout_losses"] for row in lead_rows],
        "profit_per_hour": [row["profit_per_hour"] for row in lead_rows],
    }

    # -- 3. pearl shelf life ----------------------------------------------
    shelf_rows: List[Dict[str, object]] = []
    for shelf_life in SHELF_LIVES:
        config = with_ingredients(
            base, {"pearls": {"shelf_life_minutes": shelf_life}}
        )
        run = run_cell(config)
        row = {"shelf_life_minutes": shelf_life}
        row.update(_metrics_row(config, run, keys))
        shelf_rows.append(row)
    tables["shelf_life_scan"] = shelf_rows
    series["shelf_life"] = {
        "x": [row["shelf_life_minutes"] for row in shelf_rows],
        "waste_units": [row["waste_units"] for row in shelf_rows],
        "profit_per_hour": [row["profit_per_hour"] for row in shelf_rows],
        "fill_rate": [row["fill_rate"] for row in shelf_rows],
    }

    # -- 4. shelf life x pearl lot size interaction ------------------------
    interaction_rows: List[Dict[str, object]] = []
    for shelf_life in PEARLS_SHELF_INTERACTION:
        for S_factor in ss_factors:
            changes = {
                "pearls": {
                    "shelf_life_minutes": shelf_life,
                    "reorder_point": 0.3 * next(
                        ingredient.initial_stock
                        for ingredient in base.inventory.ingredients  # type: ignore[union-attr]
                        if ingredient.name == "pearls"
                    ),
                    "order_quantity": S_factor
                    * next(
                        ingredient.initial_stock
                        for ingredient in base.inventory.ingredients  # type: ignore[union-attr]
                        if ingredient.name == "pearls"
                    ),
                }
            }
            config = with_ingredients(base, changes)
            run = run_cell(config)
            row = {"shelf_life_minutes": shelf_life, "S_factor": S_factor}
            row.update(_metrics_row(config, run, keys))
            interaction_rows.append(row)
    tables["shelf_vs_order_quantity"] = interaction_rows
    series["shelf_order_quantity_waste"] = {
        "shelf_life_minutes": list(PEARLS_SHELF_INTERACTION),
        "S_factors": list(ss_factors),
        "waste_units": [
            [
                row["waste_units"]  # type: ignore[index]
                for row in interaction_rows
                if row["shelf_life_minutes"] == shelf_life
            ]
            for shelf_life in PEARLS_SHELF_INTERACTION
        ],
    }

    # -- 5. pearl lot-size ceiling (where waste starts) --------------------
    ceiling_rows: List[Dict[str, object]] = []
    pearls_initial = next(
        ingredient.initial_stock
        for ingredient in base.inventory.ingredients  # type: ignore[union-attr]
        if ingredient.name == "pearls"
    )
    for S_factor in PEARLS_ORDER_CEILING:
        config = with_ingredients(
            base,
            {"pearls": {"reorder_point": 0.3 * pearls_initial, "order_quantity": S_factor * pearls_initial}},
        )
        run = run_cell(config)
        row = {
            "S_factor": S_factor,
            "order_quantity_units": _r(S_factor * pearls_initial, 3),
        }
        row.update(_metrics_row(config, run, keys))
        ceiling_rows.append(row)
    tables["pearls_order_ceiling"] = ceiling_rows
    series["pearls_order_ceiling"] = {
        "x": [row["order_quantity_units"] for row in ceiling_rows],
        "waste_units": [row["waste_units"] for row in ceiling_rows],
        "fill_rate": [row["fill_rate"] for row in ceiling_rows],
        "profit_per_hour": [row["profit_per_hour"] for row in ceiling_rows],
    }

    # -- 6. lost sales vs substitution ------------------------------------
    scarce = with_ingredients(base, {"ice_mix": SCARCE_ICE})
    pearl_short = with_ingredients(base, {"pearls": SCARCE_PEARLS})
    policy_rows: List[Dict[str, object]] = []
    for regime_name, regime in (
        ("baseline", base),
        ("ice_short", scarce),
        ("pearls_short", pearl_short),
    ):
        for policy_name, policy, substitute in (
            ("lose", "lose", None),
            ("substitute_mix_to_tea", "substitute", ("mix", "tea")),
            ("substitute_ice_to_bread", "substitute", ("ice", "bread")),
        ):
            inventory = regime.inventory
            if inventory is None:  # pragma: no cover - defensive
                raise RuntimeError("scenario has no inventory layer")
            config = replace(
                regime,
                inventory=replace(
                    inventory,
                    stockout_policy=policy,
                    substitute=substitute,
                ),
            )
            run = run_cell(config)
            row = {
                "regime": regime_name,
                "stockout_policy": policy_name,
                "substitute": list(substitute) if substitute else None,
            }
            row.update(_metrics_row(config, run, keys))
            row.update(substitution_outcomes(config))
            policy_rows.append(row)
    tables["stockout_policy"] = policy_rows
    lose_by_regime = {
        str(row["regime"]): row
        for row in policy_rows
        if row["stockout_policy"] == "lose"
    }
    for row in policy_rows:
        reference = lose_by_regime[str(row["regime"])]
        row["profit_delta_vs_lose"] = _r(
            float(row["profit_per_hour"]) - float(reference["profit_per_hour"])
        )
        row["fill_delta_vs_lose"] = _r(
            float(row["fill_rate"]) - float(reference["fill_rate"])
        )
    best_substitution = argmax(
        [row for row in policy_rows if row["stockout_policy"] != "lose"],
        "profit_delta_vs_lose",
    )

    # -- 7. trade-off frontier + decision picks ---------------------------
    grid_rows = tables["ss_joint_grid"]  # type: ignore[assignment]
    frontier = pareto_front(
        grid_rows,
        maximise=("profit_per_hour", "fill_rate"),
        minimise=("waste_units",),
    )
    base_fill = float(tables["baseline"]["metrics"]["fill_rate"])  # type: ignore[index]
    base_profit = float(tables["baseline"]["metrics"]["profit_per_hour"])  # type: ignore[index]
    base_waste = float(tables["baseline"]["metrics"]["waste_units"])  # type: ignore[index]
    adequate = [
        row for row in grid_rows if float(row["fill_rate"]) >= base_fill
    ]
    constraint_satisfied = bool(adequate)
    if not adequate:
        adequate = grid_rows
    waste_start = next(
        (
            row
            for row in ceiling_rows
            if float(row["waste_units"]) > 1.0
        ),
        None,
    )
    lead_ok = [
        row for row in lead_rows if float(row["fill_rate"]) >= 0.95
    ]  # type: ignore[index]
    shelf_ok = [
        row for row in shelf_rows if float(row["waste_units"]) < 1.0
    ]  # type: ignore[index]

    tables["tradeoff"] = {
        "frontier": [
            {
                "s_factor": row["s_factor"],
                "S_factor": row["S_factor"],
                "settings": row["settings"],
                "fill_rate": row["fill_rate"],
                "stockout_losses": row["stockout_losses"],
                "waste_units": row["waste_units"],
                "purchase_cost": row["purchase_cost"],
                "profit_per_hour": row["profit_per_hour"],
            }
            for row in frontier
        ],
        "max_profit": {
            "s_factor": argmax(grid_rows, "profit_per_hour")["s_factor"],  # type: ignore[arg-type]
            "S_factor": argmax(grid_rows, "profit_per_hour")["S_factor"],  # type: ignore[arg-type]
            "profit_per_hour": argmax(grid_rows, "profit_per_hour")["profit_per_hour"],  # type: ignore[arg-type]
            "fill_rate": argmax(grid_rows, "profit_per_hour")["fill_rate"],  # type: ignore[arg-type]
        },
        "max_fill": {
            "s_factor": argmax(grid_rows, "fill_rate")["s_factor"],  # type: ignore[arg-type]
            "S_factor": argmax(grid_rows, "fill_rate")["S_factor"],  # type: ignore[arg-type]
            "fill_rate": argmax(grid_rows, "fill_rate")["fill_rate"],  # type: ignore[arg-type]
            "profit_per_hour": argmax(grid_rows, "fill_rate")["profit_per_hour"],  # type: ignore[arg-type]
        },
        "min_waste": {
            "s_factor": argmin(grid_rows, "waste_units")["s_factor"],  # type: ignore[arg-type]
            "S_factor": argmin(grid_rows, "waste_units")["S_factor"],  # type: ignore[arg-type]
            "waste_units": argmin(grid_rows, "waste_units")["waste_units"],  # type: ignore[arg-type]
            "fill_rate": argmin(grid_rows, "waste_units")["fill_rate"],  # type: ignore[arg-type]
        },
        "best_with_baseline_service": {
            "s_factor": argmax(adequate, "profit_per_hour")["s_factor"],
            "S_factor": argmax(adequate, "profit_per_hour")["S_factor"],
            "profit_per_hour": argmax(adequate, "profit_per_hour")["profit_per_hour"],
            "fill_rate": argmax(adequate, "profit_per_hour")["fill_rate"],
            "waste_units": argmax(adequate, "profit_per_hour")["waste_units"],
            "purchase_cost": argmax(adequate, "profit_per_hour")["purchase_cost"],
            "settings": argmax(adequate, "profit_per_hour")["settings"],
            "constraint_satisfied": constraint_satisfied,
            "minimum_fill_required": _r(base_fill),
        },
        "waste_threshold": {
            "order_quantity_units": waste_start["order_quantity_units"] if waste_start else None,
            "S_factor": waste_start["S_factor"] if waste_start else None,
            "first_waste_units": waste_start["waste_units"] if waste_start else None,
            "pearls_initial_stock": _r(pearls_initial, 3),
        },
        "lead_time_fill_95_max": max(
            (row["lead_time_minutes"] for row in lead_ok), default=None
        ),
        "shelf_life_waste_free_min": min(
            (row["shelf_life_minutes"] for row in shelf_ok), default=None
        ),
    }

    # Which ingredient's (s, S) actually matters?  Repeat the "best profit with
    # no service loss" pick inside each grid (joint, pearls-only, tea-kit-only)
    # so the report can rank the two replenishment levers.
    recommendations: List[Dict[str, object]] = []
    for grid_name in ("ss_joint_grid", "ss_pearls_only", "ss_teakit_only"):
        rows = tables[grid_name]  # type: ignore[index]
        candidates = [row for row in rows if float(row["fill_rate"]) >= base_fill]
        satisfied = bool(candidates)
        chosen = argmax(candidates or rows, "profit_per_hour")
        recommendations.append(
            {
                "grid": grid_name,
                "constraint_satisfied": satisfied,
                "s_factor": chosen["s_factor"],
                "S_factor": chosen["S_factor"],
                "settings": chosen["settings"],
                "fill_rate": chosen["fill_rate"],
                "waste_units": chosen["waste_units"],
                "purchase_cost": chosen["purchase_cost"],
                "profit_per_hour": chosen["profit_per_hour"],
                "profit_delta_vs_baseline": _r(
                    float(chosen["profit_per_hour"]) - base_profit  # type: ignore[arg-type]
                ),
            }
        )
    tables["tradeoff"]["recommendations"] = recommendations  # type: ignore[index]

    # -- 8. one-line decision summary -------------------------------------
    best = tables["tradeoff"]["best_with_baseline_service"]  # type: ignore[index]
    base_cfg = tables["baseline"]["config"]  # type: ignore[index]
    tables["decision_summary"] = {
        "baseline": {
            "fill_rate": _r(base_fill),
            "stockout_losses": tables["baseline"]["metrics"]["stockout_losses"],  # type: ignore[index]
            "waste_units": _r(base_waste),
            "purchase_cost": tables["baseline"]["metrics"]["purchase_cost"],  # type: ignore[index]
            "profit_per_hour": _r(base_profit),
        },
        "recommended_ss": best,
        "profit_gain_per_hour": _r(float(best["profit_per_hour"]) - base_profit),
        "fill_change": _r(float(best["fill_rate"]) - base_fill),
        "waste_change": _r(float(best["waste_units"]) - base_waste),
        "substitution_gain_ice_short": _r(
            max(
                float(row["profit_delta_vs_lose"])
                for row in policy_rows
                if row["regime"] == "ice_short" and row["stockout_policy"] != "lose"
            )
        ),
        "substitution_gain_pearls_short": _r(
            max(
                float(row["profit_delta_vs_lose"])
                for row in policy_rows
                if row["regime"] == "pearls_short" and row["stockout_policy"] != "lose"
            )
        ),
        "best_substitution": {
            "regime": best_substitution["regime"],
            "policy": best_substitution["stockout_policy"],
            "profit_delta_vs_lose": best_substitution["profit_delta_vs_lose"],
            "fill_delta_vs_lose": best_substitution["fill_delta_vs_lose"],
            "substituted_per_rep": best_substitution["substituted_per_rep"],
        },
        "lead_time_effect": {
            row["lead_time_minutes"]: row["fill_rate"] for row in lead_rows
        },
        "scenario_base": {
            "arrival_rate": base.arrival_rate,
            "workers": base.workers,
            "utilization": _r(base.utilization()),
            "policy": base.policy.describe(),
        },
        "baseline_config": base_cfg,
    }

    elapsed = time.perf_counter() - started
    meta = common.meta(
        "layer3_inventory_bom",
        notes=(
            "Layer 3 (inventory / BOM): (s, S) grids on the perishable pearls and the "
            "non-perishable tea kit, serial lead time, pearl shelf life, shelf-life x "
            "lot-size interaction, and lost-sale vs substitution. Baseline scenario "
            "data/scenarios/inventory_lean.json."
        ),
        scenarios=["inventory_lean"],
        seeds={"seed": SEED, "seed_stride": SEED_STRIDE},
        reps=reps_note if not quick else reps_note,
        reps_full=REPS,
        reps_overload=REPS_OVERLOAD,
        overload_utilisation=OVERLOAD_UTILISATION,
        runtime_seconds=_r(elapsed, 2),
        caveats=[
            "fill_rate divides by all arrivals (including the warm-up hour); the money "
            "and served metrics are post-warm-up. Morning stock-outs therefore appear "
            "in fill_rate but not in served.",
            "purchase_cost charges every purchased unit including stock left at closing "
            "and re-charges the opening stock on every replicate, so it must be read "
            "next to fill_rate / stockout_losses.",
            "waste_units is a lower bound: expiry is evaluated lazily when an "
            "ingredient is next touched.",
            "A single outstanding order per ingredient (the engine's (s, S) rule), so an "
            "order quantity below the lead-time demand guarantees a stock-out.",
        ],
        design={
            "s_factors": list(s_factors),
            "S_factors": list(ss_factors),
            "lead_times": list(LEAD_TIMES),
            "shelf_lives": list(SHELF_LIVES),
            "pearls_order_ceiling": list(PEARLS_ORDER_CEILING),
            "scarce_ice": SCARCE_ICE,
            "scarce_pearls": SCARCE_PEARLS,
        },
    )
    return {"meta": meta, "tables": tables, "series": series}


# ---------------------------------------------------------------------------
# Economics / fairness layer (Layer 4)
# ---------------------------------------------------------------------------
def _economics_base():
    return library.load_scenario("campus_rush")


def with_pricing(config, multiplier: float, elasticity: float):
    return replace(
        config,
        pricing=ds.PricingSpec(
            peak_windows=PEAK_WINDOWS,
            peak_price_multiplier=multiplier,
            elasticity=elasticity,
        ),
    )


def with_sla(config, target: float, compensation: float):
    return replace(
        config,
        sla=ds.SlaSpec(target_minutes=target, compensation=compensation),
    )


def high_load_config(config, arrival_rate: float):
    """``campus_rush`` demand + classes, but back to three cross-trained clerks.

    The network layer of ``campus_rush`` hides the queue behind the baristas, so
    the starvation cap has almost nothing to age.  Dropping the network keeps the
    three customer classes and the peak profile while concentrating all work in
    three clerks, which is the high-load split+fast configuration the fairness
    question is about (utilisation = arrival_rate * 2.117 / 3).
    """
    planning = replace(
        config.policy, split_mix=True, fast_priority=True, starvation_cap=None
    )
    return replace(
        config,
        workers=3,
        network=None,
        arrival_rate=arrival_rate,
        policy=planning,
    )


def with_cap(config, cap: Optional[float]):
    return replace(config, policy=replace(config.policy, starvation_cap=cap))


def flex_network(config):
    """Add one tea station slot and a fourth barista from the first peak on."""
    network = config.network
    if network is None:  # pragma: no cover - defensive
        raise RuntimeError("campus_rush lost its network layer")
    stations = tuple(
        replace(station, capacity=4) if station.name == "tea" else station
        for station in network.stations
    )
    staff = replace(
        network.staff,
        counts=(2, 4),
        windows=network.staff.windows + (ds.ShiftWindow("barista", 60.0, 480.0),),  # type: ignore[union-attr]
    )
    return replace(config, network=replace(network, stations=stations, staff=staff))


def class_metrics(run: Dict[str, object]) -> Dict[str, Dict[str, float]]:
    means = run["means"]  # type: ignore[index]
    collected: Dict[str, Dict[str, float]] = {}
    for key, value in means.items():
        if not key.startswith("class_"):
            continue
        body = key[len("class_") :]
        for suffix in ("_mean_los", "_p95_los", "_served"):
            if body.endswith(suffix):
                name = body[: -len(suffix)]
                collected.setdefault(name, {})[suffix[1:]] = _r(value)
                break
    return collected


def _peak_row(run: Dict[str, object]) -> Dict[str, Optional[float]]:
    """Peak-window tail statistics produced by ``run_cell(..., peaks=True)``."""
    peak = run.get("peak")
    if not peak:
        return {}
    return {
        "peak_los_p95": _r(peak["los_p95"]["mean"]),  # type: ignore[index]
        "peak_los_p95_ci95": _r(peak["los_p95"]["ci95"]),  # type: ignore[index]
        "offpeak_los_p95": _r(peak["offpeak_los_p95"]["mean"]),  # type: ignore[index]
        "peak_served_share": _r(peak["served_share"]),  # type: ignore[index]
    }


def _class_gaps(classes: Dict[str, Dict[str, float]]) -> Dict[str, Optional[float]]:
    """Mean- and tail-based spreads between customer classes.

    The engine's ``fairness_gap`` is ``max(mean) - min(mean)``.  A mean-based
    gap and a tail-based gap can move in opposite directions, so both are kept:
    the starvation cap reorders the queue, which flattens the tails while it can
    still widen the spread of the means.
    """
    if len(classes) < 2:
        return {"class_mean_spread": None, "class_p95_spread": None}
    means = [value["mean_los"] for value in classes.values() if "mean_los" in value]
    tails = [value["p95_los"] for value in classes.values() if "p95_los" in value]
    return {
        "class_mean_spread": _r(max(means) - min(means)) if len(means) >= 2 else None,
        "class_p95_spread": _r(max(tails) - min(tails)) if len(tails) >= 2 else None,
    }


def study_economics(quick: bool = False) -> Dict[str, object]:
    started = time.perf_counter()
    base = _economics_base()
    hours = base.sim_minutes / 60.0

    multipliers = PRICE_MULTIPLIERS[:2] if quick else PRICE_MULTIPLIERS
    elasticities = ELASTICITIES[:2] if quick else ELASTICITIES
    targets = SLA_TARGETS[:2] if quick else SLA_TARGETS
    compensations = SLA_COMPENSATIONS[:2] if quick else SLA_COMPENSATIONS
    caps = STARVATION_CAPS[:3] if quick else STARVATION_CAPS
    loads = FAIRNESS_LOADS[:1] if quick else FAIRNESS_LOADS
    refinement = PRICE_REFINEMENT[:1] if quick else PRICE_REFINEMENT

    tables: Dict[str, object] = {}
    series: Dict[str, object] = {}

    # -- baseline ---------------------------------------------------------
    base_run = run_cell(base, peaks=True)
    tables["baseline"] = {
        "config": describe(base),
        "metrics": summarise(base_run, ECONOMIC_KEYS, base),
        "peak": _peak_row(base_run),
        "ci95": summarise_ci(base_run, ECONOMIC_KEYS),
        "by_class": class_metrics(base_run),
    }
    base_profit = float(tables["baseline"]["metrics"]["profit_per_hour"])  # type: ignore[index]
    base_revenue = float(tables["baseline"]["metrics"]["revenue_per_hour"])  # type: ignore[index]
    base_served = float(tables["baseline"]["metrics"]["served"])  # type: ignore[index]

    # -- 1. peak pricing ---------------------------------------------------
    price_rows: List[Dict[str, object]] = []

    def price_cell(multiplier: float, elasticity: float, stage: str) -> Dict[str, object]:
        config = with_pricing(base, multiplier, elasticity)
        run = run_cell(config, peaks=True)
        row: Dict[str, object] = {
            "stage": stage,
            "peak_price_multiplier": multiplier,
            "elasticity": elasticity,
            "demand_factor": _r(multiplier**elasticity),
            "peak_windows": [list(window) for window in PEAK_WINDOWS],
        }
        row.update(summarise(run, ECONOMIC_KEYS, config))
        row.update(_peak_row(run))
        row["served_retained"] = _r(float(row["served"]) / base_served)  # type: ignore[arg-type]
        row["profit_delta_vs_base"] = _r(float(row["profit_per_hour"]) - base_profit)  # type: ignore[arg-type]
        row["revenue_delta_vs_base"] = _r(float(row["revenue_per_hour"]) - base_revenue)  # type: ignore[arg-type]
        row["balk_delta_vs_base"] = _r(float(row["balked"]) - float(tables["baseline"]["metrics"]["balked"]))  # type: ignore[arg-type,index]
        return row

    for elasticity in elasticities:
        for multiplier in multipliers:
            price_rows.append(price_cell(multiplier, elasticity, "grid"))
    tables["pricing_grid"] = price_rows

    refinement_rows: List[Dict[str, object]] = []
    for elasticity in elasticities:
        for multiplier in refinement:
            refinement_rows.append(price_cell(multiplier, elasticity, "refinement"))
    tables["pricing_refinement"] = refinement_rows

    all_price_rows = price_rows + refinement_rows
    # Revenue / profit optima and the largest multiplier that keeps >=97% of the
    # baseline customer count ("service-neutral" price ceiling).
    optima: List[Dict[str, object]] = []
    for elasticity in elasticities:
        rows = [row for row in all_price_rows if row["elasticity"] == elasticity]
        largest = max(float(row["peak_price_multiplier"]) for row in rows)  # type: ignore[arg-type]
        revenue_best = argmax(rows, "revenue_per_hour")
        profit_best = argmax(rows, "profit_per_hour")
        neutral = [
            row for row in rows if float(row["served"]) >= 0.97 * base_served
        ]
        neutral_best = argmax(neutral, "profit_per_hour") if neutral else None
        optima.append(
            {
                "elasticity": elasticity,
                "revenue_max_multiplier": revenue_best["peak_price_multiplier"],
                "revenue_max_per_hour": revenue_best["revenue_per_hour"],
                "revenue_max_served": revenue_best["served"],
                "revenue_max_peak_p95": revenue_best.get("peak_los_p95"),
                "revenue_max_is_boundary": float(revenue_best["peak_price_multiplier"]) == largest,  # type: ignore[arg-type]
                "profit_max_multiplier": profit_best["peak_price_multiplier"],
                "profit_max_per_hour": profit_best["profit_per_hour"],
                "profit_max_served": profit_best["served"],
                "profit_max_los_p95": profit_best["los_p95"],
                "profit_max_peak_p95": profit_best.get("peak_los_p95"),
                "profit_max_is_boundary": float(profit_best["peak_price_multiplier"]) == largest,  # type: ignore[arg-type]
                "service_neutral_multiplier": (
                    neutral_best["peak_price_multiplier"] if neutral_best else None
                ),
                "service_neutral_profit_per_hour": (
                    neutral_best["profit_per_hour"] if neutral_best else None
                ),
                "service_neutral_served_retained": (
                    neutral_best["served_retained"] if neutral_best else None
                ),
                "service_neutral_peak_p95": (
                    neutral_best.get("peak_los_p95") if neutral_best else None
                ),
            }
        )
    tables["pricing_optima"] = optima

    pricing_curves: Dict[str, object] = {}
    for elasticity in elasticities:
        rows = sorted(
            (row for row in all_price_rows if row["elasticity"] == elasticity),
            key=lambda row: float(row["peak_price_multiplier"]),  # type: ignore[arg-type]
        )
        pricing_curves[f"{elasticity:g}"] = {
            "x": [row["peak_price_multiplier"] for row in rows],
            "revenue_per_hour": [row["revenue_per_hour"] for row in rows],
            "profit_per_hour": [row["profit_per_hour"] for row in rows],
            "served": [row["served"] for row in rows],
            "los_p95": [row["los_p95"] for row in rows],
            "peak_los_p95": [row.get("peak_los_p95") for row in rows],
            "balked": [row["balked"] for row in rows],
            "fairness_gap": [row["fairness_gap"] for row in rows],
        }
    series["pricing_curves"] = pricing_curves

    # -- 2. SLA target x compensation -------------------------------------
    sla_rows: List[Dict[str, object]] = []
    for target in targets:
        for compensation in compensations:
            config = with_sla(base, target, compensation)
            run = run_cell(config, peaks=True)
            row: Dict[str, object] = {
                "target_minutes": target,
                "compensation": compensation,
            }
            row.update(summarise(run, ECONOMIC_KEYS, config))
            row.update(_peak_row(run))
            row["compensation_per_hour"] = _r(
                float(row["sla_compensation_total"]) / hours  # type: ignore[arg-type]
            )
            row["profit_delta_vs_no_sla"] = _r(
                float(row["profit_per_hour"]) - base_profit  # type: ignore[arg-type]
            )
            row["compensation_per_served_customer"] = _r(
                float(row["sla_compensation_total"]) / max(1e-9, float(row["served"]))  # type: ignore[arg-type]
            )
            sla_rows.append(row)
    tables["sla_grid"] = sla_rows
    # For each promise length, the cheapest compensation on the grid and what the
    # promise costs relative to no SLA at all.
    promise_rows: List[Dict[str, object]] = []
    for target in targets:
        rows = [row for row in sla_rows if row["target_minutes"] == target]
        cheapest = argmin(rows, "compensation")
        promise_rows.append(
            {
                "target_minutes": target,
                "attainment": cheapest["sla_attainment"],
                "cheapest_compensation": cheapest["compensation"],
                "cheapest_compensation_per_hour": cheapest["compensation_per_hour"],
                "cheapest_profit_per_hour": cheapest["profit_per_hour"],
                "cheapest_profit_delta_vs_no_sla": cheapest["profit_delta_vs_no_sla"],
                "most_expensive_compensation": argmax(rows, "compensation")["compensation"],
                "most_expensive_profit_per_hour": argmax(rows, "compensation")["profit_per_hour"],
                "attainment_identical_across_compensation": len(
                    {round(float(row["sla_attainment"]), 9) for row in rows}  # type: ignore[arg-type]
                )
                == 1,
            }
        )
    tables["sla_promises"] = promise_rows
    best_attainment = argmax(sla_rows, "sla_attainment")
    cheapest_best = min(
        (
            row
            for row in sla_rows
            if row["target_minutes"] == best_attainment["target_minutes"]
        ),
        key=lambda row: float(row["compensation"]),  # type: ignore[arg-type]
    )
    tables["sla_summary"] = {
        "no_sla": {
            "profit_per_hour": tables["baseline"]["metrics"]["profit_per_hour"],  # type: ignore[index]
            "los_p95": tables["baseline"]["metrics"]["los_p95"],  # type: ignore[index]
            "peak_los_p95": tables["baseline"]["peak"]["peak_los_p95"],  # type: ignore[index]
            "mean_los": tables["baseline"]["metrics"]["mean_los"],  # type: ignore[index]
            "served": tables["baseline"]["metrics"]["served"],  # type: ignore[index]
        },
        # No tested promise is met by 100% of customers, so this is the *highest*
        # attainment on the grid at the cheapest compensation that reaches it.
        # The name is the one the report builder reads; read "full" as "closest
        # to full" (see max_attainment below for the number).
        "cheapest_full_attainment": {
            "target_minutes": cheapest_best["target_minutes"],
            "min_compensation": cheapest_best["compensation"],
            "attainment": cheapest_best["sla_attainment"],
            "profit_per_hour": cheapest_best["profit_per_hour"],
            "attainment_is_100pct": float(cheapest_best["sla_attainment"]) >= 0.9999,  # type: ignore[arg-type]
        },
        "max_attainment": {
            "target_minutes": best_attainment["target_minutes"],
            "attainment": best_attainment["sla_attainment"],
            "compensation": best_attainment["compensation"],
            "profit_per_hour": best_attainment["profit_per_hour"],
        },
        "tightest_promise": promise_rows[0] if promise_rows else None,
        "loosest_promise": promise_rows[-1] if promise_rows else None,
        "profit_cost_of_tightest_vs_loosest": (
            _r(
                float(promise_rows[0]["cheapest_profit_per_hour"])
                - float(promise_rows[-1]["cheapest_profit_per_hour"])
            )
            if promise_rows
            else None
        ),
        "attainment_uplift_tightest_to_loosest": (
            _r(
                float(promise_rows[-1]["attainment"])
                - float(promise_rows[0]["attainment"])
            )
            if promise_rows
            else None
        ),
        "worst_case": argmin(sla_rows, "profit_per_hour"),
        "service_is_unchanged_by_sla": all(
            abs(float(row["los_p95"]) - float(tables["baseline"]["metrics"]["los_p95"]))  # type: ignore[index,arg-type]
            < 1e-9
            for row in sla_rows
        ),
    }
    series["sla_curve"] = {
        "rows": [
            {
                "target_minutes": row["target_minutes"],
                "compensation": row["compensation"],
                "attainment": row["sla_attainment"],
                "compensation_total": row["sla_compensation_total"],
                "compensation_per_hour": row["compensation_per_hour"],
                "profit_per_hour": row["profit_per_hour"],
            }
            for row in sla_rows
        ]
    }

    # -- 3. fairness cap at high load --------------------------------------
    fairness_rows: List[Dict[str, object]] = []
    for load in loads:
        config = high_load_config(base, load)
        runs_by_cap: Dict[Optional[float], Dict[str, object]] = {}
        for cap in caps:
            capped = with_cap(config, cap)
            run = run_cell(capped, peaks=True)
            runs_by_cap[cap] = run
            row: Dict[str, object] = {
                "arrival_rate": load,
                "utilisation": _r(capped.utilization()),
                "starvation_cap": cap,
            }
            row.update(summarise(run, ECONOMIC_KEYS, capped))
            row.update(_peak_row(run))
            row["escalations_per_hour"] = _r(
                float(row["starvation_events"]) / hours  # type: ignore[arg-type]
            )
            row["by_class"] = class_metrics(run)
            row.update(_class_gaps(row["by_class"]))  # type: ignore[arg-type]
            row["ci95"] = {
                key: summarise_ci(run, ECONOMIC_KEYS)[key]
                for key in ("profit_per_hour", "los_p95", "fairness_gap")
                if key in summarise_ci(run, ECONOMIC_KEYS)
            }
            fairness_rows.append(row)
        # Pair every cap with the uncapped run of the same load (CRN).
        reference_run = runs_by_cap.get(None)
        for row in fairness_rows:
            if row["arrival_rate"] != load:
                continue
            cap = row["starvation_cap"]
            if cap is None or reference_run is None:
                row["paired_vs_uncapped"] = None
                continue
            row["paired_vs_uncapped"] = paired(
                runs_by_cap[cap],
                reference_run,
                ("profit_per_hour", "los_p95", "fairness_gap", "served", "mean_los"),
            )
    tables["fairness_cap"] = fairness_rows
    primary = [
        row for row in fairness_rows if row["arrival_rate"] == FAIRNESS_PRIMARY
    ] or [row for row in fairness_rows if row["arrival_rate"] == loads[-1]]
    tables["fairness_pareto"] = pareto_front(
        primary, maximise=("profit_per_hour",), minimise=("los_p95", "fairness_gap")
    )
    uncapped_primary = next(
        (row for row in primary if row["starvation_cap"] is None), None
    )
    best_tail = argmin(primary, "los_p95")
    tables["fairness_summary"] = {
        "primary_load": FAIRNESS_PRIMARY,
        "primary_utilisation": (
            primary[0]["utilisation"] if primary else None
        ),
        "uncapped": uncapped_primary,
        "best_tail_protection": best_tail,
        "best_fairness_gap": argmin(primary, "fairness_gap"),
        "max_profit": argmax(primary, "profit_per_hour"),
        "tail_improvement_from_best_cap": (
            _r(
                float(best_tail["los_p95"])
                - float(uncapped_primary["los_p95"])  # type: ignore[arg-type]
            )
            if uncapped_primary
            else None
        ),
        "profit_cost_of_best_tail_cap": (
            _r(
                float(best_tail["profit_per_hour"])
                - float(uncapped_primary["profit_per_hour"])  # type: ignore[arg-type]
            )
            if uncapped_primary
            else None
        ),
        "fairness_gap_change_of_best_tail_cap": (
            _r(
                float(best_tail["fairness_gap"])
                - float(uncapped_primary["fairness_gap"])  # type: ignore[arg-type]
            )
            if uncapped_primary
            else None
        ),
        # The engine's fairness_gap is a *mean* difference; the cap mainly moves
        # the tails.  Both are reported so the two directions cannot be confused.
        "mean_gap_widens_while_tail_gap_narrows": (
            bool(
                float(best_tail["class_mean_spread"])  # type: ignore[arg-type]
                > float(uncapped_primary["class_mean_spread"])  # type: ignore[arg-type]
                and float(best_tail["class_p95_spread"])  # type: ignore[arg-type]
                < float(uncapped_primary["class_p95_spread"])  # type: ignore[arg-type]
            )
            if uncapped_primary
            and best_tail.get("class_p95_spread") is not None
            and uncapped_primary.get("class_p95_spread") is not None
            else None
        ),
        "mean_gap_uncapped": (
            uncapped_primary.get("class_mean_spread") if uncapped_primary else None
        ),
        "mean_gap_best_cap": best_tail.get("class_mean_spread"),
        "tail_gap_uncapped": (
            uncapped_primary.get("class_p95_spread") if uncapped_primary else None
        ),
        "tail_gap_best_cap": best_tail.get("class_p95_spread"),
        "load_sensitivity": [
            {
                "arrival_rate": row["arrival_rate"],
                "starvation_cap": row["starvation_cap"],
                "los_p95": row["los_p95"],
                "profit_per_hour": row["profit_per_hour"],
                "fairness_gap": row["fairness_gap"],
            }
            for row in fairness_rows
        ],
    }
    series["fairness_pareto"] = [
        {
            "starvation_cap": row["starvation_cap"],
            "profit_per_hour": row["profit_per_hour"],
            "los_p95": row["los_p95"],
            "fairness_gap": row["fairness_gap"],
            "starvation_events": row["starvation_events"],
        }
        for row in primary
    ]

    # -- 4. good manager ---------------------------------------------------
    good_policy = replace(
        base.policy, split_mix=True, fast_priority=True, starvation_cap=1.5
    )
    pricing_cell = with_pricing(base, 1.2, -1.0)
    sla_cell = with_sla(base, 5.0, 1.0)
    network_cell = flex_network(base)
    good_manager = replace(
        network_cell,
        pricing=ds.PricingSpec(
            peak_windows=PEAK_WINDOWS, peak_price_multiplier=1.2, elasticity=-1.0
        ),
        sla=ds.SlaSpec(target_minutes=5.0, compensation=1.0),
        policy=good_policy,
    )
    scenario_rows: List[Dict[str, object]] = []
    lever_cells = (
        ("capacity_4th_barista", network_cell),
        ("pricing_1.2_e-1.0", pricing_cell),
        ("sla_5min_1.0", sla_cell),
        ("fairness_cap_1.5", with_cap(base, 1.5)),
        ("good_manager", good_manager),
    )
    for name, config in lever_cells:
        run = run_cell(config, peaks=True)
        row: Dict[str, object] = {"scenario": name, "config": describe(config)}
        row.update(summarise(run, ECONOMIC_KEYS, config))
        row.update(_peak_row(run))
        row["by_class"] = class_metrics(run)
        row.update(_class_gaps(row["by_class"]))  # type: ignore[arg-type]
        row["profit_delta_vs_baseline"] = _r(
            float(row["profit_per_hour"]) - base_profit  # type: ignore[arg-type]
        )
        row["served_change_pct"] = _r(
            100.0 * (float(row["served"]) / base_served - 1.0)  # type: ignore[arg-type]
        )
        row["paired_vs_baseline"] = paired(
            run,
            base_run,
            (
                "profit_per_hour",
                "revenue_per_hour",
                "served",
                "los_p95",
                "fairness_gap",
                "balked",
                "sla_attainment",
                "sla_compensation_total",
            ),
        )
        scenario_rows.append(row)
    tables["good_manager"] = scenario_rows

    good_row = next(row for row in scenario_rows if row["scenario"] == "good_manager")
    tables["management_summary"] = {
        "baseline": {
            "profit_per_hour": _r(base_profit),
            "served": _r(base_served),
            "los_p95": tables["baseline"]["metrics"]["los_p95"],  # type: ignore[index]
            "peak_los_p95": tables["baseline"]["peak"]["peak_los_p95"],  # type: ignore[index]
            "mean_los": tables["baseline"]["metrics"]["mean_los"],  # type: ignore[index]
            "balked": tables["baseline"]["metrics"]["balked"],  # type: ignore[index]
            "fairness_gap": tables["baseline"]["metrics"]["fairness_gap"],  # type: ignore[index]
            "sla_attainment": None,
        },
        "good_manager": {
            "profit_per_hour": good_row["profit_per_hour"],
            "served": good_row["served"],
            "los_p95": good_row["los_p95"],
            "peak_los_p95": good_row["peak_los_p95"],
            "mean_los": good_row["mean_los"],
            "balked": good_row["balked"],
            "fairness_gap": good_row["fairness_gap"],
            "sla_attainment": good_row["sla_attainment"],
            "sla_compensation_total": good_row["sla_compensation_total"],
        },
        "paired_profit_gain": good_row["paired_vs_baseline"]["diff"]["profit_per_hour"],  # type: ignore[index]
        "paired_profit_gain_ci95": good_row["paired_vs_baseline"]["ci95"]["profit_per_hour"],  # type: ignore[index]
        "paired_los_p95_change": good_row["paired_vs_baseline"]["diff"]["los_p95"],  # type: ignore[index]
        "paired_served_change": good_row["paired_vs_baseline"]["diff"]["served"],  # type: ignore[index]
        "lever_ranking_by_profit": sorted(
            (
                {
                    "scenario": row["scenario"],
                    "profit_per_hour": row["profit_per_hour"],
                    "profit_delta_vs_baseline": row["profit_delta_vs_baseline"],
                    "los_p95": row["los_p95"],
                    "peak_los_p95": row["peak_los_p95"],
                }
                for row in scenario_rows
                if row["scenario"] != "good_manager"
            ),
            key=lambda item: float(item["profit_delta_vs_baseline"]),  # type: ignore[arg-type]
            reverse=True,
        ),
    }
    series["good_manager_bars"] = [
        {
            "scenario": row["scenario"],
            "profit_per_hour": row["profit_per_hour"],
            "los_p95": row["los_p95"],
            "peak_los_p95": row["peak_los_p95"],
            "served": row["served"],
            "fairness_gap": row["fairness_gap"],
            "balked": row["balked"],
        }
        for row in scenario_rows
    ]

    elapsed = time.perf_counter() - started
    meta = common.meta(
        "layer4_economics_fairness",
        notes=(
            "Layer 4: peak pricing (multiplier x elasticity on the campus_rush peak "
            "windows), SLA target x compensation, starvation cap at high load "
            "(campus_rush classes and peak profile with the network layer removed, "
            "three cross-trained clerks), and a combined good-manager scenario "
            "compared with the shipped baseline under common random numbers."
        ),
        scenarios=["campus_rush"],
        seeds={"seed": SEED, "seed_stride": SEED_STRIDE},
        reps=(
            "quick smoke run"
            if quick
            else f"{REPS} replicates ({REPS_OVERLOAD} above 0.95 utilisation)"
        ),
        reps_full=REPS,
        reps_overload=REPS_OVERLOAD,
        overload_utilisation=OVERLOAD_UTILISATION,
        runtime_seconds=_r(elapsed, 2),
        caveats=[
            "profit_per_hour subtracts the waiting cost of the served customers only, "
            "so demand shedding (higher price, fewer arrivals) looks profitable twice: "
            "fewer lost sales and less waiting cost. The profit-maximising multiplier "
            "therefore sits at the edge of the tested range and must not be read as a "
            "policy recommendation on its own.",
            "Compensation is a pure transfer: it never changes service times, so "
            "los_p95 is identical across the SLA grid. Only capacity/pricing changes "
            "attainment.",
            "campus_rush has no inventory layer (its scenario file carries no BOM), so "
            "the good-manager scenario covers pricing + SLA + fairness + network. "
            "Cross-layer inventory coupling is out of scope for this study.",
            "The fairness experiment keeps campus_rush's demand profile, classes and "
            "patience, but drops the network layer and sets workers=3 so the queue is "
            "visible to the starvation cap; that is the split+fast high-load cell.",
        ],
        design={
            "peak_windows": [list(window) for window in PEAK_WINDOWS],
            "price_multipliers": list(multipliers),
            "price_refinement": list(refinement),
            "elasticities": list(elasticities),
            "sla_targets": list(targets),
            "sla_compensations": list(compensations),
            "starvation_caps": list(caps),
            "fairness_loads": list(loads),
        },
    )
    return {"meta": meta, "tables": tables, "series": series}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--quick",
        action="store_true",
        help="run a reduced design (smoke test, not report grade)",
    )
    parser.add_argument(
        "--only",
        choices=("inventory", "economics", "both"),
        default="both",
        help="restrict the run to one study (default: both)",
    )
    args = parser.parse_args(argv)

    started = time.perf_counter()
    if args.only in ("inventory", "both"):
        payload = study_inventory(quick=args.quick)
        common.save("inventory_study", payload)
    if args.only in ("economics", "both"):
        payload = study_economics(quick=args.quick)
        common.save("economics_study", payload)
    print(f"total runtime {time.perf_counter() - started:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
