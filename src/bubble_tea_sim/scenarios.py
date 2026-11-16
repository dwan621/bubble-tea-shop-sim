"""Named scenarios used by the study, the tests and the CLI.

Two groups exist:

* ``*_baseline`` scenarios reproduce the original scripts in ``original/`` exactly
  (same arrival stream, same seeds, same scheduling) and are pinned by tests to
  the numbers recorded in ``docs/experiment_log.md``.
* ``study_*`` scenarios are the cleaner, unified configurations used for the new
  experiments (fine-grained load/worker sweeps, break-even, sensitivity and
  behaviour mechanisms).
"""

from __future__ import annotations

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

# Seed strides used by the original course scripts: seed = stride * replicate_index.
BASELINE_MIXED_ORDER_SEED_STRIDE = 9001  # 9000 * rep + rep
BASELINE_BREAD_PRIORITY_SEED_STRIDE = 7001  # 7000 * rep + rep

# Baseline parameter sets -----------------------------------------------------
BASELINE_MIXED_ORDER_MIX = OrderMix(tea=0.55, bread=0.20, ice=0.05, mix=0.20)
BASELINE_BREAD_PRIORITY_MIX = OrderMix(tea=0.65, bread=0.20, ice=0.15, mix=0.00)
# The original bread/ice-cream script used 0.33 min (20 s) for the ice cream.
BASELINE_BREAD_PRIORITY_TIMES = ServiceTimes(order=0.5, tea=2.0, bread=0.167, ice=0.33)


def mixed_order_baseline(
    arrival_rate: float,
    *,
    split_mix: bool,
    workers: int = 3,
) -> SimConfig:
    """The M2 mixed-order study (``mixed_order_sim.py``)."""
    return SimConfig(
        name=f"original-mixed-order-lam{arrival_rate:g}-{'split' if split_mix else 'synchro'}",
        workers=workers,
        arrival_rate=arrival_rate,
        sim_minutes=480.0,
        warmup_minutes=60.0,
        mix=BASELINE_MIXED_ORDER_MIX,
        times=ServiceTimes(order=0.5, tea=2.0, bread=0.167, ice=0.333),
        policy=Policy(split_mix=split_mix, fast_priority=False),
    )


def bread_priority_baseline(
    arrival_rate: float,
    *,
    fast_priority: bool,
    workers: int = 3,
) -> SimConfig:
    """The P-series fast-item-priority study (``bread_priority_sim.py``)."""
    return SimConfig(
        name=f"original-bread-priority-lam{arrival_rate:g}-{'fast' if fast_priority else 'fcfs'}",
        workers=workers,
        arrival_rate=arrival_rate,
        sim_minutes=480.0,
        warmup_minutes=60.0,
        mix=BASELINE_BREAD_PRIORITY_MIX,
        times=BASELINE_BREAD_PRIORITY_TIMES,
        policy=Policy(split_mix=False, fast_priority=fast_priority),
    )


# Study scenarios -----------------------------------------------------------
def study(
    arrival_rate: float,
    *,
    workers: int = 3,
    split_mix: bool = False,
    fast_priority: bool = False,
    balk_threshold: float | None = None,
    renege_threshold: float | None = None,
    dynamic_priority_threshold: float | None = None,
    mix_ice_priority: str = "jump",
    mix: OrderMix | None = None,
    times: ServiceTimes | None = None,
    economics: Economics | None = None,
    sim_minutes: float = 480.0,
    warmup_minutes: float = 60.0,
    name: str | None = None,
) -> SimConfig:
    """A study configuration with the report's default parameters."""
    policy = Policy(
        split_mix=split_mix,
        fast_priority=fast_priority,
        balk_threshold=balk_threshold,
        renege_threshold=renege_threshold,
        dynamic_priority_threshold=dynamic_priority_threshold,
        mix_ice_priority=mix_ice_priority,
    )
    return SimConfig(
        name=name or f"study-lam{arrival_rate:g}-{policy.describe()}",
        workers=workers,
        arrival_rate=arrival_rate,
        sim_minutes=sim_minutes,
        warmup_minutes=warmup_minutes,
        mix=mix or OrderMix(),
        times=times or ServiceTimes(),
        policy=policy,
        economics=economics or Economics(),
    )


def four_policies(
    arrival_rate: float,
    *,
    workers: int = 3,
    **kwargs,
) -> list:
    """The 2x2 baseline matrix: delivery strategy x fast priority."""
    return [
        study(
            arrival_rate,
            workers=workers,
            split_mix=split,
            fast_priority=fast,
            name=f"lam{arrival_rate:g}-{'split' if split else 'synchro'}-"
            f"{'fast' if fast else 'fcfs'}",
            **kwargs,
        )
        for split in (False, True)
        for fast in (False, True)
    ]


def default_mix() -> OrderMix:
    return OrderMix()


def default_times() -> ServiceTimes:
    return ServiceTimes()


__all__ = [
    "BASELINE_BREAD_PRIORITY_MIX",
    "BASELINE_BREAD_PRIORITY_SEED_STRIDE",
    "BASELINE_BREAD_PRIORITY_TIMES",
    "BASELINE_MIXED_ORDER_MIX",
    "BASELINE_MIXED_ORDER_SEED_STRIDE",
    "default_mix",
    "default_times",
    "four_policies",
    "bread_priority_baseline",
    "mixed_order_baseline",
    "study",
]
