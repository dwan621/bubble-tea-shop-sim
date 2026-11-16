"""Scenario library: JSON scenarios with provenance, loaded into ``SimConfig``.

A scenario file describes one shop/context (campus rush, CBD lunch, mall
weekend, ...). It contains the mechanism layers it needs plus a ``provenance`` block
that records where every assumption came from and how uncertain it is. The
loader turns the file into a :class:`~bubble_tea_sim.params.SimConfig`.

Files live in ``data/scenarios/*.json``. See ``data/README.md`` for the schema.

Example
-------
>>> from bubble_tea_sim.library import load_scenario
>>> config = load_scenario("campus_rush")
>>> config.baseline_compat
False
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import data_spec as ds
from .params import (
    BREAD,
    ICE,
    MIX,
    TEA,
    Economics,
    OrderMix,
    Policy,
    ServiceTimes,
    SimConfig,
)

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"
if not SCENARIO_DIR.exists():  # installed wheel: fall back to the working directory
    SCENARIO_DIR = Path.cwd() / "data" / "scenarios"


def scenario_files() -> List[Path]:
    return sorted(SCENARIO_DIR.glob("*.json"))


def scenario_names() -> List[str]:
    return [path.stem for path in scenario_files()]


def load_raw(name: str) -> Dict[str, object]:
    path = SCENARIO_DIR / f"{name}.json"
    if not path.exists():
        available = ", ".join(scenario_names()) or "<none>"
        raise FileNotFoundError(f"unknown scenario {name!r}; available: {available}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _mix(payload: Optional[Dict[str, float]]) -> OrderMix:
    if not payload:
        return OrderMix()
    return OrderMix(
        tea=float(payload.get(TEA, 0.55)),
        bread=float(payload.get(BREAD, 0.20)),
        ice=float(payload.get(ICE, 0.05)),
        mix=float(payload.get(MIX, 0.20)),
    )


def _times(payload: Optional[Dict[str, float]]) -> ServiceTimes:
    if not payload:
        return ServiceTimes()
    return ServiceTimes(
        order=float(payload.get("order", 0.5)),
        tea=float(payload.get("tea", 2.0)),
        bread=float(payload.get("bread", 0.167)),
        ice=float(payload.get("ice", 0.333)),
    )


def _policy(payload: Optional[Dict[str, object]]) -> Policy:
    if not payload:
        return Policy()
    return Policy(
        split_mix=bool(payload.get("split_mix", False)),
        fast_priority=bool(payload.get("fast_priority", False)),
        balk_threshold=payload.get("balk_threshold"),
        renege_threshold=payload.get("renege_threshold"),
        dynamic_priority_threshold=payload.get("dynamic_priority_threshold"),
        mix_ice_priority=str(payload.get("mix_ice_priority", "jump")),
        starvation_cap=payload.get("starvation_cap"),
    )


def _economics(payload: Optional[Dict[str, float]]) -> Economics:
    if not payload:
        return Economics()
    return Economics(**payload)


def _demand(payload: Optional[Dict[str, object]]) -> Tuple[ds.DemandProfile, float]:
    if not payload:
        return ds.DemandProfile(), 1.0
    segments = tuple(
        ds.DemandSegment(float(start), float(multiplier))
        for start, multiplier in payload.get("segments", [[0.0, 1.0]])  # type: ignore[union-attr]
    )
    profile = ds.DemandProfile(segments=segments)
    return profile, float(payload.get("normalize_daily_mean", 0.0) or 0.0)


def _classes(payload: Optional[Iterable[Dict[str, object]]]) -> ds.MixSpec:
    if not payload:
        return ds.MixSpec()
    classes = []
    for item in payload:
        patience_payload = item.get("patience", {})  # type: ignore[union-attr]
        mix_payload = item.get("mix")  # type: ignore[union-attr]
        classes.append(
            ds.CustomerClass(
                name=str(item.get("name", "regular")),  # type: ignore[union-attr]
                weight=float(item.get("weight", 1.0)),  # type: ignore[union-attr]
                mix=_mix(mix_payload) if mix_payload else None,  # type: ignore[arg-type]
                patience=ds.PatienceSpec(
                    balk_mean=patience_payload.get("balk_mean"),  # type: ignore[union-attr]
                    balk_cv=float(patience_payload.get("balk_cv", 0.5)),  # type: ignore[union-attr]
                    renege_mean=patience_payload.get("renege_mean"),  # type: ignore[union-attr]
                    renege_cv=float(patience_payload.get("renege_cv", 0.5)),  # type: ignore[union-attr]
                ),
                priority=int(item.get("priority", 1)),  # type: ignore[union-attr]
                delivery=bool(item.get("delivery", False)),  # type: ignore[union-attr]
            )
        )
    return ds.MixSpec(classes=tuple(classes))


def _batches(payload: Optional[Dict[str, object]]) -> ds.BatchSpec:
    if not payload:
        return ds.BatchSpec()
    sizes = tuple(
        (int(size), float(weight))
        for size, weight in payload.get("sizes", [[2, 1.0]])  # type: ignore[union-attr]
    )
    return ds.BatchSpec(
        probability=float(payload.get("probability", 0.0)), sizes=sizes  # type: ignore[arg-type]
    )


def _variability(payload: Optional[Dict[str, object]]) -> ds.ServiceVariability:
    if not payload:
        return ds.ServiceVariability()
    return ds.ServiceVariability(
        kind=str(payload.get("kind", "fixed")),
        order_cv=float(payload.get("order_cv", 0.0)),
        tea_cv=float(payload.get("tea_cv", 0.0)),
        bread_cv=float(payload.get("bread_cv", 0.0)),
        ice_cv=float(payload.get("ice_cv", 0.0)),
    )


def _network(payload: Optional[Dict[str, object]]) -> Optional[ds.NetworkSpec]:
    if not payload:
        return None
    stations = tuple(
        ds.StationSpec(
            name=str(item["name"]),
            capacity=int(item.get("capacity", 1)),
            skill=item.get("skill"),
        )
        for item in payload.get("stations", [])  # type: ignore[union-attr]
    )
    staff_payload = payload.get("staff")
    staff = None
    if staff_payload:
        windows_payload = staff_payload.get("windows", [])  # type: ignore[union-attr]
        windows = tuple(
            ds.ShiftWindow(
                role=str(item["role"]),
                start_minute=float(item.get("start", 0)),
                end_minute=float(item.get("end", 480)),
            )
            for item in windows_payload
        )
        breaks = tuple(
            (str(item["role"]), float(item["start"]), float(item["end"]))
            for item in staff_payload.get("breaks", [])  # type: ignore[union-attr]
        )
        staff = ds.StaffSpec(
            roles=tuple(staff_payload.get("roles", ["clerk"])),  # type: ignore[arg-type]
            counts=tuple(int(count) for count in staff_payload.get("counts", [3])),  # type: ignore[arg-type]
            skills=tuple(
                tuple(skill_list)
                for skill_list in staff_payload.get("skills", [["all"]])  # type: ignore[arg-type]
            ),
            windows=windows,
            breaks=breaks,
        )
    routes = tuple(
        (str(component), str(station))
        for component, station in payload.get("routes", [])  # type: ignore[union-attr]
    )
    return ds.NetworkSpec(stations=stations, staff=staff, routes=routes)


def _inventory(payload: Optional[Dict[str, object]]) -> Optional[ds.InventorySpec]:
    if not payload:
        return None
    ingredients = tuple(
        ds.Ingredient(
            name=str(item["name"]),
            initial_stock=float(item.get("initial_stock", 0)),
            reorder_point=float(item.get("reorder_point", 0)),
            order_quantity=float(item.get("order_quantity", 0)),
            lead_time_minutes=float(item.get("lead_time_minutes", 60)),
            unit_cost=float(item.get("unit_cost", 0.0)),
            shelf_life_minutes=item.get("shelf_life_minutes"),
        )
        for item in payload.get("ingredients", [])  # type: ignore[union-attr]
    )
    recipes = tuple(
        ds.Recipe(
            product=str(item["product"]),
            components=tuple(
                (str(name), float(quantity))
                for name, quantity in item.get("components", [])  # type: ignore[union-attr]
            ),
        )
        for item in payload.get("recipes", [])  # type: ignore[union-attr]
    )
    substitute = payload.get("substitute")
    return ds.InventorySpec(
        ingredients=ingredients,
        recipes=recipes,
        stockout_policy=str(payload.get("stockout_policy", "lose")),
        substitute=tuple(substitute) if substitute else None,  # type: ignore[arg-type]
    )


def _pricing(payload: Optional[Dict[str, object]]) -> Optional[ds.PricingSpec]:
    if not payload:
        return None
    windows = tuple(
        (float(start), float(end))
        for start, end in payload.get("peak_windows", [])  # type: ignore[union-attr]
    )
    return ds.PricingSpec(
        peak_windows=windows,
        peak_price_multiplier=float(payload.get("peak_price_multiplier", 1.0)),
        elasticity=float(payload.get("elasticity", -1.5)),
    )


def _sla(payload: Optional[Dict[str, object]]) -> Optional[ds.SlaSpec]:
    if not payload:
        return None
    return ds.SlaSpec(
        target_minutes=float(payload.get("target_minutes", 5.0)),
        compensation=float(payload.get("compensation", 2.0)),
        fairness_cap_minutes=payload.get("fairness_cap_minutes"),
    )


def build_config(payload: Dict[str, object]) -> SimConfig:
    """Turn one scenario dict into a :class:`SimConfig`."""
    base = dict(payload.get("base", {}))  # type: ignore[arg-type]
    demand, normalize = _demand(payload.get("demand"))
    arrival_rate = float(base.get("arrival_rate", 1.25))
    if normalize:
        arrival_rate = arrival_rate / demand.daily_mean_multiplier(
            float(base.get("sim_minutes", 480.0))
        )
    policy = _policy(payload.get("policy"))  # type: ignore[arg-type]
    sla = _sla(payload.get("sla"))  # type: ignore[arg-type]
    # ``sla.fairness_cap_minutes`` is a convenience alias for the fairness knob;
    # an explicit ``policy.starvation_cap`` always wins.
    if (
        sla is not None
        and sla.fairness_cap_minutes is not None
        and policy.starvation_cap is None
    ):
        from dataclasses import replace as _replace

        policy = _replace(policy, starvation_cap=sla.fairness_cap_minutes)
    return SimConfig(
        name=str(payload.get("name", "scenario")),
        workers=int(base.get("workers", 3)),
        arrival_rate=arrival_rate,
        sim_minutes=float(base.get("sim_minutes", 480.0)),
        warmup_minutes=float(base.get("warmup_minutes", 60.0)),
        mix=_mix(payload.get("mix")),  # type: ignore[arg-type]
        times=_times(payload.get("times")),  # type: ignore[arg-type]
        policy=policy,
        economics=_economics(payload.get("economics")),  # type: ignore[arg-type]
        demand=demand,
        batches=_batches(payload.get("batches")),  # type: ignore[arg-type]
        classes=_classes(payload.get("classes")),  # type: ignore[arg-type]
        variability=_variability(payload.get("variability")),  # type: ignore[arg-type]
        network=_network(payload.get("network")),  # type: ignore[arg-type]
        inventory=_inventory(payload.get("inventory")),  # type: ignore[arg-type]
        pricing=_pricing(payload.get("pricing")),  # type: ignore[arg-type]
        sla=sla,
    )


def load_scenario(name: str) -> SimConfig:
    return build_config(load_raw(name))


def load_all() -> Dict[str, SimConfig]:
    return {name: load_scenario(name) for name in scenario_names()}


def with_overrides(config: SimConfig, **changes) -> SimConfig:
    """Small helper for sweeps: ``with_overrides(cfg, arrival_rate=1.0)``."""
    from dataclasses import replace

    policy_changes = changes.pop("policy", None)
    if policy_changes:
        config = replace(config, policy=replace(config.policy, **policy_changes))
    return replace(config, **changes)
