"""Bubble-tea shop discrete-event simulation study (SYE5006 presentation project).

Quick start::

    >>> from bubble_tea_sim import scenarios, simulate
    >>> result = simulate(scenarios.study(1.25, split_mix=True), seed=0)
    >>> round(result.metrics.mean_los, 2)
    5.26

The package is dependency-free (Python standard library only) so the whole study
can be reproduced with ``python -m bubble_tea_sim reproduce --reps 200 --out
results/anchors.json`` and the ``analysis/`` scripts.
"""

from .engine import (
    Customer,
    Job,
    Metrics,
    Simulation,
    SimulationResult,
    simulate,
)
from .params import (
    Economics,
    OrderMix,
    Policy,
    ServiceTimes,
    SimConfig,
)
from . import data_spec, library, scenarios, stats

__all__ = [
    "Customer",
    "Economics",
    "Job",
    "Metrics",
    "OrderMix",
    "Policy",
    "ServiceTimes",
    "SimConfig",
    "Simulation",
    "SimulationResult",
    "data_spec",
    "library",
    "scenarios",
    "simulate",
    "stats",
]

__version__ = "2026.11"
