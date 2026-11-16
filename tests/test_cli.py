"""CLI smoke tests: the documented commands must work on a fresh checkout."""

from __future__ import annotations

import json

from bubble_tea_sim.cli import main


def test_run_command_outputs_metrics(tmp_path, capsys) -> None:
    output = tmp_path / "run.json"
    code = main(
        [
            "run",
            "--lam",
            "1.25",
            "--workers",
            "3",
            "--split",
            "--seed",
            "0",
            "--out",
            str(output),
        ]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["served"] > 0
    assert 0 < payload["util"] <= 1
    assert payload["mean_los"] > 0


def test_reproduce_command_matches_anchors(tmp_path, capsys) -> None:
    output = tmp_path / "anchors.json"
    code = main(["reproduce", "--reps", "20", "--out", str(output)])
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    anchor = payload["mixed_order"]["lam1.25-synchro"]
    assert 4.5 < anchor["means"]["mean_los"] < 5.4
    pooled = payload["bread_priority"]["lam1.3-fast"]
    assert 1.0 < pooled["los"]["bread"] < 1.3


def test_breakeven_command_returns_a_load(tmp_path) -> None:
    output = tmp_path / "breakeven.json"
    code = main(
        [
            "breakeven",
            "--workers",
            "3",
            "--lower",
            "0.6",
            "--upper",
            "1.25",
            "--reps",
            "12",
            "--out",
            str(output),
        ]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metric"] == "profit_per_hour"
    assert 0.6 <= payload["lambda"] <= 1.25


def test_scenarios_command_lists_provenance(tmp_path) -> None:
    output = tmp_path / "scenarios.json"
    code = main(["scenarios", "--out", str(output)])
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    names = {row["name"] for row in payload["scenarios"]}
    assert {"baseline_flat", "campus_rush"} <= names
    assert all(row["uncertainty"] for row in payload["scenarios"])


def test_scenario_command_runs_library_config(tmp_path) -> None:
    output = tmp_path / "scenario.json"
    code = main(
        ["scenario", "--name", "baseline_flat", "--reps", "3", "--out", str(output)]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["config"]["name"] == "baseline_flat"
    assert payload["reps"] == 3
    assert payload["means"]["served"] > 0


def test_sweep_command_writes_records(tmp_path) -> None:
    output = tmp_path / "sweep.json"
    code = main(
        [
            "sweep",
            "--workers-list",
            "3",
            "--lambdas",
            "0.8",
            "--reps",
            "8",
            "--out",
            str(output),
        ]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["records"]) == 4
