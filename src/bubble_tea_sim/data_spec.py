"""Specification objects: demand, service variability, network, inventory, pricing.

baseline modelled one clerk pool with fixed service times and a stationary Poisson
arrival stream. the four-layer model keeps that model as the special case ``baseline_compat`` and
adds four optional layers on top:

1. **Demand** - intra-day arrival profile, batch arrivals, heterogeneous
   customer classes with their own order mix and patience distribution.
2. **Supply network** - stations with finite capacity, staff roles with skills,
   shift windows and breaks, so policies can be tested against a moving
   bottleneck.
3. **Inventory / BOM** - ingredient bills of materials, (s, S) replenishment
   with lead time, shelf life and waste.
4. **Economics / fairness** - time-of-day pricing with demand elasticity, SLA
   compensation and a starvation cap for the low-priority queue.

Every object is frozen and hashable so configurations stay reproducible and can
be serialised to JSON. Defaults are chosen so that leaving a layer `None` keeps
the baseline behaviour bit-for-bit.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DemandSegment:
    """A piecewise-constant multiplier on the base arrival rate."""

    start_minute: float
    multiplier: float

    def __post_init__(self) -> None:
        if self.multiplier < 0:
            raise ValueError("demand multiplier must be non-negative")


@dataclass(frozen=True)
class DemandProfile:
    """Intra-day demand curve (e.g. lunch and after-work peaks)."""

    segments: Tuple[DemandSegment, ...] = (DemandSegment(0.0, 1.0),)

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("demand profile needs at least one segment")
        if self.segments[0].start_minute != 0.0:
            raise ValueError("first demand segment must start at minute 0")
        previous = -1.0
        for segment in self.segments:
            if segment.start_minute <= previous:
                raise ValueError("demand segments must be ordered by start_minute")
            previous = segment.start_minute

    def multiplier_at(self, minute: float) -> float:
        multiplier = self.segments[0].multiplier
        for segment in self.segments:
            if minute >= segment.start_minute:
                multiplier = segment.multiplier
            else:
                break
        return multiplier

    def peak_multiplier(self) -> float:
        return max(segment.multiplier for segment in self.segments)

    def daily_mean_multiplier(self, sim_minutes: float) -> float:
        """Average multiplier over the modelled day (used to keep daily demand fixed)."""
        total = 0.0
        for index, segment in enumerate(self.segments):
            start = segment.start_minute
            end = (
                self.segments[index + 1].start_minute
                if index + 1 < len(self.segments)
                else sim_minutes
            )
            if end > start:
                total += segment.multiplier * (min(end, sim_minutes) - start)
        return total / sim_minutes if sim_minutes > 0 else 1.0

    def is_flat(self) -> bool:
        return len(self.segments) == 1 and self.segments[0].multiplier == 1.0


def flat_profile() -> DemandProfile:
    return DemandProfile()


@dataclass(frozen=True)
class BatchSpec:
    """Some arrivals are groups (students, families, delivery riders' orders)."""

    probability: float = 0.0
    sizes: Tuple[Tuple[int, float], ...] = ((2, 0.6), (3, 0.3), (4, 0.1))

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("batch probability must be in [0, 1]")
        total = sum(weight for _, weight in self.sizes)
        if abs(total - 1.0) > 1e-9:
            raise ValueError("batch size weights must sum to 1")

    def sample_size(self, rnd: random.Random) -> int:
        if self.probability == 0.0 or rnd.random() >= self.probability:
            return 1
        draw = rnd.random()
        cumulative = 0.0
        for size, weight in self.sizes:
            cumulative += weight
            if draw < cumulative:
                return size
        return self.sizes[-1][0]


@dataclass(frozen=True)
class PatienceSpec:
    """Balking / reneging thresholds drawn per customer (lognormal, mean + CV)."""

    balk_mean: Optional[float] = None
    balk_cv: float = 0.5
    renege_mean: Optional[float] = None
    renege_cv: float = 0.5

    def __post_init__(self) -> None:
        for value in (self.balk_mean, self.renege_mean):
            if value is not None and value <= 0:
                raise ValueError("patience means must be positive")
        for cv in (self.balk_cv, self.renege_cv):
            if cv < 0:
                raise ValueError("patience CV must be non-negative")

    def sample_balk(self, rnd: random.Random) -> Optional[float]:
        return _sample_lognormal(rnd, self.balk_mean, self.balk_cv)

    def sample_renege(self, rnd: random.Random) -> Optional[float]:
        return _sample_lognormal(rnd, self.renege_mean, self.renege_cv)


@dataclass(frozen=True)
class CustomerClass:
    """A customer segment with its own order mix, patience and queue priority."""

    name: str = "regular"
    weight: float = 1.0
    mix: Optional["OrderMixLike"] = None  # OrderMix instance (avoid circular import)
    patience: PatienceSpec = field(default_factory=PatienceSpec)
    priority: int = 1  # lower number = more important, same convention as jobs
    delivery: bool = False  # delivery orders cannot balk once accepted


@dataclass(frozen=True)
class MixSpec:
    """Weighted mixture of customer classes."""

    classes: Tuple[CustomerClass, ...] = (CustomerClass(),)

    def __post_init__(self) -> None:
        if not self.classes:
            raise ValueError("at least one customer class is required")
        total = sum(customer_class.weight for customer_class in self.classes)
        if total <= 0:
            raise ValueError("customer class weights must be positive")
        for customer_class in self.classes:
            if customer_class.weight < 0:
                raise ValueError("customer class weights must be non-negative")

    def normalised(self) -> Tuple[float, ...]:
        total = sum(customer_class.weight for customer_class in self.classes)
        return tuple(customer_class.weight / total for customer_class in self.classes)


# ---------------------------------------------------------------------------
# Service variability
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ServiceVariability:
    """Make-time variability. ``fixed`` reproduces baseline exactly."""

    kind: str = "fixed"  # fixed | exponential | lognormal | gamma
    order_cv: float = 0.0
    tea_cv: float = 0.0
    bread_cv: float = 0.0
    ice_cv: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in ("fixed", "exponential", "lognormal", "gamma"):
            raise ValueError(f"unknown service variability kind: {self.kind!r}")
        for cv in (self.order_cv, self.tea_cv, self.bread_cv, self.ice_cv):
            if cv < 0:
                raise ValueError("service variability CV must be non-negative")
        if self.kind == "fixed" and max(
            self.order_cv, self.tea_cv, self.bread_cv, self.ice_cv
        ) > 0:
            raise ValueError("fixed variability requires zero CVs")

    def cv_for(self, component: str) -> float:
        if component == "order":
            return self.order_cv
        if component == "tea":
            return self.tea_cv
        if component == "bread":
            return self.bread_cv
        if component in ("ice", "mix_ice"):
            return self.ice_cv
        return 0.0

    def is_fixed(self) -> bool:
        return self.kind == "fixed"

    def sample(self, rnd: random.Random, mean: float, cv: float) -> float:
        """Draw one make time.

        ``exponential`` always samples an exponential (CV = 1 by definition), so
        a configuration that says ``kind="exponential"`` is never silently
        deterministic. ``lognormal``/``gamma`` degenerate to the mean when the
        component CV is zero; ``fixed`` always returns the mean.
        """
        if self.kind == "fixed":
            return mean
        if self.kind == "exponential":
            return rnd.expovariate(1.0 / mean)
        if cv == 0.0:
            return mean
        if self.kind == "lognormal":
            return _sample_lognormal(rnd, mean, cv, required=True)
        # gamma with shape 1/cv^2 and scale mean*cv^2
        shape = 1.0 / (cv * cv)
        scale = mean * cv * cv
        return rnd.gammavariate(shape, scale)


# ---------------------------------------------------------------------------
# Supply network
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StationSpec:
    """A physical station with finite capacity (order counter, tea machine, ...)."""

    name: str
    capacity: int = 1
    skill: Optional[str] = None  # staff skill required to operate it

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("station capacity must be >= 1")


@dataclass(frozen=True)
class ShiftWindow:
    """One staff member's availability window (one role instance)."""

    role: str
    start_minute: float
    end_minute: float

    def __post_init__(self) -> None:
        if self.end_minute <= self.start_minute:
            raise ValueError("shift window must have positive length")


@dataclass(frozen=True)
class StaffSpec:
    """Staff roles, skills, shift windows and breaks.

    ``windows`` may be empty, in which case every staff unit is available for the
    whole run (the baseline behaviour). ``breaks`` split a role's window into two.
    """

    roles: Tuple[str, ...] = ("clerk",)
    counts: Tuple[int, ...] = (3,)
    skills: Tuple[Tuple[str, ...], ...] = (("all",),)
    windows: Tuple[ShiftWindow, ...] = ()
    breaks: Tuple[Tuple[str, float, float], ...] = ()  # (role, start, end)

    def __post_init__(self) -> None:
        if len(self.roles) != len(self.counts) or len(self.roles) != len(self.skills):
            raise ValueError("roles, counts and skills must have equal length")
        if any(count < 0 for count in self.counts):
            raise ValueError("staff counts must be non-negative")
        for break_item in self.breaks:
            if break_item[2] <= break_item[1]:
                raise ValueError("break must have positive length")

    def total_staff(self) -> int:
        return sum(self.counts)


@dataclass(frozen=True)
class NetworkSpec:
    """The physical process: stations plus the staff that operate them.

    ``routes`` maps a job component (``tea``, ``bread``, ``ice``, ``mix_ice``,
    ``mix_tea``, ``mix_all``) to a station name. Components without a route fall
    back to their base component name.

    When ``stations`` is empty and ``staff`` is None the engine uses the baseline
    single clerk pool and one atomic job per component.
    """

    stations: Tuple[StationSpec, ...] = ()
    staff: Optional[StaffSpec] = None
    routes: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        names = [station.name for station in self.stations]
        if len(names) != len(set(names)):
            raise ValueError("station names must be unique")

    def station_map(self) -> Dict[str, StationSpec]:
        return {station.name: station for station in self.stations}

    def route_map(self) -> Dict[str, str]:
        return dict(self.routes)


# ---------------------------------------------------------------------------
# Inventory / BOM
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ingredient:
    """One stocked ingredient with (s, S) replenishment and optional shelf life."""

    name: str
    initial_stock: float
    reorder_point: float
    order_quantity: float
    lead_time_minutes: float
    unit_cost: float = 0.0
    shelf_life_minutes: Optional[float] = None  # None = does not perish

    def __post_init__(self) -> None:
        if self.initial_stock < 0:
            raise ValueError("initial stock must be non-negative")
        if self.reorder_point < 0 or self.order_quantity < 0:
            raise ValueError("reorder point and order quantity must be non-negative")
        if self.lead_time_minutes < 0:
            raise ValueError("lead time must be non-negative")
        if self.shelf_life_minutes is not None and self.shelf_life_minutes <= 0:
            raise ValueError("shelf life must be positive when set")


@dataclass(frozen=True)
class Recipe:
    """Bill of materials for one order class."""

    product: str  # tea | bread | ice | mix
    components: Tuple[Tuple[str, float], ...]

    def __post_init__(self) -> None:
        for name, quantity in self.components:
            if quantity <= 0:
                raise ValueError(f"BOM quantity for {name!r} must be positive")


@dataclass(frozen=True)
class InventorySpec:
    """Inventory layer: recipes, stocks, replenishment and stock-out policy."""

    ingredients: Tuple[Ingredient, ...]
    recipes: Tuple[Recipe, ...]
    stockout_policy: str = "lose"  # lose | substitute
    substitute: Optional[Tuple[str, str]] = None  # (short product, substitute product)

    def __post_init__(self) -> None:
        names = [ingredient.name for ingredient in self.ingredients]
        if len(names) != len(set(names)):
            raise ValueError("ingredient names must be unique")
        if self.stockout_policy not in ("lose", "substitute"):
            raise ValueError("stockout_policy must be 'lose' or 'substitute'")
        if self.stockout_policy == "substitute" and self.substitute is None:
            raise ValueError("substitute policy needs a substitute mapping")
        products = [recipe.product for recipe in self.recipes]
        if len(products) != len(set(products)):
            raise ValueError("recipes must be unique per product")

    def recipe_map(self) -> Dict[str, Tuple[Tuple[str, float], ...]]:
        return {recipe.product: recipe.components for recipe in self.recipes}


# ---------------------------------------------------------------------------
# Pricing / SLA
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PricingSpec:
    """Time-of-day pricing with a constant-elasticity demand response."""

    peak_windows: Tuple[Tuple[float, float], ...] = ()  # (start, end) minutes
    peak_price_multiplier: float = 1.0
    elasticity: float = -1.5

    def __post_init__(self) -> None:
        if self.peak_price_multiplier <= 0:
            raise ValueError("price multiplier must be positive")
        if self.elasticity > 0:
            raise ValueError("demand elasticity should be negative")
        for start, end in self.peak_windows:
            if end <= start:
                raise ValueError("pricing window must have positive length")

    def price_multiplier_at(self, minute: float) -> float:
        for start, end in self.peak_windows:
            if start <= minute < end:
                return self.peak_price_multiplier
        return 1.0

    def demand_multiplier_at(self, minute: float) -> float:
        price = self.price_multiplier_at(minute)
        return price**self.elasticity


@dataclass(frozen=True)
class SlaSpec:
    """Service-level agreement: compensation for late customers."""

    target_minutes: float = 5.0
    compensation: float = 2.0
    fairness_cap_minutes: Optional[float] = None  # aging cap for low priority

    def __post_init__(self) -> None:
        if self.target_minutes <= 0:
            raise ValueError("SLA target must be positive")
        if self.compensation < 0:
            raise ValueError("SLA compensation must be non-negative")
        if self.fairness_cap_minutes is not None and self.fairness_cap_minutes <= 0:
            raise ValueError("fairness cap must be positive when set")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sample_lognormal(
    rnd: random.Random, mean: Optional[float], cv: float, *, required: bool = False
) -> Optional[float]:
    if mean is None:
        if required:
            raise ValueError("lognormal sample needs a mean")
        return None
    if cv == 0.0:
        return mean
    sigma_squared = math.log(1.0 + cv * cv)
    mu = math.log(mean) - 0.5 * sigma_squared
    return rnd.lognormvariate(mu, math.sqrt(sigma_squared))
