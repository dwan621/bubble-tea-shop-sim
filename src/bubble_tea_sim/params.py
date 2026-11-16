"""Configuration objects for the bubble-tea shop simulation.

Everything that the model assumes is explicit here: the order mix, the service
times, the scheduling policy, and the economic parameters used by the report.
Scenarios are built by composing these objects (see :mod:`bubble_tea_sim.scenarios`).

All times are in minutes and all money amounts are in the same (unspecified)
currency unit used throughout the course report.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Mapping, Optional

from .data_spec import (
    BatchSpec,
    DemandProfile,
    InventorySpec,
    MixSpec,
    NetworkSpec,
    PricingSpec,
    ServiceVariability,
    SlaSpec,
)

# Order classes. ``mix`` means "tea + ice cream in one order".
TEA = "tea"
BREAD = "bread"
ICE = "ice"
MIX = "mix"

ORDER_KINDS = (TEA, BREAD, ICE, MIX)


@dataclass(frozen=True)
class OrderMix:
    """Arrival share of each order class (must sum to 1)."""

    tea: float = 0.55
    bread: float = 0.20
    ice: float = 0.05
    mix: float = 0.20

    def as_dict(self) -> Dict[str, float]:
        return {TEA: self.tea, BREAD: self.bread, ICE: self.ice, MIX: self.mix}

    def validate(self) -> "OrderMix":
        total = self.tea + self.bread + self.ice + self.mix
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"order mix must sum to 1.0, got {total!r}")
        if min(self.tea, self.bread, self.ice, self.mix) < 0:
            raise ValueError("order mix shares must be non-negative")
        return self


@dataclass(frozen=True)
class ServiceTimes:
    """Clerk-minutes per job.

    ``order`` is the cashier step (taken once per order); the product times are
    the make steps. A pure order is therefore ``order + product`` long, matching
    the AnyLogic model where the same clerk takes the order and makes the item.
    """

    order: float = 0.5
    tea: float = 2.0
    bread: float = 0.167
    ice: float = 0.333

    def for_kind(self, kind: str, *, split_mix: bool) -> list:
        """Return the ``(component, duration)`` job list for one order class."""
        if kind == TEA:
            return [(TEA, self.order + self.tea)]
        if kind == BREAD:
            return [(BREAD, self.order + self.bread)]
        if kind == ICE:
            return [(ICE, self.order + self.ice)]
        if kind == MIX:
            if split_mix:
                # The ice-cream component owns the order step; the tea component
                # is queued as a normal (slower) job. Total work is unchanged.
                return [(MIX + "_ice", self.order + self.ice), (MIX + "_tea", self.tea)]
            return [(MIX + "_all", self.order + self.tea + self.ice)]
        raise ValueError(f"unknown order kind: {kind!r}")


@dataclass(frozen=True)
class Policy:
    """Scheduling policy knobs.

    ``split_mix``      : hand the ice cream of a mixed order over as soon as it
                         is ready (True) instead of waiting for the tea (False).
    ``fast_priority``  : bread and ice-cream orders jump ahead of tea orders.
    ``balk_threshold`` : customers leave immediately when the estimated wait at
                         arrival exceeds this many minutes (None disables).
    ``renege_threshold``: customers leave when they have waited this many
                         minutes without service starting (None disables).
    ``dynamic_priority_threshold``: escalate the ice component of a mixed order
                         to the fast lane once it has waited this many minutes
                         (only used when ``mix_ice_priority == "dynamic"``).
    ``mix_ice_priority``: when the mixed order is split, should its ice component
                         jump the queue immediately ("jump"), never jump ("fcfs"),
                         or jump only after the melting-risk threshold ("dynamic")?
    """

    split_mix: bool = False
    fast_priority: bool = False
    balk_threshold: Optional[float] = None
    renege_threshold: Optional[float] = None
    dynamic_priority_threshold: Optional[float] = None
    mix_ice_priority: str = "jump"
    starvation_cap: Optional[float] = None  # fairness: max wait before aging to top

    def __post_init__(self) -> None:
        if self.mix_ice_priority not in ("jump", "fcfs", "dynamic"):
            raise ValueError(
                "mix_ice_priority must be 'jump', 'fcfs' or 'dynamic', "
                f"got {self.mix_ice_priority!r}"
            )
        if self.mix_ice_priority == "dynamic" and self.dynamic_priority_threshold is None:
            raise ValueError(
                "mix_ice_priority='dynamic' requires dynamic_priority_threshold"
            )
        if self.starvation_cap is not None and self.starvation_cap <= 0:
            raise ValueError("starvation_cap must be positive when set")

    @property
    def any_behavior(self) -> bool:
        return any(
            value is not None
            for value in (
                self.balk_threshold,
                self.renege_threshold,
                self.dynamic_priority_threshold,
            )
        )

    def describe(self) -> str:
        parts = ["split" if self.split_mix else "synchro"]
        if self.split_mix and self.mix_ice_priority != "jump":
            if self.mix_ice_priority == "fcfs":
                parts.append("mix-ice-fcfs")
            else:
                parts.append(f"mix-ice-dyn>{self.dynamic_priority_threshold:g}m")
        if self.fast_priority:
            parts.append("fast-priority")
        if self.starvation_cap is not None:
            parts.append(f"fairness-cap>{self.starvation_cap:g}m")
        if self.balk_threshold is not None:
            parts.append(f"balk>{self.balk_threshold:g}m")
        if self.renege_threshold is not None:
            parts.append(f"renege>{self.renege_threshold:g}m")
        return "+".join(parts)


@dataclass(frozen=True)
class Economics:
    """Economic parameters used to convert waiting time into money."""

    price_tea: float = 8.0
    price_bread: float = 6.0
    price_ice: float = 2.0
    price_mix: float = 10.0
    wage_per_worker_hour: float = 25.0
    waiting_cost_per_customer_minute: float = 0.5

    def price_for(self, kind: str) -> float:
        if kind == TEA:
            return self.price_tea
        if kind == BREAD:
            return self.price_bread
        if kind == ICE:
            return self.price_ice
        if kind == MIX:
            return self.price_mix
        raise ValueError(f"unknown order kind: {kind!r}")

    def weighted_price(self, mix: OrderMix) -> float:
        shares = mix.as_dict()
        return sum(self.price_for(kind) * share for kind, share in shares.items())


@dataclass(frozen=True)
class SimConfig:
    """A complete, reproducible simulation configuration."""

    name: str = "baseline"
    workers: int = 3
    arrival_rate: float = 1.25  # customers per minute (Poisson arrivals)
    sim_minutes: float = 480.0  # one 8-hour shop day
    warmup_minutes: float = 60.0  # arrivals before this are excluded from metrics
    mix: OrderMix = field(default_factory=OrderMix)
    times: ServiceTimes = field(default_factory=ServiceTimes)
    policy: Policy = field(default_factory=Policy)
    economics: Economics = field(default_factory=Economics)

    # -- mechanism layers (all opt-in; defaults reproduce baseline exactly) --------------
    demand: DemandProfile = field(default_factory=DemandProfile)
    batches: BatchSpec = field(default_factory=BatchSpec)
    classes: MixSpec = field(default_factory=MixSpec)
    variability: ServiceVariability = field(default_factory=ServiceVariability)
    network: Optional[NetworkSpec] = None
    inventory: Optional[InventorySpec] = None
    pricing: Optional[PricingSpec] = None
    sla: Optional[SlaSpec] = None

    def __post_init__(self) -> None:
        if self.workers < 1:
            raise ValueError("workers must be >= 1")
        if self.arrival_rate <= 0:
            raise ValueError("arrival_rate must be positive")
        if self.sim_minutes <= 0:
            raise ValueError("sim_minutes must be positive")
        if not 0 <= self.warmup_minutes < self.sim_minutes:
            raise ValueError("warmup_minutes must be in [0, sim_minutes)")
        self.mix.validate()
        if self.network is not None and self.network.staff is not None:
            for station in self.network.stations:
                if station.skill is None:
                    raise ValueError(
                        f"station {station.name!r} needs a skill in a staffed network"
                    )

    @property
    def baseline_compat(self) -> bool:
        """True when the configuration is exactly the original model.

        The baseline dispatch rule (reserving idle clerks for future jobs) is kept for
        these configurations so the original anchor tables stay bit-for-bit
        identical. Any mechanism layer switches the engine to event-driven dispatch.
        """
        if not self.demand.is_flat():
            return False
        if self.batches.probability != 0.0:
            return False
        if len(self.classes.classes) != 1:
            return False
        customer_class = self.classes.classes[0]
        if (
            customer_class.name != "regular"
            or customer_class.weight != 1.0
            or customer_class.mix is not None
            or customer_class.priority != 1
            or customer_class.patience.balk_mean is not None
            or customer_class.patience.renege_mean is not None
        ):
            return False
        if not self.variability.is_fixed():
            return False
        if any(
            layer is not None
            for layer in (self.network, self.inventory, self.pricing, self.sla)
        ):
            return False
        if self.policy.starvation_cap is not None:
            return False
        return True

    # -- derived quantities -------------------------------------------------
    def mean_service_time(self) -> float:
        """Demand-weighted mean clerk-minutes per customer (``p_bar``)."""
        shares = self.mix.as_dict()
        total = 0.0
        for kind, share in shares.items():
            jobs = self.times.for_kind(kind, split_mix=self.policy.split_mix)
            total += share * sum(duration for _, duration in jobs)
        return total

    def utilization(self) -> float:
        return self.arrival_rate * self.mean_service_time() / self.workers

    def with_policy(self, **changes) -> "SimConfig":
        return replace(self, policy=replace(self.policy, **changes))

    def with_mix(self, **changes) -> "SimConfig":
        return replace(self, mix=replace(self.mix, **changes))

    def describe(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "workers": self.workers,
            "arrival_rate": self.arrival_rate,
            "sim_minutes": self.sim_minutes,
            "warmup_minutes": self.warmup_minutes,
            "mix": self.mix.as_dict(),
            "service_time_mean": self.mean_service_time(),
            "utilization": self.utilization(),
            "policy": self.policy.describe(),
        }


def config_from_dict(data: Mapping[str, object]) -> SimConfig:
    """Build a :class:`SimConfig` from a plain dict (used by the CLI/JSON)."""
    mix = OrderMix(**data.get("mix", {}))
    times = ServiceTimes(**data.get("times", {}))
    policy = Policy(**data.get("policy", {}))
    economics = Economics(**data.get("economics", {}))
    return SimConfig(
        name=data.get("name", "baseline"),
        workers=int(data.get("workers", 3)),
        arrival_rate=float(data.get("arrival_rate", 1.25)),
        sim_minutes=float(data.get("sim_minutes", 480.0)),
        warmup_minutes=float(data.get("warmup_minutes", 60.0)),
        mix=mix,
        times=times,
        policy=policy,
        economics=economics,
    )
