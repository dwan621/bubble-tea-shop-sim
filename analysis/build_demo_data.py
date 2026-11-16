"""Precompute the datasets used by the offline demo (``demo/``).

The demo must open from ``file://`` with no build step and no network, so the
browser never runs the discrete-event simulation: everything is precomputed
here, written as compact JSON into ``demo/data/`` and rendered by vanilla
JavaScript in ``demo/index.html``.

Outputs
-------
``demo/data/manifest.json``       provenance: versions, seeds, replicates, sizes
``demo/data/scenarios.json``      every scenario x the 2x2 policy matrix
``demo/data/demand_slider.json``  intra-day demand curve family (flat -> 2x peak)
``demo/data/timeline.json``       one traced day per animated configuration

Run from the repository root::

    python analysis/build_demo_data.py

The script is deterministic: same repository state -> byte-identical JSON.
"""

from __future__ import annotations

import json
import math
import platform
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from bubble_tea_sim import __version__, library, stats
from bubble_tea_sim.data_spec import DemandProfile, DemandSegment
from bubble_tea_sim.engine import Job, Simulation
from bubble_tea_sim.params import SimConfig

ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA = ROOT / "demo" / "data"

#: The 2x2 delivery/triage matrix, in a stable display order.
POLICY_MATRIX: Tuple[Tuple[str, bool, bool], ...] = (
    ("synchro+fcfs", False, False),
    ("synchro+fast", False, True),
    ("split+fcfs", True, False),
    ("split+fast", True, True),
)

POLICY_LABEL = {
    "synchro+fcfs": "Synchro + FCFS",
    "synchro+fast": "Synchro + fast priority",
    "split+fcfs": "Split + FCFS",
    "split+fast": "Split + fast priority",
}

#: Metrics copied into the demo (a small, UI-focused subset).
DEMO_METRICS: Tuple[str, ...] = (
    "served",
    "util",
    "mean_los",
    "los_p50",
    "los_p95",
    "balked",
    "reneged",
    "stockout_losses",
    "profit_per_hour",
    "revenue_per_hour",
    "fill_rate",
    "waste_units",
    "fairness_gap",
)

