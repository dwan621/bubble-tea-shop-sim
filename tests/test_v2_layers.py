"""v2 layer tests: degenerate equivalence, invariants and directional effects.

The contract is: with every v2 layer switched off the unified engine reproduces
the v1 numbers exactly; with a layer switched on, the mechanism must move the
metrics in the documented direction without breaking conservation.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from bubble_tea_sim import data_spec as ds
from bubble_tea_sim import library, params, scenarios
from bubble_tea_sim.engine import Simulation, simulate


def _run(config, seed=0):
    return Simulation(config, seed=seed).run()


def test_baseline_flat_scenario_is_bit_exact_v1() -> None:
    config = library.load_scenario("baseline_flat")
    assert config.legacy_compat
    legacy = scenarios.legacy_mixed_order(1.25, split_mix=False)
    assert legacy.legacy_compat
    first = _run(config, seed=7).metrics.as_dict()
    second = _run(legacy, seed=7).metrics.as_dict()
    assert first == second


def test_scenario_library_is_complete_and_provenanced() -> None:
    names = library.scenario_names()
    expected = {
        "baseline_flat",
        "bread_counter_bottleneck",
        "campus_rush",
        "cbd_commute",
        "exam_week",
        "flagship_five_staff",
        "ice_cream_bottleneck",
        "inventory_generous",
        "inventory_lean",
        "late_night_study",
        "mall_weekend",
        "network_tea_bottleneck",
        "peak_pricing",
        "rainy_delivery",
        "strict_sla_fairness",
        "tiny_two_staff",
    }
    assert set(names) == expected
    for name in names:
        raw = library.load_raw(name)
        provenance = raw.get("provenance")
        assert provenance, f"{name} lacks provenance"
        for field in ("source", "method", "uncertainty"):
            assert provenance.get(field), f"{name} provenance lacks {field}"
        config = library.load_scenario(name)
        assert config.name == name


def test_demand_profile_creates_peak_hours() -> None:
    config = library.load_scenario("campus_rush")
    result = _run(config, seed=3)
    hourly = result.metrics.hourly
    arrivals = [row["arrivals"] for row in hourly]
    assert max(arrivals) > 1.5 * min(arrivals)
    # Daily mean is normalised so total demand stays close to the quoted rate,
    # allowing for batch arrivals (a batch of n customers is one arrival event).
    batch = config.batches
    expected_size = 1.0 - batch.probability + batch.probability * sum(
        size * weight for size, weight in batch.sizes
    )
    expected = config.arrival_rate * config.sim_minutes * expected_size
    total = sum(1 for customer in result.customers if customer.arrival < config.sim_minutes)
    assert total == pytest.approx(expected, rel=0.15)


def test_customer_classes_and_patience() -> None:
    config = library.load_scenario("campus_rush")
    result = _run(config, seed=5)
    classes = {customer.class_name for customer in result.customers}
    assert {"regular", "student", "delivery"} <= classes
    # Delivery customers never balk, so every balked customer is a walk-in class.
    balked = {customer.class_name for customer in result.customers if customer.abandoned == "balk"}
    assert "delivery" not in balked
    assert result.metrics.by_class
    assert result.metrics.fairness_gap is not None


def test_service_variability_increases_tail_waiting() -> None:
    base = params.SimConfig(
        workers=3,
        arrival_rate=0.9,
        demand=ds.DemandProfile(),
        variability=ds.ServiceVariability(kind="fixed"),
    )
    variable = replace(
        base,
        variability=ds.ServiceVariability(kind="lognormal", tea_cv=0.6, bread_cv=0.3, ice_cv=0.3),
    )
    fixed_summary = [ _run(base, seed=seed).metrics for seed in range(12) ]
    variable_summary = [ _run(variable, seed=seed).metrics for seed in range(12) ]
    fixed_mean = sum(m.mean_los for m in fixed_summary) / 12
    variable_mean = sum(m.mean_los for m in variable_summary) / 12
    fixed_p95 = sum(m.los_p95 for m in fixed_summary) / 12
    variable_p95 = sum(m.los_p95 for m in variable_summary) / 12
    assert variable_mean > fixed_mean
    assert variable_p95 > fixed_p95


def test_exponential_variability_is_never_silently_deterministic() -> None:
    """``kind="exponential"`` implies CV=1 even when the component CV is zero."""
    config = params.SimConfig(
        workers=3,
        arrival_rate=0.9,
        variability=ds.ServiceVariability(kind="exponential"),
    )
    summary = [ _run(config, seed=seed).metrics for seed in range(10) ]
    p95 = sum(m.los_p95 for m in summary) / len(summary)
    fixed = replace(config, variability=ds.ServiceVariability(kind="fixed"))
    fixed_p95 = sum(_run(fixed, seed=seed).metrics.los_p95 for seed in range(10)) / 10
    assert p95 > fixed_p95


def test_network_is_staged_and_shows_bottlenecks() -> None:
    config = library.load_scenario("network_tea_bottleneck")
    result = _run(config, seed=1)
    served = [customer for customer in result.customers if customer.served]
    assert served
    assert all(customer.order_done is not None for customer in served)
    stations = result.metrics.station_util
    assert stations
    # The deliberately undersized tea station is the busiest resource.
    assert max(stations, key=stations.get) == "tea"
    assert result.metrics.station_util["tea"] > result.metrics.station_util["order"]


def test_inventory_stockouts_and_waste() -> None:
    base = library.load_scenario("inventory_lean")
    assert base.inventory is not None

    def custom(ingredient: ds.Ingredient):
        return replace(
            base,
            inventory=ds.InventorySpec(
                ingredients=(ingredient,),
                recipes=(
                    ds.Recipe("tea", ((ingredient.name, 1.0),)),
                    ds.Recipe("bread", ((ingredient.name, 1.0),)),
                    ds.Recipe("ice", ((ingredient.name, 1.0),)),
                    ds.Recipe("mix", ((ingredient.name, 2.0),)),
                ),
            ),
        )

    tight = custom(
        ds.Ingredient("kit", 0.0, 0.0, 0.0, 60.0, unit_cost=1.0)
    )
    tight_metrics = _run(tight, seed=0).metrics
    assert tight_metrics.stockout_losses > 0
    assert tight_metrics.fill_rate is not None and tight_metrics.fill_rate < 0.2

    generous = custom(
        ds.Ingredient("kit", 100_000.0, 0.0, 0.0, 60.0, unit_cost=1.0)
    )
    generous_metrics = _run(generous, seed=0).metrics
    assert generous_metrics.stockout_losses == 0
    assert generous_metrics.fill_rate == pytest.approx(1.0, abs=1e-12)

    # A perishable that is over-ordered expires before it can be consumed.
    perishable = custom(
        ds.Ingredient(
            "pearls", 1000.0, 0.0, 0.0, 0.0, unit_cost=0.6, shelf_life_minutes=60.0
        )
    )
    perishable_metrics = _run(perishable, seed=0).metrics
    assert perishable_metrics.waste_units > 100.0


def test_pricing_and_sla_layers() -> None:
    base = library.load_scenario("baseline_flat")
    pricing = ds.PricingSpec(
        peak_windows=((120.0, 180.0),),
        peak_price_multiplier=1.2,
        elasticity=-1.2,
    )
    sla = ds.SlaSpec(target_minutes=4.0, compensation=2.0)
    with_layers = replace(base, pricing=pricing, sla=sla)
    plain = _run(base, seed=0).metrics
    layered = _run(with_layers, seed=0).metrics
    assert 1.0 < layered.mean_price_factor < 1.2
    assert layered.served < plain.served  # elasticity lowers demand inside the peak
    assert layered.sla_attainment is not None
    assert 0.0 <= layered.sla_attainment <= 1.0
    assert layered.sla_compensation_total >= 0.0
    assert layered.profit_per_hour < plain.profit_per_hour
    no_late = replace(with_layers, sla=ds.SlaSpec(target_minutes=1e6, compensation=2.0))
    assert _run(no_late, seed=0).metrics.sla_compensation_total == 0.0


def test_fairness_cap_ages_the_low_priority_queue() -> None:
    base = library.load_scenario("campus_rush")
    base = replace(base, workers=3, network=None, arrival_rate=1.1)
    capped = replace(
        base, policy=replace(base.policy, starvation_cap=3.0, fast_priority=True)
    )
    uncapped = _run(base, seed=2).metrics
    with_cap = _run(capped, seed=2).metrics
    assert uncapped.starvation_events == 0
    assert with_cap.starvation_events > 0
    assert with_cap.fairness_gap is not None


def test_balk_estimate_counts_only_staff_on_shift() -> None:
    """Late-joining shifts and breaks must not inflate the capacity estimate."""
    network = ds.NetworkSpec(
        staff=ds.StaffSpec(
            roles=("cashier",),
            counts=(2,),
            skills=(("cashier",),),
            windows=(
                ds.ShiftWindow("cashier", 0.0, 480.0),
                ds.ShiftWindow("cashier", 240.0, 480.0),
            ),
        )
    )
    config = params.SimConfig(workers=2, arrival_rate=0.5, network=network)
    simulation = Simulation(config, seed=0)
    simulation.in_system = 8
    simulation.now = 100.0
    early = simulation._estimate_wait()
    simulation.now = 300.0
    late = simulation._estimate_wait()
    assert early > late


def test_sla_fairness_cap_alias_is_mapped_to_the_policy() -> None:
    """``sla.fairness_cap_minutes`` must actually switch the fairness cap on."""
    config = library.load_scenario("strict_sla_fairness")
    assert config.sla is not None
    assert config.sla.fairness_cap_minutes is not None
    assert config.policy.starvation_cap == config.sla.fairness_cap_minutes
    result = _run(config, seed=1)
    assert result.metrics.starvation_events > 0


def test_v2_runs_are_deterministic() -> None:
    config = library.load_scenario("campus_rush")
    first = _run(config, seed=11).metrics.as_dict()
    second = _run(config, seed=11).metrics.as_dict()
    assert first == second
    assert first != _run(config, seed=12).metrics.as_dict()


def test_scenario_library_results_match_the_library() -> None:
    """The committed screening results must cover exactly the committed scenarios."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = root / "results" / "v2" / "scenario_library.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = library.scenario_names()
    assert payload["meta"]["scenario_library"] == names
    assert [row["name"] for row in payload["tables"]["scenarios"]] == names


def test_v2_flow_conservation() -> None:
    for name in library.scenario_names():
        config = library.load_scenario(name)
        result = _run(config, seed=4)
        accounted = (
            sum(1 for customer in result.customers if customer.served)
            + result.metrics.balked
            + result.metrics.reneged
            + result.metrics.stockout_losses
            + result.metrics.stranded
        )
        arrived = len(result.customers)
        assert accounted == arrived, name
