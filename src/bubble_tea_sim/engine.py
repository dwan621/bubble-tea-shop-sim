"""Discrete-event simulation engine for the bubble-tea shop study.

The shop is one queueing system: a pool of cross-trained clerks serves four
order classes (tea, bread, ice cream, and mixed tea + ice cream). A *job* is one
uninterruptible block of clerk time. A pure order is a single job
(order + make), while a mixed order is either one long job (synchronised
delivery) or two jobs (split delivery: the ice cream is handed over first and
the customer leaves when the tea is ready).

The engine is deterministic given a seed and is designed to reproduce the
legacy Python scripts bit-for-bit for the configurations that use fixed service
times (see ``tests/test_legacy_anchors.py``). Behaviour mechanisms (balking,
reneging, dynamic priority) are layered on top of the same scheduling loop.

Conventions
-----------
* All durations are minutes; money is in the report's currency units.
* Arrivals follow a Poisson process with rate ``arrival_rate`` customers/min.
* Arrivals are generated for the whole run up front, mirroring the legacy
  scripts, so the random stream does not depend on run-time behaviour.
* Statistics use only customers who arrive after ``warmup_minutes``.
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .params import BREAD, ICE, MIX, TEA, OrderMix, SimConfig

# Component tags produced by ``ServiceTimes.for_kind``.
COMP_TEA = TEA
COMP_BREAD = BREAD
COMP_ICE = ICE
COMP_MIX_ICE = MIX + "_ice"
COMP_MIX_TEA = MIX + "_tea"
COMP_MIX_ALL = MIX + "_all"

# Event type ordering when several events share a timestamp. Completions first
# (free a clerk), then arrivals, then renege deadlines (handled after dispatch).
_EV_COMPLETION = 0
_EV_ARRIVAL = 1


@dataclass
class Job:
    """One uninterruptible block of clerk time."""

    job_id: int
    cid: int
    component: str
    ready: float
    duration: float
    priority: int
    seq: int
    started: Optional[float] = None
    finished: Optional[float] = None
    cancelled: bool = False

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"Job(id={self.job_id}, comp={self.component!r}, ready={self.ready:.2f}, "
            f"dur={self.duration:.3f}, prio={self.priority})"
        )


@dataclass
class Customer:
    """A customer visit and its timing record."""

    cid: int
    kind: str
    arrival: float
    departure: Optional[float] = None
    abandoned: Optional[str] = None  # "balk" | "renege"
    started: bool = False
    tea_done: Optional[float] = None
    ice_done: Optional[float] = None
    bread_done: Optional[float] = None
    jobs_total: int = 0
    jobs_finished: int = 0

    @property
    def served(self) -> bool:
        return self.departure is not None


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
        }


@dataclass
class SimulationResult:
    config: SimConfig
    seed: int
    customers: List[Customer]
    metrics: Metrics


class Simulation:
    """One replicate of the bubble-tea shop model."""

    def __init__(self, config: SimConfig, seed: int = 0):
        self.config = config
        self.seed = seed
        self.rnd = random.Random(seed)
        self.now = 0.0
        self.worker_free: List[float] = [0.0] * config.workers
        self.ready: List[Job] = []
        self.events: List[Tuple[float, int, int, str, object]] = []
        self.customers: List[Customer] = []
        self.jobs: List[Job] = []
        self.busy = 0.0
        self.in_system = 0
        self.balked = 0
        self.reneged = 0
        self._event_seq = 0
        self._job_seq = 0
        self._arrivals = self._generate_arrivals()
        self._schedule_arrivals()

    # -- arrival stream -----------------------------------------------------
    def _generate_arrivals(self) -> List[Tuple[float, str]]:
        """Generate the Poisson arrival stream and order classes up front.

        Mirrors the legacy scripts: draw the inter-arrival time, then the class
        uniform, and keep the customer whose arrival overshoots the horizon.
        """
        arrivals: List[Tuple[float, str]] = []
        cumulative = self.config.mix.as_dict()
        order = (TEA, BREAD, ICE, MIX)
        thresholds = []
        running = 0.0
        for kind in order:
            running += cumulative[kind]
            thresholds.append((running, kind))
        t = 0.0
        while t < self.config.sim_minutes:
            t += self.rnd.expovariate(self.config.arrival_rate)
            u = self.rnd.random()
            kind = MIX
            for limit, candidate in thresholds:
                if u < limit:
                    kind = candidate
                    break
            arrivals.append((t, kind))
        return arrivals

    def _schedule_arrivals(self) -> None:
        for arrival, kind in self._arrivals:
            self._push_event(arrival, _EV_ARRIVAL, (kind,))

    def _push_event(self, time: float, kind: int, payload: object) -> None:
        self._event_seq += 1
        heapq.heappush(self.events, (time, kind, self._event_seq, payload))

    # -- helpers ------------------------------------------------------------
    def _estimate_wait(self) -> float:
        """Rough expected wait for a customer arriving right now.

        Uses ``in_system * p_bar / workers`` (Little's Law style estimate) so
        the balking rule is explainable without running a second simulation.
        """
        in_system = self.in_system + 1  # include the arriving customer
        mean_service = self.config.mean_service_time()
        return in_system * mean_service / self.config.workers

    def _base_priority(self, component: str) -> int:
        policy = self.config.policy
        if component in (COMP_BREAD, COMP_ICE):
            return 0 if policy.fast_priority else 1
        if component == COMP_MIX_ICE:
            return 0 if policy.mix_ice_priority == "jump" else 1
        return 1

    def _effective_priority(self, job: Job, now: float) -> int:
        policy = self.config.policy
        if (
            job.component == COMP_MIX_ICE
            and policy.mix_ice_priority == "dynamic"
            and policy.dynamic_priority_threshold is not None
            and now - job.ready >= policy.dynamic_priority_threshold
            and job.priority > 0
        ):
            return 0
        return job.priority

    def _create_jobs(self, customer: Customer) -> None:
        components = self.config.times.for_kind(
            customer.kind, split_mix=self.config.policy.split_mix
        )
        for component, duration in components:
            self._job_seq += 1
            job = Job(
                job_id=self._job_seq,
                cid=customer.cid,
                component=component,
                ready=customer.arrival,
                duration=duration,
                priority=self._base_priority(component),
                seq=self._job_seq,
            )
            self.jobs.append(job)
            self.ready.append(job)
        customer.jobs_total = len(components)

    # -- main loop ----------------------------------------------------------
    def run(self) -> SimulationResult:
        # Safety valve: behaviour mechanisms can make the tail long, but a run
        # that needs 10x the modelled horizon is a bug, not a queue.
        hard_stop = self.config.sim_minutes * 10 + 10_000
        while self.events:
            next_time = self.events[0][0]
            if next_time > hard_stop:
                break
            self.now = next_time
            batch: List[Tuple[float, int, int, str, object]] = []
            while self.events and self.events[0][0] == next_time:
                batch.append(heapq.heappop(self.events))
            for event in batch:
                if event[1] == _EV_COMPLETION:
                    self._complete_job(event[3])
                elif event[1] == _EV_ARRIVAL:
                    self._handle_arrival(event[3][0])
            self._dispatch()
            for event in batch:
                if event[1] not in (_EV_COMPLETION, _EV_ARRIVAL):
                    self._handle_renege(event[3])
        # Flush any customers still waiting when the horizon event loop ends.
        metrics = self._build_metrics()
        return SimulationResult(
            config=self.config,
            seed=self.seed,
            customers=self.customers,
            metrics=metrics,
        )

    # -- event handlers -----------------------------------------------------
    def _handle_arrival(self, kind: str) -> None:
        customer = Customer(cid=len(self.customers), kind=kind, arrival=self.now)
        self.customers.append(customer)
        if self.config.policy.balk_threshold is not None:
            if self._estimate_wait() > self.config.policy.balk_threshold:
                customer.abandoned = "balk"
                self.balked += 1
                return
        self.in_system += 1
        self._create_jobs(customer)
        if self.config.policy.renege_threshold is not None:
            deadline = self.now + self.config.policy.renege_threshold
            self._push_event(deadline, 2, customer.cid)

    def _complete_job(self, job: Job) -> None:
        job.finished = self.now
        customer = self.customers[job.cid]
        if job.component in (COMP_TEA, COMP_MIX_TEA, COMP_MIX_ALL):
            customer.tea_done = self.now
        if job.component in (COMP_ICE, COMP_MIX_ICE, COMP_MIX_ALL):
            customer.ice_done = self.now
        if job.component in (COMP_BREAD, COMP_MIX_ALL):
            customer.bread_done = self.now
        customer.jobs_finished += 1
        if customer.jobs_finished >= customer.jobs_total:
            done = [
                value
                for value in (customer.tea_done, customer.ice_done, customer.bread_done)
                if value is not None
            ]
            customer.departure = max(done)
            self.in_system -= 1

    def _handle_renege(self, cid: int) -> None:
        customer = self.customers[cid]
        if customer.departure is not None or customer.abandoned is not None:
            return
        if customer.started:
            return
        customer.abandoned = "renege"
        self.reneged += 1
        self.in_system -= 1
        for job in self.jobs:
            if job.cid == cid:
                job.cancelled = True

    # -- scheduling ---------------------------------------------------------
    def _dispatch(self) -> None:
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
            best.started = self.now
            best.finished = self.now + best.duration
            self.ready.remove(best)
            worker = min(free, key=lambda i: (self.worker_free[i], i))
            self.worker_free[worker] = best.finished
            self.busy += best.duration
            self.customers[best.cid].started = True
            self._push_event(best.finished, _EV_COMPLETION, best)

    # -- metrics ------------------------------------------------------------
    def _build_metrics(self) -> Metrics:
        config = self.config
        warmup = config.warmup_minutes
        included = [
            c
            for c in self.customers
            if c.served and c.arrival >= warmup
        ]
        metrics = Metrics(
            workers=config.workers,
            arrival_rate=config.arrival_rate,
            sim_minutes=config.sim_minutes,
            warmup_minutes=config.warmup_minutes,
            policy=config.policy.describe(),
        )
        metrics.balked = self.balked
        metrics.reneged = self.reneged
        metrics.busy_minutes = self.busy
        metrics.util = self.busy / (config.workers * config.sim_minutes)

        los: List[float] = []
        by_kind: Dict[str, List[float]] = {TEA: [], BREAD: [], ICE: [], MIX: []}
        mix_los: List[float] = []
        ice_hand: List[float] = []
        revenue = 0.0
        flow_time = 0.0
        for customer in included:
            los_value = customer.departure - customer.arrival
            los.append(los_value)
            by_kind[customer.kind].append(los_value)
            flow_time += los_value
            revenue += config.economics.price_for(customer.kind)
            if customer.kind == MIX:
                mix_los.append(los_value)
                ice_done = (
                    customer.ice_done
                    if customer.ice_done is not None
                    else customer.tea_done
                )
                if ice_done is not None:
                    ice_hand.append(ice_done - customer.arrival)

        metrics.served = len(included)
        metrics.mean_los = _mean(los)
        metrics.los_by_kind = {kind: _mean(values) for kind, values in by_kind.items()}
        metrics.mix_los = _mean(mix_los)
        metrics.mix_ice_hand = _mean(ice_hand)
        metrics.counts = {kind: len(values) for kind, values in by_kind.items()}
        metrics.flow_time_total = flow_time

        hours = config.sim_minutes / 60.0
        metrics.revenue_total = revenue
        metrics.revenue_per_hour = revenue / hours
        metrics.wage_per_hour = config.economics.wage_per_worker_hour * config.workers
        metrics.waiting_cost_total = (
            config.economics.waiting_cost_per_customer_minute * flow_time
        )
        metrics.profit_per_hour = (
            revenue
            - metrics.wage_per_hour * hours
            - metrics.waiting_cost_total
        ) / hours
        return metrics


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def simulate(config: SimConfig, seed: int = 0) -> SimulationResult:
    """Run one replicate."""
    return Simulation(config, seed=seed).run()
