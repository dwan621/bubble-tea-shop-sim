"""Discrete-event simulation engine (baseline and layer configurations).

The shop is one queueing system. A *job* is one uninterruptible block of clerk
or station time. The original model has a single cross-trained clerk pool, fixed
service times, a stationary Poisson arrival stream and one atomic job per
component; that model is kept bit-for-bit identical for its configurations.

the four-layer model adds four optional layers on the same event loop:

* demand: intra-day arrival profile, batch arrivals, customer classes with their
  own order mix and patience distribution, make-time variability;
* supply: stations with finite capacity, staff roles/skills, shift windows and
  breaks, so the bottleneck can move;
* inventory: bills of materials, (s, S) replenishment with lead time, shelf life
  and waste, with lost-sale or substitution on stock-out;
* economics/fairness: time-of-day pricing with demand elasticity, SLA
  compensation and a starvation cap that ages the low-priority queue.

Configurations that use none of the mechanism layers take the ``baseline_compat`` path
(including its future-reservation dispatch rule) and therefore reproduce the
original course scripts exactly. layer configurations use an event-driven dispatch
rule: a job starts as soon as all of its required resources are free.

Conventions
-----------
* All durations are minutes; money is in the report's currency units.
* Arrivals are generated before the event loop starts, from a seeded
  ``random.Random``, so behaviour never changes the random stream.
* Statistics use only customers who arrive after ``warmup_minutes``.
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .data_spec import (
    Ingredient,
    InventorySpec,
    NetworkSpec,
    StaffSpec,
    StationSpec,
)
from .params import BREAD, ICE, MIX, TEA, SimConfig

# Component tags produced by ``ServiceTimes.for_kind``.
COMP_TEA = TEA
COMP_BREAD = BREAD
COMP_ICE = ICE
COMP_MIX_ICE = MIX + "_ice"
COMP_MIX_TEA = MIX + "_tea"
COMP_MIX_ALL = MIX + "_all"

# Event type ordering when several events share a timestamp.
_EV_COMPLETION = 0
_EV_ARRIVAL = 1
_EV_RENEGE = 2
_EV_RESTOCK = 3
_EV_SHIFT = 4


@dataclass
class Job:
    """One uninterruptible block of clerk/station time."""

    job_id: int
    cid: int
    component: str
    ready: float
    duration: float
    priority: int
    seq: int
    station: Optional[str] = None
    skill: Optional[str] = None
    stage: str = "make"  # "make" (atomic baseline job) or "order" (staged job)
    started: Optional[float] = None
    finished: Optional[float] = None
    cancelled: bool = False
    escalated: bool = False

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"Job(id={self.job_id}, comp={self.component!r}, ready={self.ready:.2f}, "
            f"dur={self.duration:.3f}, prio={self.priority})"
        )


@dataclass(frozen=True)
class CustomerPlan:
    """What the demand process decided for one arriving customer."""

    kind: str
    class_name: str = "regular"
    priority: int = 1
    balk_threshold: Optional[float] = None
    renege_threshold: Optional[float] = None
    price_factor: float = 1.0
    delivery: bool = False


@dataclass
class Customer:
    """A customer visit and its timing record."""

    cid: int
    kind: str
    arrival: float
    departure: Optional[float] = None
    abandoned: Optional[str] = None  # balk | renege | stockout
    started: bool = False
    tea_done: Optional[float] = None
    ice_done: Optional[float] = None
    bread_done: Optional[float] = None
    jobs_total: int = 0
    jobs_finished: int = 0
    class_name: str = "regular"
    class_priority: int = 1
    price_factor: float = 1.0
    substituted: bool = False
    order_done: Optional[float] = None

    @property
    def served(self) -> bool:
        return self.departure is not None


@dataclass
class StaffUnit:
    """One clerk: role, skills, availability windows and next free time."""

    role: str
    skills: Tuple[str, ...]
    windows: Tuple[Tuple[float, float], ...] = ()  # empty = always available
    free_at: float = 0.0
    busy_minutes: float = 0.0


@dataclass
class StationState:
    """One physical station with ``capacity`` parallel slots."""

    name: str
    capacity: int
    free_at: List[float] = field(default_factory=list)
    busy_minutes: float = 0.0


@dataclass
class Lot:
    """A FIFO inventory lot with an optional expiry time."""

    quantity: float
    expiry: Optional[float] = None


@dataclass
class IngredientState:
    spec: Ingredient
    lots: List[Lot] = field(default_factory=list)
    on_order: float = 0.0
    purchases: float = 0.0
    consumed: float = 0.0
    waste: float = 0.0

    def position(self) -> float:
        return sum(lot.quantity for lot in self.lots) + self.on_order


@dataclass
class Metrics:
    """Aggregated run statistics (one replicate)."""

    workers: int
    arrival_rate: float
    sim_minutes: float
    warmup_minutes: float
    policy: str
    served: int = 0
    mean_los: float = 0.0
    los_by_kind: Dict[str, float] = field(default_factory=dict)
    mix_los: float = 0.0
    mix_ice_hand: float = 0.0
    util: float = 0.0
    busy_minutes: float = 0.0
    counts: Dict[str, int] = field(default_factory=dict)
    flow_time_total: float = 0.0
    revenue_total: float = 0.0
    revenue_per_hour: float = 0.0
    wage_per_hour: float = 0.0
    waiting_cost_total: float = 0.0
    profit_per_hour: float = 0.0
    balked: int = 0
    reneged: int = 0
    stranded: int = 0  # still in the shop when the modelled day ends
    # -- layer metrics ---------------------------------------------------------
    los_p50: float = 0.0
    los_p90: float = 0.0
    los_p95: float = 0.0
    sla_attainment: Optional[float] = None
    sla_compensation_total: float = 0.0
    by_class: Dict[str, Dict[str, float]] = field(default_factory=dict)
    hourly: List[Dict[str, float]] = field(default_factory=list)
    station_util: Dict[str, float] = field(default_factory=dict)
    fill_rate: Optional[float] = None
    stockout_losses: int = 0
    waste_units: float = 0.0
    purchase_cost: float = 0.0
    ingredient_cost_per_hour: float = 0.0
    starvation_events: int = 0
    fairness_gap: Optional[float] = None
    mean_price_factor: float = 1.0
    staff_minutes_available: float = 0.0
    runs_baseline: bool = True

    def as_dict(self) -> Dict[str, object]:
        return {
            "workers": self.workers,
            "arrival_rate": self.arrival_rate,
            "sim_minutes": self.sim_minutes,
            "warmup_minutes": self.warmup_minutes,
            "policy": self.policy,
            "served": self.served,
            "mean_los": self.mean_los,
            "los_by_kind": dict(self.los_by_kind),
            "mix_los": self.mix_los,
            "mix_ice_hand": self.mix_ice_hand,
            "util": self.util,
            "busy_minutes": self.busy_minutes,
            "counts": dict(self.counts),
            "flow_time_total": self.flow_time_total,
            "revenue_total": self.revenue_total,
            "revenue_per_hour": self.revenue_per_hour,
            "wage_per_hour": self.wage_per_hour,
            "waiting_cost_total": self.waiting_cost_total,
            "profit_per_hour": self.profit_per_hour,
            "balked": self.balked,
            "reneged": self.reneged,
            "stranded": self.stranded,
            "los_p50": self.los_p50,
            "los_p90": self.los_p90,
            "los_p95": self.los_p95,
            "sla_attainment": self.sla_attainment,
            "sla_compensation_total": self.sla_compensation_total,
            "by_class": {name: dict(values) for name, values in self.by_class.items()},
            "hourly": [dict(row) for row in self.hourly],
            "station_util": dict(self.station_util),
            "fill_rate": self.fill_rate,
            "stockout_losses": self.stockout_losses,
            "waste_units": self.waste_units,
            "purchase_cost": self.purchase_cost,
            "ingredient_cost_per_hour": self.ingredient_cost_per_hour,
            "starvation_events": self.starvation_events,
            "fairness_gap": self.fairness_gap,
            "mean_price_factor": self.mean_price_factor,
            "staff_minutes_available": self.staff_minutes_available,
            "runs_baseline": self.runs_baseline,
        }


@dataclass
class SimulationResult:
    config: SimConfig
    seed: int
    customers: List[Customer]
    metrics: Metrics


class Simulation:
    """One replicate of the bubble-tea shop model (baseline or layer configuration)."""

    def __init__(self, config: SimConfig, seed: int = 0, trace: bool = False):
        self.config = config
        self.seed = seed
        self.rnd = random.Random(seed)
        self.original = config.baseline_compat
        self.trace: Optional[List[Dict[str, object]]] = [] if trace else None
        self.now = 0.0
        self.ready: List[Job] = []
        self.events: List[Tuple[float, int, int, object]] = []
        self.customers: List[Customer] = []
        self.jobs: List[Job] = []
        self.busy = 0.0
        self.busy_by_hour: Dict[int, float] = {}
        self.in_system = 0
        self.balked = 0
        self.reneged = 0
        self.stranded = 0
        self.stockout_losses = 0
        self.starvation_events = 0
        self._event_seq = 0
        self._job_seq = 0
        self._demand_hours = config.sim_minutes / 60.0

        if self.original:
            self.worker_free: List[float] = [0.0] * config.workers
            self.staff_units: List[StaffUnit] = []
            self.stations: Dict[str, StationState] = {}
        else:
            self._build_resources()
        self.inventory: Dict[str, IngredientState] = {}
        if config.inventory is not None:
            self._build_inventory(config.inventory)
        self.arrivals = self._generate_arrivals()
        self._schedule_arrivals()
        self._schedule_shift_events()
        self.staff_minutes_available = self._staff_minutes_available()

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------
    def _build_resources(self) -> None:
        network = self.config.network
        self.staff_units = []
        self.stations = {}
        if network is None:
            self.staff_units = [
                StaffUnit("clerk", ("all",), ()) for _ in range(self.config.workers)
            ]
            return
        staff_spec = network.staff
        if staff_spec is None:
            raise ValueError("a network configuration needs a staff specification")
        for role, count, skills in zip(
            staff_spec.roles, staff_spec.counts, staff_spec.skills
        ):
            role_windows = [
                window for window in staff_spec.windows if window.role == role
            ]
            if role_windows:
                if len(role_windows) != count:
                    raise ValueError(
                        f"role {role!r} declares {count} staff but "
                        f"{len(role_windows)} shift windows"
                    )
                for index, window in enumerate(role_windows):
                    spans = self._split_breaks(
                        role, index, window.start_minute, window.end_minute,
                        staff_spec,
                    )
                    self.staff_units.append(StaffUnit(role, tuple(skills), spans))
            else:
                for _ in range(count):
                    self.staff_units.append(StaffUnit(role, tuple(skills), ()))
        for station in network.stations:
            self.stations[station.name] = StationState(
                station.name, station.capacity, [0.0] * station.capacity
            )
        routes = network.route_map()
        known = set(self.stations)
        for component, station_name in routes.items():
            if station_name not in known:
                raise ValueError(
                    f"route {component!r} points at unknown station {station_name!r}"
                )

    def _split_breaks(
        self,
        role: str,
        index: int,
        start: float,
        end: float,
        staff_spec: StaffSpec,
    ) -> Tuple[Tuple[float, float], ...]:
        spans = [(start, end)]
        for break_role, break_start, break_end in staff_spec.breaks:
            if break_role != role:
                continue
            length = break_end - break_start
            shifted_start = break_start + index * length
            shifted_end = shifted_start + length
            if shifted_end > end:
                shifted_start = max(start + 1.0, end - length)
                shifted_end = end
            if shifted_start <= start or shifted_end >= end:
                continue
            updated: List[Tuple[float, float]] = []
            for span_start, span_end in spans:
                if shifted_start <= span_start and shifted_end >= span_end:
                    continue
                if shifted_end <= span_start or shifted_start >= span_end:
                    updated.append((span_start, span_end))
                    continue
                if span_start < shifted_start:
                    updated.append((span_start, shifted_start))
                if shifted_end < span_end:
                    updated.append((shifted_end, span_end))
            spans = updated
        return tuple(spans)

    def _schedule_shift_events(self) -> None:
        boundaries = set()
        for unit in self.staff_units:
            for start, end in unit.windows:
                boundaries.add(start)
                boundaries.add(end)
        for boundary in sorted(boundaries):
            if boundary <= 0:
                continue
            self._push_event(boundary, _EV_SHIFT, None)

    def _staff_minutes_available(self) -> float:
        if self.original:
            return self.config.workers * self.config.sim_minutes
        total = 0.0
        for unit in self.staff_units:
            if unit.windows:
                for start, end in unit.windows:
                    total += max(0.0, end - start)
            else:
                total += self.config.sim_minutes
        return total

    def _station_for(self, component: str) -> Optional[str]:
        network = self.config.network
        if network is None or not network.stations:
            return None
        base = component
        if component == COMP_MIX_ICE:
            base = ICE
        elif component == COMP_MIX_TEA:
            base = TEA
        elif component == COMP_MIX_ALL:
            base = "order"
        return network.route_map().get(component, base)

    def _skill_for(self, station_name: Optional[str]) -> Optional[str]:
        if station_name is None:
            return None
        station = self.config.network.station_map().get(station_name)  # type: ignore[union-attr]
        return station.skill if station is not None else None

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    def _build_inventory(self, spec: InventorySpec) -> None:
        for ingredient in spec.ingredients:
            state = IngredientState(spec=ingredient)
            if ingredient.initial_stock > 0:
                expiry = (
                    ingredient.shelf_life_minutes
                    if ingredient.shelf_life_minutes is not None
                    else None
                )
                state.lots.append(Lot(ingredient.initial_stock, expiry))
                state.purchases = ingredient.initial_stock * ingredient.unit_cost
            self.inventory[ingredient.name] = state
        self._inventory_spec = spec
        self._recipes = spec.recipe_map()

    def _discard_expired(self, name: str, now: float) -> None:
        state = self.inventory[name]
        kept: List[Lot] = []
        for lot in state.lots:
            if lot.expiry is not None and lot.expiry <= now:
                state.waste += lot.quantity
            else:
                kept.append(lot)
        state.lots = kept

    def _available(self, name: str, now: float) -> float:
        self._discard_expired(name, now)
        return sum(lot.quantity for lot in self.inventory[name].lots)

    def _consume(self, name: str, quantity: float, now: float) -> bool:
        state = self.inventory[name]
        available = self._available(name, now)
        self._maybe_reorder(name, now)
        if available + 1e-12 < quantity:
            return False
        remaining = quantity
        for lot in state.lots:
            if remaining <= 0:
                break
            take = min(lot.quantity, remaining)
            lot.quantity -= take
            remaining -= take
        state.lots = [lot for lot in state.lots if lot.quantity > 1e-12]
        state.consumed += quantity
        self._maybe_reorder(name, now)
        return True

    def _maybe_reorder(self, name: str, now: float) -> None:
        state = self.inventory[name]
        ingredient = state.spec
        if ingredient.order_quantity <= 0 or state.on_order > 0:
            return
        if state.position() <= ingredient.reorder_point + 1e-12:
            state.on_order += ingredient.order_quantity
            self._push_event(
                now + ingredient.lead_time_minutes, _EV_RESTOCK, name
            )

    def _restock(self, name: str) -> None:
        state = self.inventory[name]
        ingredient = state.spec
        quantity = ingredient.order_quantity
        if quantity <= 0:
            return
        expiry = (
            self.now + ingredient.shelf_life_minutes
            if ingredient.shelf_life_minutes is not None
            else None
        )
        state.lots.append(Lot(quantity, expiry))
        state.on_order = max(0.0, state.on_order - quantity)
        state.purchases += quantity * ingredient.unit_cost
        self._maybe_reorder(name, self.now)

    def _reserve_ingredients(self, kind: str) -> Tuple[bool, str]:
        """Reserve the BOM for one order; returns (ok, served_kind)."""
        spec = self.config.inventory
        if spec is None:
            return True, kind
        recipe = self._recipes.get(kind)
        if recipe is None:
            return True, kind
        for name, _ in recipe:
            self._available(name, self.now)
            self._maybe_reorder(name, self.now)
        if all(self._available(name, self.now) >= quantity for name, quantity in recipe):
            for name, quantity in recipe:
                self._consume(name, quantity, self.now)
            return True, kind
        if spec.stockout_policy == "substitute" and spec.substitute is not None:
            short, replacement = spec.substitute
            if kind == short:
                replacement_recipe = self._recipes.get(replacement)
                if replacement_recipe is not None and all(
                    self._available(name, self.now) >= quantity
                    for name, quantity in replacement_recipe
                ):
                    for name, quantity in replacement_recipe:
                        self._consume(name, quantity, self.now)
                    return True, replacement
        return False, kind

    # ------------------------------------------------------------------
    # Demand generation
    # ------------------------------------------------------------------
    def _kind_thresholds(self, mix) -> List[Tuple[float, str]]:
        cumulative = mix.as_dict()
        thresholds: List[Tuple[float, str]] = []
        running = 0.0
        for kind in (TEA, BREAD, ICE, MIX):
            running += cumulative[kind]
            thresholds.append((running, kind))
        return thresholds

    def _generate_arrivals(self) -> List[Tuple[float, Tuple[CustomerPlan, ...]]]:
        if self.original:
            return self._generate_arrivals_stationary()
        return self._generate_arrivals_by_profile()

    def _generate_arrivals_stationary(self) -> List[Tuple[float, Tuple[CustomerPlan, ...]]]:
        arrivals: List[Tuple[float, Tuple[CustomerPlan, ...]]] = []
        thresholds = self._kind_thresholds(self.config.mix)
        t = 0.0
        while t < self.config.sim_minutes:
            t += self.rnd.expovariate(self.config.arrival_rate)
            u = self.rnd.random()
            kind = MIX
            for limit, candidate in thresholds:
                if u < limit:
                    kind = candidate
                    break
            arrivals.append((t, (CustomerPlan(kind),)))
        return arrivals

    def _rate_multiplier(self, minute: float) -> float:
        multiplier = self.config.demand.multiplier_at(minute)
        pricing = self.config.pricing
        if pricing is not None:
            multiplier *= pricing.demand_multiplier_at(minute)
        return multiplier

    def _peak_rate_multiplier(self) -> float:
        candidates = [0.0]
        for segment in self.config.demand.segments:
            candidates.append(segment.start_minute)
        if self.config.pricing is not None:
            for start, _end in self.config.pricing.peak_windows:
                candidates.append(start)
        candidates.append(self.config.sim_minutes - 1e-9)
        return max(self._rate_multiplier(minute) for minute in candidates)

    def _generate_arrivals_by_profile(self) -> List[Tuple[float, Tuple[CustomerPlan, ...]]]:
        arrivals: List[Tuple[float, Tuple[CustomerPlan, ...]]] = []
        mix_thresholds = self._kind_thresholds(self.config.mix)
        class_weights = self.config.classes.normalised()
        classes = self.config.classes.classes
        class_thresholds = []
        running = 0.0
        for weight in class_weights:
            running += weight
            class_thresholds.append(running)
        peak = self._peak_rate_multiplier()
        if peak <= 0:
            return arrivals
        lam_max = self.config.arrival_rate * peak
        t = 0.0
        while t < self.config.sim_minutes:
            t += self.rnd.expovariate(lam_max)
            if t >= self.config.sim_minutes:
                continue
            if self.rnd.random() >= self._rate_multiplier(t) / peak:
                continue
            batch_size = self.config.batches.sample_size(self.rnd)
            plans: List[CustomerPlan] = []
            for _ in range(batch_size):
                class_draw = self.rnd.random()
                customer_class = classes[-1]
                for limit, candidate in zip(class_thresholds, classes):
                    if class_draw < limit:
                        customer_class = candidate
                        break
                thresholds = (
                    self._kind_thresholds(customer_class.mix)
                    if customer_class.mix is not None
                    else mix_thresholds
                )
                kind_draw = self.rnd.random()
                kind = MIX
                for limit, candidate in thresholds:
                    if kind_draw < limit:
                        kind = candidate
                        break
                patience = customer_class.patience
                balk = None if customer_class.delivery else patience.sample_balk(self.rnd)
                renege = (
                    None if customer_class.delivery else patience.sample_renege(self.rnd)
                )
                price_factor = 1.0
                if self.config.pricing is not None:
                    price_factor = self.config.pricing.price_multiplier_at(t)
                plans.append(
                    CustomerPlan(
                        kind=kind,
                        class_name=customer_class.name,
                        priority=customer_class.priority,
                        balk_threshold=balk,
                        renege_threshold=renege,
                        price_factor=price_factor,
                        delivery=customer_class.delivery,
                    )
                )
            arrivals.append((t, tuple(plans)))
        return arrivals

    def _schedule_arrivals(self) -> None:
        for arrival, plans in self.arrivals:
            self._push_event(arrival, _EV_ARRIVAL, plans)

    def _push_event(self, time: float, kind: int, payload: object) -> None:
        self._event_seq += 1
        heapq.heappush(self.events, (time, kind, self._event_seq, payload))

    def _trace(self, event: str, **fields: object) -> None:
        if self.trace is None:
            return
        record: Dict[str, object] = {"time": round(self.now, 3), "event": event}
        record.update(fields)
        self.trace.append(record)

    # ------------------------------------------------------------------
    # Priority rules
    # ------------------------------------------------------------------
    def _estimate_wait(self) -> float:
        """Rough expected wait for a customer arriving right now.

        Only staff units that are on shift at ``now`` count towards capacity, so
        a late-joining shift or a break does not make the shop look bigger than
        it is. Uses ``in_system * p_bar / staff`` (Little's Law style estimate).
        """
        in_system = self.in_system + 1
        mean_service = self.config.mean_service_time()
        if self.original:
            staff = self.config.workers
        else:
            on_shift = sum(
                1
                for unit in self.staff_units
                if self._window_covers(unit, self.now, self.now + 1e-9)
            )
            staff = max(1, on_shift)
        return in_system * mean_service / max(1, staff)

    def _base_priority(self, component: str) -> int:
        policy = self.config.policy
        if component in (COMP_BREAD, COMP_ICE):
            return 0 if policy.fast_priority else 1
        if component == COMP_MIX_ICE:
            return 0 if policy.mix_ice_priority == "jump" else 1
        return 1

    def _effective_priority(self, job: Job, now: float) -> int:
        policy = self.config.policy
        if policy.starvation_cap is not None and now - job.ready >= policy.starvation_cap:
            if not job.escalated:
                job.escalated = True
                self.starvation_events += 1
            return 0
        if (
            job.component == COMP_MIX_ICE
            and policy.mix_ice_priority == "dynamic"
            and policy.dynamic_priority_threshold is not None
            and now - job.ready >= policy.dynamic_priority_threshold
            and job.priority > 0
        ):
            return 0
        return job.priority

    def _make_mean(self, component: str) -> float:
        times = self.config.times
        if component in (COMP_TEA, COMP_MIX_TEA):
            return times.tea
        if component == COMP_BREAD:
            return times.bread
        if component in (COMP_ICE, COMP_MIX_ICE):
            return times.ice
        if component == COMP_MIX_ALL:
            return times.tea + times.ice
        return times.order

    def _duration(self, component: str, mean: float) -> float:
        variability = self.config.variability
        if variability.is_fixed():
            return mean
        return variability.sample(self.rnd, mean, variability.cv_for(component))

    def _add_job(
        self,
        customer: Customer,
        component: str,
        mean: float,
        priority: int,
        ready: float,
        stage: str = "make",
        station: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> Job:
        self._job_seq += 1
        job = Job(
            job_id=self._job_seq,
            cid=customer.cid,
            component=component,
            ready=ready,
            duration=self._duration(component, mean),
            priority=priority,
            seq=self._job_seq,
            station=station,
            skill=skill,
            stage=stage,
        )
        self.jobs.append(job)
        self.ready.append(job)
        return job

    def _create_jobs(self, customer: Customer, plan: CustomerPlan) -> None:
        # layer network: the order is taken first, production jobs are created when
        # the order step finishes (so the station bottleneck and the order queue
        # are modelled separately).
        if self.config.network is not None and self.config.network.stations:
            station = self._station_for("order")
            self._add_job(
                customer,
                "order",
                self.config.times.order,
                min(1, plan.priority),
                customer.arrival,
                stage="order",
                station=station,
                skill=self._skill_for(station),
            )
            customer.jobs_total = 1
            return
        station_routes = self.config.network is not None
        created = 0
        for component, mean in self.config.times.for_kind(
            customer.kind, split_mix=self.config.policy.split_mix
        ):
            station = self._station_for(component) if station_routes else None
            self._add_job(
                customer,
                component,
                mean,
                min(self._base_priority(component), plan.priority),
                customer.arrival,
                station=station,
                skill=self._skill_for(station),
            )
            created += 1
        customer.jobs_total = created

    def _create_production_jobs(self, customer: Customer) -> None:
        """Create the make-stage jobs after the order has been taken."""
        kind = customer.kind
        split = self.config.policy.split_mix
        if kind == TEA:
            plan = [(COMP_TEA, self._make_mean(COMP_TEA))]
        elif kind == BREAD:
            plan = [(COMP_BREAD, self._make_mean(COMP_BREAD))]
        elif kind == ICE:
            plan = [(COMP_ICE, self._make_mean(COMP_ICE))]
        elif split:
            plan = [
                (COMP_MIX_ICE, self._make_mean(COMP_MIX_ICE)),
                (COMP_MIX_TEA, self._make_mean(COMP_MIX_TEA)),
            ]
        else:
            # Synchronised delivery: tea first, then ice cream on the same visit.
            plan = [(COMP_MIX_TEA, self._make_mean(COMP_MIX_TEA))]
        made = 0
        for component, mean in plan:
            station = self._station_for(component)
            self._add_job(
                customer,
                component,
                mean,
                min(self._base_priority(component), customer.class_priority),
                self.now,
                station=station,
                skill=self._skill_for(station),
            )
            made += 1
        customer.jobs_total += made

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> SimulationResult:
        hard_stop = self.config.sim_minutes * 10 + 10_000
        while self.events:
            next_time = self.events[0][0]
            if next_time > hard_stop:
                break
            self.now = next_time
            batch: List[Tuple[float, int, int, object]] = []
            while self.events and self.events[0][0] == next_time:
                batch.append(heapq.heappop(self.events))
            for event in batch:
                if event[1] == _EV_COMPLETION:
                    self._complete_job(event[3])  # type: ignore[arg-type]
                elif event[1] == _EV_ARRIVAL:
                    for plan in event[3]:  # type: ignore[union-attr]
                        self._handle_arrival(plan)
                elif event[1] == _EV_RESTOCK:
                    self._restock(event[3])  # type: ignore[arg-type]
            self._dispatch()
            for event in batch:
                if event[1] == _EV_RENEGE:
                    self._handle_renege(event[3])  # type: ignore[arg-type]
        # Anyone still waiting when the last event has been processed was left
        # in the shop at closing time: record it instead of losing the customer.
        for customer in self.customers:
            if customer.departure is None and customer.abandoned is None:
                customer.abandoned = "closed"
                self.stranded += 1
                self.in_system -= 1
                for job in self.jobs:
                    if job.cid == customer.cid:
                        job.cancelled = True
        metrics = self._build_metrics()
        return SimulationResult(
            config=self.config,
            seed=self.seed,
            customers=self.customers,
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _handle_arrival(self, plan: CustomerPlan) -> None:
        customer = Customer(
            cid=len(self.customers),
            kind=plan.kind,
            arrival=self.now,
            class_name=plan.class_name,
            class_priority=plan.priority,
            price_factor=plan.price_factor,
        )
        self.customers.append(customer)
        self._trace(
            "arrival", cid=customer.cid, kind=plan.kind, klass=plan.class_name
        )
        balk_threshold = (
            plan.balk_threshold
            if plan.balk_threshold is not None
            else self.config.policy.balk_threshold
        )
        if not plan.delivery and balk_threshold is not None:
            if self._estimate_wait() > balk_threshold:
                customer.abandoned = "balk"
                self.balked += 1
                self._trace("balk", cid=customer.cid)
                return
        ok, served_kind = self._reserve_ingredients(plan.kind)
        if not ok:
            customer.abandoned = "stockout"
            self.stockout_losses += 1
            self._trace("stockout", cid=customer.cid, kind=plan.kind)
            return
        if served_kind != plan.kind:
            customer.kind = served_kind
            customer.substituted = True
        self.in_system += 1
        self._create_jobs(customer, plan)
        renege_threshold = (
            plan.renege_threshold
            if plan.renege_threshold is not None
            else self.config.policy.renege_threshold
        )
        if not plan.delivery and renege_threshold is not None:
            self._push_event(
                self.now + renege_threshold, _EV_RENEGE, customer.cid
            )

    def _complete_job(self, job: Job) -> None:
        job.finished = self.now
        customer = self.customers[job.cid]
        if job.stage == "order":
            customer.order_done = self.now
            self._create_production_jobs(customer)
        else:
            if job.component in (COMP_TEA, COMP_MIX_TEA, COMP_MIX_ALL):
                customer.tea_done = self.now
            if job.component in (COMP_ICE, COMP_MIX_ICE, COMP_MIX_ALL):
                customer.ice_done = self.now
            if job.component in (COMP_BREAD, COMP_MIX_ALL):
                customer.bread_done = self.now
            if (
                job.component == COMP_MIX_TEA
                and customer.kind == MIX
                and not self.config.policy.split_mix
                and customer.ice_done is None
            ):
                station = self._station_for(COMP_MIX_ICE)
                self._add_job(
                    customer,
                    COMP_MIX_ICE,
                    self._make_mean(COMP_MIX_ICE),
                    min(self._base_priority(COMP_MIX_ICE), customer.class_priority),
                    self.now,
                    station=station,
                    skill=self._skill_for(station),
                )
                customer.jobs_total += 1
        customer.jobs_finished += 1
        if customer.jobs_finished >= customer.jobs_total:
            done = [
                value
                for value in (customer.tea_done, customer.ice_done, customer.bread_done)
                if value is not None
            ]
            customer.departure = max(done) if done else self.now
            self._trace("done", cid=customer.cid, component=job.component)
            self.in_system -= 1

    def _handle_renege(self, cid: int) -> None:
        customer = self.customers[cid]
        if customer.departure is not None or customer.abandoned is not None:
            return
        if customer.started:
            return
        customer.abandoned = "renege"
        self.reneged += 1
        self._trace("renege", cid=cid)
        self.in_system -= 1
        for job in self.jobs:
            if job.cid == cid:
                job.cancelled = True

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def _dispatch(self) -> None:
        if self.original:
            self._dispatch_stationary()
        else:
            self._dispatch_network()

    def _dispatch_stationary(self) -> None:
        while True:
            free = [i for i, t in enumerate(self.worker_free) if t <= self.now]
            if not free:
                return
            candidates = [job for job in self.ready if not job.cancelled]
            if not candidates:
                return
            best = min(
                candidates,
                key=lambda job: (self._effective_priority(job, self.now), job.seq),
            )
            worker = min(free, key=lambda i: (self.worker_free[i], i))
            best.started = self.now
            best.finished = self.now + best.duration
            self.worker_free[worker] = best.finished
            self.ready.remove(best)
            self.busy += best.duration
            self._add_busy_span(self.now, best.finished)
            self.customers[best.cid].started = True
            self._trace(
                "start",
                cid=best.cid,
                component=best.component,
                station=best.station,
            )
            self._push_event(best.finished, _EV_COMPLETION, best)

    def _dispatch_network(self) -> None:
        candidates = sorted(
            (
                job
                for job in self.ready
                if not job.cancelled and job.ready <= self.now + 1e-9
            ),
            key=lambda job: (self._effective_priority(job, self.now), job.seq),
        )
        for job in candidates:
            if job.cancelled:
                continue
            staff = self._find_staff(job)
            if staff is None:
                continue
            slot = self._find_station(job)
            if job.station is not None and slot is None:
                continue
            self._start_job_network(job, staff, slot)

    def _start_job_network(
        self,
        job: Job,
        staff: StaffUnit,
        slot: Optional[Tuple[StationState, int]],
    ) -> None:
        job.started = self.now
        job.finished = self.now + job.duration
        staff.free_at = job.finished
        staff.busy_minutes += job.duration
        if slot is not None:
            station, index = slot
            station.free_at[index] = job.finished
            station.busy_minutes += job.duration
        self.ready.remove(job)
        self.busy += job.duration
        self._add_busy_span(self.now, job.finished)
        self.customers[job.cid].started = True
        self._trace(
            "start",
            cid=job.cid,
            component=job.component,
            station=job.station,
        )
        self._push_event(job.finished, _EV_COMPLETION, job)

    def _find_staff(self, job: Job) -> Optional[StaffUnit]:
        for unit in self.staff_units:
            if unit.free_at > self.now + 1e-12:
                continue
            if job.skill is not None and not self._unit_has_skill(unit, job.skill):
                continue
            if self._window_covers(unit, self.now, self.now + job.duration):
                return unit
        return None

    @staticmethod
    def _unit_has_skill(unit: StaffUnit, skill: str) -> bool:
        return "all" in unit.skills or skill in unit.skills

    def _window_covers(self, unit: StaffUnit, start: float, end: float) -> bool:
        if not unit.windows:
            return True
        return any(
            window_start <= start + 1e-12 and end <= window_end + 1e-12
            for window_start, window_end in unit.windows
        )

    def _find_station(self, job: Job) -> Optional[Tuple[StationState, int]]:
        if job.station is None:
            return None
        station = self.stations.get(job.station)
        if station is None:
            raise ValueError(f"job routed to unknown station {job.station!r}")
        for index, free_at in enumerate(station.free_at):
            if free_at <= self.now + 1e-12:
                return station, index
        return None

    def _add_busy_span(self, start: float, end: float) -> None:
        """Record busy minutes per 60-minute bucket for the hourly series."""
        if end <= start:
            return
        hour = int(start // 60)
        last = int((end - 1e-9) // 60)
        for bucket in range(hour, last + 1):
            bucket_start = bucket * 60
            bucket_end = bucket_start + 60
            overlap = min(end, bucket_end) - max(start, bucket_start)
            if overlap > 0:
                self.busy_by_hour[bucket] = self.busy_by_hour.get(bucket, 0.0) + overlap

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def _build_metrics(self) -> Metrics:
        config = self.config
        warmup = config.warmup_minutes
        included = [
            customer for customer in self.customers if customer.served and customer.arrival >= warmup
        ]
        metrics = Metrics(
            workers=config.workers,
            arrival_rate=config.arrival_rate,
            sim_minutes=config.sim_minutes,
            warmup_minutes=config.warmup_minutes,
            policy=config.policy.describe(),
            runs_baseline=self.original,
        )
        metrics.balked = self.balked
        metrics.reneged = self.reneged
        metrics.stranded = self.stranded
        metrics.busy_minutes = self.busy
        metrics.staff_minutes_available = self.staff_minutes_available

        los: List[float] = []
        by_kind: Dict[str, List[float]] = {TEA: [], BREAD: [], ICE: [], MIX: []}
        mix_los: List[float] = []
        ice_hand: List[float] = []
        revenue = 0.0
        flow_time = 0.0
        sla_late = 0
        sla_compensation = 0.0
        by_class: Dict[str, List[float]] = {}
        price_factor_total = 0.0
        for customer in included:
            los_value = customer.departure - customer.arrival
            los.append(los_value)
            by_kind.setdefault(customer.kind, []).append(los_value)
            by_class.setdefault(customer.class_name, []).append(los_value)
            flow_time += los_value
            revenue += config.economics.price_for(customer.kind) * customer.price_factor
            price_factor_total += customer.price_factor
            if customer.kind == MIX:
                mix_los.append(los_value)
                ice_done = (
                    customer.ice_done
                    if customer.ice_done is not None
                    else customer.tea_done
                )
                if ice_done is not None:
                    ice_hand.append(ice_done - customer.arrival)
            if config.sla is not None and los_value > config.sla.target_minutes:
                sla_late += 1
                sla_compensation += config.sla.compensation

        metrics.served = len(included)
        metrics.mean_los = _mean(los)
        metrics.los_by_kind = {kind: _mean(values) for kind, values in by_kind.items()}
        metrics.mix_los = _mean(mix_los)
        metrics.mix_ice_hand = _mean(ice_hand)
        metrics.counts = {kind: len(values) for kind, values in by_kind.items()}
        metrics.flow_time_total = flow_time
        metrics.los_p50 = _percentile(los, 50)
        metrics.los_p90 = _percentile(los, 90)
        metrics.los_p95 = _percentile(los, 95)
        if config.sla is not None:
            metrics.sla_attainment = (
                1.0 - sla_late / len(included) if included else None
            )
        metrics.sla_compensation_total = sla_compensation
        metrics.by_class = {
            name: {
                "served": float(len(values)),
                "mean_los": _mean(values),
                "p95_los": _percentile(values, 95),
            }
            for name, values in by_class.items()
        }
        if len(by_class) >= 2:
            means = [_mean(values) for values in by_class.values()]
            metrics.fairness_gap = max(means) - min(means)
        metrics.mean_price_factor = (
            price_factor_total / len(included) if included else 1.0
        )

        hours = config.sim_minutes / 60.0
        metrics.revenue_total = revenue
        metrics.revenue_per_hour = revenue / hours
        if config.network is not None and config.network.staff is not None:
            wage_cost = (
                self.staff_minutes_available / 60.0 * config.economics.wage_per_worker_hour
            )
            metrics.wage_per_hour = (
                wage_cost / hours if hours else config.economics.wage_per_worker_hour
            )
        else:
            metrics.wage_per_hour = (
                config.economics.wage_per_worker_hour * config.workers
            )
            wage_cost = metrics.wage_per_hour * hours
        metrics.waiting_cost_total = (
            config.economics.waiting_cost_per_customer_minute * flow_time
        )
        ingredient_cost = sum(
            state.purchases for state in self.inventory.values()
        )
        metrics.purchase_cost = ingredient_cost
        metrics.ingredient_cost_per_hour = ingredient_cost / hours
        metrics.waste_units = sum(state.waste for state in self.inventory.values())
        if config.inventory is not None:
            demand_count = len(self.customers)
            metrics.fill_rate = (
                (demand_count - self.stockout_losses) / demand_count
                if demand_count
                else None
            )
        metrics.stockout_losses = self.stockout_losses
        metrics.profit_per_hour = (
            revenue - sla_compensation - wage_cost - metrics.waiting_cost_total - ingredient_cost
        ) / hours
        metrics.util = (
            self.busy / self.staff_minutes_available
            if self.staff_minutes_available > 0 and not self.original
            else self.busy / (config.workers * config.sim_minutes)
        )
        metrics.starvation_events = self.starvation_events

        station_util = {}
        for name, station in self.stations.items():
            if station.capacity * config.sim_minutes > 0:
                station_util[name] = station.busy_minutes / (
                    station.capacity * config.sim_minutes
                )
        metrics.station_util = station_util

        hourly = []
        bucket_count = int(math.ceil(config.sim_minutes / 60.0))
        for bucket in range(bucket_count):
            hour_start = bucket * 60
            hour_end = min(config.sim_minutes, hour_start + 60)
            arrivals_in_hour = sum(
                1
                for customer in self.customers
                if hour_start <= customer.arrival < hour_end or (
                    bucket == bucket_count - 1 and customer.arrival == config.sim_minutes
                )
            )
            served_in_hour = [
                customer
                for customer in self.customers
                if customer.served
                and hour_start <= customer.departure < hour_end
                and customer.arrival >= warmup
            ]
            hourly.append(
                {
                    "hour_start": float(hour_start),
                    "arrivals": float(arrivals_in_hour),
                    "served": float(len(served_in_hour)),
                    "mean_los": _mean(
                        [customer.departure - customer.arrival for customer in served_in_hour]
                    ),
                    "busy_minutes": self.busy_by_hour.get(bucket, 0.0),
                    "busy_ratio": (
                        self.busy_by_hour.get(bucket, 0.0)
                        / (config.workers * max(1.0, hour_end - hour_start))
                    ),
                }
            )
        metrics.hourly = hourly
        return metrics


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: List[float], percent: float) -> float:
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


def simulate(config: SimConfig, seed: int = 0) -> SimulationResult:
    """Run one replicate."""
    return Simulation(config, seed=seed).run()
