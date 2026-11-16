"""Shared harness for the layer experiments.

Every layer result file in ``results/`` is produced by a script that uses this
module, so the JSON schema, the seeds and the provenance metadata are identical
across layers. Each file has the shape::

    {
      "meta": {experiment, schema_version, package_version, python_version,
               seeds, reps, notes, scenario_library},
      "tables": {...},        # layer-specific tables
      "series": {...}         # layer-specific series for figures
    }

Nothing in the files is typed by hand: the report builder reads only these
files.
"""

from __future__ import annotations

import json
import platform
from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from bubble_tea_sim import __version__, library, stats
from bubble_tea_sim.engine import Simulation, simulate

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"


def meta(experiment: str, notes: str = "", **extra) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "experiment": experiment,
        "schema_version": 1,
        "package_version": __version__,
        "python_version": platform.python_version(),
        "engine": "bubble_tea_sim.engine.Simulation (stdlib only)",
        "scenario_library": library.scenario_names(),
        "notes": notes,
    }
    payload.update(extra)
    return payload


def replicate(
    config,
    reps: int = 100,
    *,
    seed: int = 0,
    seed_stride: int = 1,
) -> Dict[str, object]:
    """Run ``reps`` replicates and return means + 95% CI for every metric."""
    rows: List[Dict[str, float]] = []
    for index in range(reps):
        metrics = Simulation(config, seed=seed + index * seed_stride).run().metrics
        rows.append(stats.flatten_metrics(metrics))
    keys = sorted(rows[0])
    return {
        "reps": reps,
        "seed": seed,
        "seed_stride": seed_stride,
        "means": {key: stats.mean([row[key] for row in rows]) for key in keys},
        "ci95": {key: stats.ci95([row[key] for row in rows]) for key in keys},
        "per_rep": rows,
    }


def paired(
    config_a,
    config_b,
    reps: int = 100,
    *,
    seed: int = 0,
    seed_stride: int = 1,
) -> Dict[str, object]:
    rows: List[Dict[str, float]] = []
    for index in range(reps):
        run_seed = seed + index * seed_stride
        a = stats.flatten_metrics(Simulation(config_a, seed=run_seed).run().metrics)
        b = stats.flatten_metrics(Simulation(config_b, seed=run_seed).run().metrics)
        rows.append({key: a[key] - b[key] for key in a})
    keys = sorted(rows[0])
    return {
        "reps": reps,
        "diff": {key: stats.mean([row[key] for row in rows]) for key in keys},
        "ci95": {key: stats.ci95([row[key] for key in rows]) for key in keys},
    }


def scenario_overrides(name: str, **changes):
    """Load a scenario and apply dataclass overrides (policy dict supported)."""
    return library.with_overrides(library.load_scenario(name), **changes)


def save(name: str, payload: Dict[str, object]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {path}")
    return path


def load(name: str) -> Dict[str, object]:
    path = RESULTS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_catalogue() -> List[Dict[str, object]]:
    """Scenario metadata (provenance + theory utilisation) for the report."""
    rows = []
    for name in library.scenario_names():
        raw = library.load_raw(name)
        config = library.load_scenario(name)
        rows.append(
            {
                "name": name,
                "title": raw.get("title", name),
                "provenance": raw.get("provenance", {}),
                "config": config.describe(),
                "baseline_compat": config.baseline_compat,
            }
        )
    return rows


def describe_series(rows: Sequence[Dict[str, object]], key: str) -> List[float]:
    return [float(row[key]) for row in rows]  # type: ignore[arg-type]