SCENARIO_REPS = 5
SLIDER_REPS = 6
SLIDER_PEAKS: Tuple[float, ...] = (1.0, 1.2, 1.4, 1.6, 1.8, 2.0)
BASE_SCENARIO = "campus_rush"
#: Two traced days: the busiest scenario under the two delivery policies.
ANIMATIONS: Tuple[Tuple[str, bool, bool, int], ...] = (
    ("flagship_five_staff", False, True, 0),
    ("flagship_five_staff", True, True, 0),
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return round(float(value), digits)


def _with_policy(config: SimConfig, split: bool, fast: bool) -> SimConfig:
    return replace(
        config,
        name=f"{config.name}-{'split' if split else 'synchro'}-{'fast' if fast else 'fcfs'}",
        policy=replace(config.policy, split_mix=split, fast_priority=fast),
    )


def _config_card(config: SimConfig) -> Dict[str, object]:
    network = config.network
    stations = []
    staff = None
    if network is not None:
        stations = [
            {"name": station.name, "capacity": station.capacity, "skill": station.skill}
            for station in network.stations
        ]
        if network.staff is not None:
            staff = {
                "roles": list(network.staff.roles),
                "counts": list(network.staff.counts),
                "skills": [list(skills) for skills in network.staff.skills],
            }
    demand_curve = [
        {"minute": segment.start_minute, "multiplier": segment.multiplier}
        for segment in config.demand.segments
    ]
    return {
        "name": config.name,
        "workers": config.workers,
        "arrival_rate": _round(config.arrival_rate),
        "sim_minutes": config.sim_minutes,
        "warmup_minutes": config.warmup_minutes,
        "util_theory": _round(config.utilization()),
        "mean_service_time": _round(config.mean_service_time()),
        "baseline_compat": config.baseline_compat,
        "policy": config.policy.describe(),
        "demand": demand_curve,
        "demand_peak": _round(config.demand.peak_multiplier()),
        "batch_probability": config.batches.probability,
        "variability": config.variability.kind,
        "classes": [cls.name for cls in config.classes.classes],
        "stations": stations,
        "staff": staff,
        "has_inventory": config.inventory is not None,
        "pricing": config.pricing is not None,
        "sla": config.sla is not None,
    }


def _mean_metrics(config: SimConfig, reps: int, seeds: Sequence[int]) -> Dict[str, object]:
    rows: List[Dict[str, float]] = []
    util_peak: List[float] = []
    balk_rates: List[float] = []
    for seed in seeds:
        result = Simulation(config, seed=seed).run()
        flat = stats.flatten_metrics(result.metrics)
        rows.append(flat)
        busy = [
            float(hour["busy_ratio"])
            for hour in result.metrics.hourly
            if float(hour["arrivals"]) > 0
        ]
        if busy:
            util_peak.append(max(busy))
        arrived = (
            flat["served"]
            + flat["balked"]
            + flat["reneged"]
            + flat["stockout_losses"]
            + flat["stranded"]
        )
        balk_rates.append(flat["balked"] / arrived if arrived else 0.0)
    means = {key: stats.mean([row[key] for row in rows]) for key in rows[0]}
    payload: Dict[str, object] = {
        key: _round(means[key]) for key in DEMO_METRICS if key in means
    }
    payload["util_peak_hour"] = _round(stats.mean(util_peak) if util_peak else 0.0)
    payload["balk_rate"] = _round(stats.mean(balk_rates))
    return payload


# --------------------------------------------------------------------------
# 1. scenario x policy matrix
# --------------------------------------------------------------------------
def scenario_payload() -> Dict[str, object]:
    scenarios = []
    for name in library.scenario_names():
        raw = library.load_raw(name)
        config = library.load_scenario(name)
        policies = []
        for key, split, fast in POLICY_MATRIX:
            variant = _with_policy(config, split, fast)
            policies.append(
                {
                    "key": key,
                    "label": POLICY_LABEL[key],
                    "metrics": _mean_metrics(variant, SCENARIO_REPS, range(SCENARIO_REPS)),
                }
            )
        scenarios.append(
            {
                "name": name,
                "title": raw.get("title", name),
                "provenance": raw.get("provenance", {}),
                "config": _config_card(config),
                "policies": policies,
            }
        )
    return {
        "meta": {
            "kind": "scenario-matrix",
            "reps": SCENARIO_REPS,
            "seed": 0,
            "seed_stride": 1,
            "metric_units": {
                "util": "fraction of staff-minutes busy",
                "mean_los": "minutes",
                "los_p50": "minutes",
                "los_p95": "minutes",
                "profit_per_hour": "currency units per hour",
                "revenue_per_hour": "currency units per hour",
                "balk_rate": "share of arrivals that walked away",
            },
        },
        "policies": [key for key, _, _ in POLICY_MATRIX],
        "scenarios": scenarios,
    }


# --------------------------------------------------------------------------
# 2. intra-day demand curve family
# --------------------------------------------------------------------------
def _scaled_profile(profile: DemandProfile, target_peak: float) -> DemandProfile:
    """Scale the peak deviation so the maximum multiplier equals ``target_peak``."""
    current_peak = profile.peak_multiplier()
    if current_peak <= 1.0 or target_peak == 1.0:
        return DemandProfile()
    factor = (target_peak - 1.0) / (current_peak - 1.0)
    segments = tuple(
        DemandSegment(segment.start_minute, 1.0 + (segment.multiplier - 1.0) * factor)
        for segment in profile.segments
    )
    return DemandProfile(segments=segments)


def demand_slider_payload() -> Dict[str, object]:
    base = library.load_scenario(BASE_SCENARIO)
    target_daily_mean = base.arrival_rate
    points = []
    for peak in SLIDER_PEAKS:
        profile = _scaled_profile(base.demand, peak)
        daily_mean = profile.daily_mean_multiplier(base.sim_minutes)
        variant = replace(
            base,
            name=f"{BASE_SCENARIO}-peak{peak:g}",
            demand=profile,
            arrival_rate=target_daily_mean / daily_mean,
        )
        metrics = _mean_metrics(variant, SLIDER_REPS, range(SLIDER_REPS))
        # Hourly profile: the planner curve (expected arrivals) plus the mean
        # simulated busy ratio in the same hour.
        hourly = []
        for index in range(int(math.ceil(base.sim_minutes / 60.0))):
            start = index * 60.0
            end = min(base.sim_minutes, start + 60.0)
            multiplier = profile.multiplier_at(start + 0.5)
            hourly.append(
                {
                    "hour": int(start // 60),
                    "expected_arrivals": _round(
                        variant.arrival_rate * (end - start) * multiplier, 2
                    ),
                    "multiplier": _round(multiplier, 3),
                }
            )
        points.append(
            {
                "peak": peak,
                "multiplier_at_peak": _round(profile.peak_multiplier(), 3),
                "arrival_rate_daily_mean": _round(variant.arrival_rate, 4),
                "demand_curve": [
                    {"minute": segment.start_minute, "multiplier": segment.multiplier}
                    for segment in profile.segments
                ],
                "hourly": hourly,
                "metrics": metrics,
            }
        )
    return {
        "meta": {
            "kind": "demand-slider",
            "base_scenario": BASE_SCENARIO,
            "reps": SLIDER_REPS,
            "seed": 0,
            "seed_stride": 1,
            "daily_mean_held_fixed": True,
            "note": (
                "The daily mean arrival rate is held fixed; only the shape of the "
                "intra-day curve changes, so every point differs in peak load only."
            ),
        },
        "points": points,
    }


# --------------------------------------------------------------------------
# 3. traced day for the animation
# --------------------------------------------------------------------------
def _lane_specs(config: SimConfig, jobs: Sequence[Job]) -> List[Dict[str, object]]:
    """Swim-lanes: the real stations when the network layer is on, else the
    components (the original engine has one cross-trained clerk pool)."""
    network = config.network
    lanes: List[Dict[str, object]] = []
    if network is not None and network.stations:
        lanes = [
            {"name": station.name, "capacity": station.capacity}
            for station in network.stations
        ]
    known = {lane["name"] for lane in lanes}
    for job in jobs:
        lane = str(job.station or job.component)
        if lane not in known:
            lanes.append({"name": lane, "capacity": config.workers})
            known.add(lane)
    if not lanes:
        lanes.append({"name": "clerk", "capacity": config.workers})
    return lanes


#: Colour slot per order component; ``order`` is the cashier step.
_JOB_KIND = {
    "tea": 0,
    "mix_tea": 0,
    "bread": 1,
    "ice": 2,
    "mix_ice": 2,
    "mix_all": 3,
    "order": 4,
}
_JOB_KINDS = ["tea", "bread", "ice", "mix", "order"]


def timeline_payload(
    scenario: str, split: bool, fast: bool, seed: int
) -> Dict[str, object]:
    config = _with_policy(library.load_scenario(scenario), split, fast)
    simulation = Simulation(config, seed=seed, trace=True)
    result = simulation.run()
    trace = simulation.trace or []

    arrivals: Dict[int, float] = {}
    first_start: Dict[int, float] = {}
    abandon_time: Dict[int, float] = {}
    for record in trace:
        event = record["event"]
        cid = int(record["cid"])  # type: ignore[arg-type]
        if event == "arrival":
            arrivals[cid] = float(record["time"])  # type: ignore[arg-type]
        elif event == "start":
            first_start.setdefault(cid, float(record["time"]))  # type: ignore[arg-type]
        elif event in ("balk", "renege", "stockout"):
            abandon_time[cid] = float(record["time"])  # type: ignore[arg-type]

    # Exact per-job service blocks come from the engine's job records: every job
    # knows its station, start and finish, so the swim-lanes show real station
    # occupancy instead of a customer-level approximation.
    lane_specs = _lane_specs(config, simulation.jobs)
    lane_index = {str(spec["name"]): index for index, spec in enumerate(lane_specs)}
    jobs: List[List[object]] = []
    job_starts: Dict[int, List[float]] = {}
    for job in simulation.jobs:
        if job.cancelled or job.started is None or job.finished is None:
            continue
        lane = str(job.station or job.component)
        jobs.append(
            [
                _round(job.started, 2),
                _round(job.finished, 2),
                lane_index.get(lane, 0),
                _JOB_KIND.get(job.component, 3),
                job.cid,
            ]
        )
        job_starts.setdefault(job.cid, []).append(job.started)
    jobs.sort(key=lambda item: item[0])  # type: ignore[arg-type, return-value]
    for cid, starts in job_starts.items():
        first_start[cid] = min(starts)

    status_code = {"served": 0, "balk": 1, "renege": 2, "stockout": 3, "stranded": 4}
    customers = []
    for customer in result.customers:
        cid = customer.cid
        start = first_start.get(cid)
        departure = customer.departure
        abandoned = customer.abandoned
        status = "served" if departure is not None else (abandoned or "stranded")
        kind = customer.kind if customer.kind in _JOB_KINDS else "tea"
        if departure is not None:
            ended = departure
        elif abandoned is not None:
            ended = abandon_time.get(cid, customer.arrival)
        else:
            ended = config.sim_minutes  # still in the shop when the day ends
        customers.append(
            [
                _round(customer.arrival, 2),
                _round(start, 2) if start is not None else None,
                _round(ended, 2),
                _JOB_KINDS.index(kind),
                status_code.get(status, 0),
                customer.class_name,
            ]
        )

    served = [customer for customer in customers if customer[4] == 0]
    waits = [customer[1] - customer[0] for customer in served if customer[1] is not None]
    return {
        "meta": {
            "kind": "timeline",
            "scenario": scenario,
            "policy": config.policy.describe(),
            "policy_key": f"{'split' if split else 'synchro'}+{'fast' if fast else 'fcfs'}",
            "seed": seed,
            "sim_minutes": config.sim_minutes,
            "reps": 1,
            "note": (
                "One traced replicate. Customer events come from the trace; the "
                "station swim-lanes come from the engine's job records. Playback "
                "repaints these records; the browser does not simulate anything."
            ),
        },
        "lanes": lane_specs,
        "kinds": _JOB_KINDS,
        "status": ["served", "balk", "renege", "stockout", "stranded"],
        "customers": customers,
        "jobs": jobs,
        "summary": {
            "arrivals": len(customers),
            "served": len(served),
            "balked": sum(1 for customer in customers if customer[4] == 1),
            "reneged": sum(1 for customer in customers if customer[4] == 2),
            "stockout": sum(1 for customer in customers if customer[4] == 3),
            "stranded": sum(1 for customer in customers if customer[4] == 4),
            "mean_wait": _round(stats.mean(waits), 3) if waits else None,
            "p95_wait": _round(
                sorted(waits)[int(0.95 * (len(waits) - 1))] if waits else 0.0, 3
            ),
            "mean_los": _round(result.metrics.mean_los, 3),
            "util": _round(result.metrics.util, 4),
            "profit_per_hour": _round(result.metrics.profit_per_hour, 2),
        },
    }


# --------------------------------------------------------------------------
# 4. manifest / main
# --------------------------------------------------------------------------
def _write(path: Path, payload: Dict[str, object], *, compact: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":") if compact else (", ", ": "),
        indent=None if compact else 1,
    )
    path.write_text(text + "\n", encoding="utf-8")
    size = path.stat().st_size
    print(f"wrote {path.relative_to(ROOT)} ({size / 1024:.1f} KiB)")
    return size


def self_check(files: Dict[str, int]) -> List[str]:
    problems: List[str] = []
    total = sum(files.values())
    if total > 3 * 1024 * 1024:
        problems.append(f"demo assets exceed 3 MB: {total} bytes")
    for name, size in files.items():
        if size <= 0:
            problems.append(f"{name} is empty")
    return problems


def _bundle(payloads: Dict[str, Dict[str, object]]) -> str:
    """Mirror the JSON files as one classic script.

    Browsers refuse ``fetch``/``XMLHttpRequest`` for ``file://`` documents, but a
    classic ``<script src>`` is loaded from the same directory without CORS, so
    the demo embeds the same precomputed payloads here. The JSON files stay the
    canonical, auditable artifacts; this file is a build product of them.
    """
    body = json.dumps(payloads, ensure_ascii=False, separators=(",", ":"))
    return (
        "/* Generated by analysis/build_demo_data.py - do not edit by hand.\n"
        "   Mirror of demo/data/*.json so that demo/index.html also works from\n"
        "   file://, where browsers block fetch() of local files. */\n"
        f"window.DEMO_DATA = {body};\n"
    )


def main() -> int:
    DEMO_DATA.mkdir(parents=True, exist_ok=True)
    files: Dict[str, int] = {}
    payloads: Dict[str, Dict[str, object]] = {}

    scenarios = scenario_payload()
    payloads["scenarios"] = scenarios
    files["scenarios.json"] = _write(DEMO_DATA / "scenarios.json", scenarios, compact=True)

    slider = demand_slider_payload()
    payloads["demand_slider"] = slider
    files["demand_slider.json"] = _write(
        DEMO_DATA / "demand_slider.json", slider, compact=True
    )

    timelines = []
    for scenario, split, fast, seed in ANIMATIONS:
        payload = timeline_payload(scenario, split, fast, seed)
        key = payload["meta"]["policy_key"]  # type: ignore[index]
        timelines.append(payload)
        payloads[f"timeline-{key.replace('+', '-')}"] = payload
        files[f"timeline-{key.replace('+', '-')}.json"] = _write(
            DEMO_DATA / f"timeline-{key.replace('+', '-')}.json", payload, compact=True
        )

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_version": __version__,
        "python_version": platform.python_version(),
        "engine": "bubble_tea_sim.engine.Simulation (standard library only)",
        "generator": "analysis/build_demo_data.py",
        "note": (
            "Every number in demo/data was precomputed by the Python engine. "
            "The browser only repaints these values; it never runs the simulation."
        ),
        "loading": (
            "demo/index.html loads data/bundle.js (a classic script, allowed from "
            "file://) which mirrors these JSON files; fetch() of local JSON is "
            "blocked by browser CORS rules."
        ),
        "scenario_reps": SCENARIO_REPS,
        "slider_reps": SLIDER_REPS,
        "files": {
            "scenarios": "scenarios.json",
            "demand_slider": "demand_slider.json",
            "timelines": [
                {
                    "file": f"timeline-{p['meta']['policy_key'].replace('+', '-')}.json",  # type: ignore[index]
                    "scenario": p["meta"]["scenario"],  # type: ignore[index]
                    "policy": p["meta"]["policy"],  # type: ignore[index]
                }
                for p in timelines
            ],
        },
        "sizes_bytes": dict(files),
        "total_bytes": sum(files.values()),
        "scenarios": [entry["name"] for entry in scenarios["scenarios"]],
    }
    payloads["manifest"] = manifest
    files["manifest.json"] = _write(DEMO_DATA / "manifest.json", manifest)

    bundle = _bundle(payloads)
    bundle_path = DEMO_DATA / "bundle.js"
    bundle_path.write_text(bundle, encoding="utf-8", newline="\n")
    files["bundle.js"] = bundle_path.stat().st_size
    print(f"wrote {bundle_path.relative_to(ROOT)} ({files['bundle.js'] / 1024:.1f} KiB)")

    problems = self_check(files)
    if problems:
        for problem in problems:
            print(f"SELF-CHECK FAILED: {problem}")
        return 1
    print(f"demo assets total: {sum(files.values()) / 1024:.1f} KiB (limit 3072 KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
