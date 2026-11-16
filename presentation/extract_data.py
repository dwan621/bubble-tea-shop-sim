"""Extract the headline numbers used by the presentation into data.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "data.json"


def load(name: str):
    return json.loads((ROOT / "results" / name).read_text(encoding="utf-8"))


def main() -> None:
    demand = load("demand_study.json")
    network = load("network_study.json")
    inventory = load("inventory_study.json")
    economics = load("economics_study.json")
    policy = load("policy_sweep.json")
    breakeven = load("breakeven.json")
    scenarios = load("scenario_library.json")

    peak = demand["findings"]["peak_vs_flat"]
    bottleneck = network["findings"]["bottleneck_migration"]
    strategy = network["findings"]["strategy_by_bottleneck"]
    skill_pairs = {row["name"]: row for row in network["tables"]["skill_matrix_paired"]}
    shift_pairs = {row["name"]: row for row in network["tables"]["shifts_paired"]}
    shifts = network["findings"]["shifts"]

    inv_decision = inventory["tables"]["decision_summary"]
    inv_tradeoff = inventory["tables"]["tradeoff"]
    lead_effect = inv_decision["lead_time_effect"]

    pricing_optima = economics["tables"]["pricing_optima"]
    sla = economics["tables"]["sla_summary"]
    fairness = economics["tables"]["fairness_summary"]
    mgmt = economics["tables"]["management_summary"]

    # baseline policy rows at workers=3, lambda=1.25
    records = [
        row
        for row in policy["records"]
        if row["workers"] == 3 and abs(row["arrival_rate"] - 1.25) < 1e-9
    ]
    by_policy = {row["policy_label"]: row["means"] for row in records}
    baseline_pairs = [
        row
        for row in policy["pairs"]
        if row["workers"] == 3 and abs(row["arrival_rate"] - 1.25) < 1e-9
    ]
    fast_pair = next(
        (row for row in baseline_pairs if row["pair_key"] == "fast_minus_fcfs"), None
    )
    split_pair = next(
        (row for row in baseline_pairs if row["pair_key"] == "split_minus_synchro"), None
    )
    be3 = next(item for item in breakeven["breakeven"] if item["workers"] == 3)

    data = {
        "meta": {
            "title": "Bubble-tea shop simulation: scheduling, inventory and pricing across four layers",
            "title_en": "Bubble-tea shop simulation: four layers, one engine",
            "course": "SYE5006 Service Operations and Queueing",
            "date": "2026-11",
            "tests": 69,
            "scenarios": len(scenarios["tables"]["scenarios"]),
            "reps": 100,
        },
        "baseline": {
            "profit": by_policy["Synchro + FCFS"]["profit_per_hour"],
            "los": by_policy["Synchro + FCFS"]["mean_los"],
            "p95": economics["tables"]["baseline"]["metrics"]["los_p95"],
            "fast_delta": fast_pair["diff"]["profit_per_hour"] if fast_pair else None,
            "fast_ci": fast_pair["ci95"]["profit_per_hour"] if fast_pair else None,
            "split_delta": split_pair["diff"]["profit_per_hour"] if split_pair else None,
            "split_ci": split_pair["ci95"]["profit_per_hour"] if split_pair else None,
            "breakeven_lambda": be3["lambda_star"],
            "breakeven_util": be3["utilization_star"],
        },
        "peak": {
            "p95_peak_abs": demand["tables"]["peak_vs_flat"][0]["metrics"]["los_p95"],
            "p95_flat_abs": demand["tables"]["peak_vs_flat"][1]["metrics"]["los_p95"],
            "mean_los_peak": demand["tables"]["peak_vs_flat"][0]["metrics"]["mean_los"],
            "mean_los_flat": demand["tables"]["peak_vs_flat"][1]["metrics"]["mean_los"],
            "p95_peak": peak["p95_ratio_peak_over_flat"],
            "busy_peak": peak["peak_hour_busy_ratio_peak"],
            "busy_flat": peak["peak_hour_busy_ratio_flat"],
            "balk_peak": peak["balk_rate_peak"],
            "balk_flat": peak["balk_rate_flat"],
            "profit_peak": peak["profit_per_hour_peak"],
            "profit_flat": peak["profit_per_hour_flat"],
            "util_peak": peak["daily_util_peak"],
            "util_flat": peak["daily_util_flat"],
        },
        "bottleneck": bottleneck,
        "strategy": {
            "split_values": network["tables"]["strategy_split_value"],
            "tea_fast": strategy["fast_priority_value"][0]["profit_per_hour"],
            "tea_split": strategy["fast_priority_value"][1]["profit_per_hour"],
            "ice_fast": strategy["fast_priority_value"][2]["profit_per_hour"],
            "ice_split": strategy["fast_priority_value"][3]["profit_per_hour"],
        },
        "skills": {
            "generalist": skill_pairs["skill_generalist_minus_dedicated"]["metrics"]["profit_per_hour"],
            "cross": skill_pairs["skill_cross_trained_minus_dedicated"]["metrics"]["profit_per_hour"],
        },
        "shifts": {
            "peak_los": shifts["peak_hour_los"],
            "break_delta": shift_pairs["shift_staggered_break_minus_no_shift"]["metrics"]["profit_per_hour"],
            "mid_delta": shift_pairs["shift_mid_shift_barista_minus_no_shift"]["metrics"]["profit_per_hour"],
            "mid_peak_delta": shift_pairs["shift_mid_shift_barista_minus_no_shift"]["metrics"]["peak_hour_los"],
        },
        "inventory": {
            "baseline": inv_decision["baseline"],
            "recommended": inv_decision["recommended_ss"],
            "gain": inv_decision["profit_gain_per_hour"],
            "fill_change": inv_decision["fill_change"],
            "substitution_gain": inv_decision["substitution_gain_ice_short"],
            "lead_fill": lead_effect,
            "best_fill": max(row["fill_rate"] for row in inv_tradeoff["frontier"]),
        },
        "pricing": {
            "service_neutral": pricing_optima[0]["service_neutral_multiplier"],
            "neutral_profit": pricing_optima[0]["service_neutral_profit_per_hour"],
            "neutral_retained": pricing_optima[0]["service_neutral_served_retained"],
            "neutral_peak_p95": pricing_optima[0]["service_neutral_peak_p95"],
            "optima": [
                {
                    "elasticity": item["elasticity"],
                    "service_neutral": item["service_neutral_multiplier"],
                    "profit_max": item["profit_max_multiplier"],
                    "boundary": item["profit_max_is_boundary"],
                }
                for item in pricing_optima
            ],
        },
        "sla": sla,
        "fairness": {
            "uncapped": fairness["uncapped"],
            "best_tail": fairness.get("best_tail_protection"),
            "mean_gap_uncapped": fairness.get("mean_gap_uncapped"),
            "mean_gap_best": fairness.get("mean_gap_best_cap"),
            "tail_gap_uncapped": fairness.get("tail_gap_uncapped"),
            "tail_gap_best": fairness.get("tail_gap_best_cap"),
        },
        "management": mgmt,
        "charts": {
            "hourly": {
                "labels": [f"{int(row['hour_start'] // 60) + 1}h" for row in demand["series"]["peak_vs_flat_hourly"]["peak_shape"]],
                "peak": [row["busy_ratio"] for row in demand["series"]["peak_vs_flat_hourly"]["peak_shape"]],
                "flat": [row["busy_ratio"] for row in demand["series"]["peak_vs_flat_hourly"]["flat_same_daily_mean"]],
            },
            "variability": {
                "labels": [row["variant"].replace("lognormal_cv", "lognormal CV ") for row in demand["tables"]["variability_scan"] if abs(row["lambda"] - 1.2) < 1e-9],
                "p95": [round(row["metrics"]["los_p95"], 2) for row in demand["tables"]["variability_scan"] if abs(row["lambda"] - 1.2) < 1e-9],
            },
            "patience": {
                "labels": [f"balk {int(row['balk_mean'])}m" for row in demand["tables"]["patience_scan"] if abs(row["lambda"] - 1.2) < 1e-9 and row["renege_mean"] == 10.0],
                "abandon": [round(row["metrics"]["abandon_rate"], 4) for row in demand["tables"]["patience_scan"] if abs(row["lambda"] - 1.2) < 1e-9 and row["renege_mean"] == 10.0],
            },
            "tea_capacity": {
                "labels": ["1", "2", "3", "4"],
                "series": [
                    {
                        "name": f"λ={lam}",
                        "values": [round(row["metrics"]["los_p95"], 2) for row in network["tables"]["tea_capacity_sweep"] if abs(row["lambda"] - lam) < 1e-9],
                    }
                    for lam in (0.6, 0.9, 1.2)
                ],
            },
            "lead_time": {
                "labels": [f"{int(row['lead_time_minutes'])}m" for row in inventory["tables"]["lead_time_scan"]],
                "fill": [round(row["fill_rate"], 4) for row in inventory["tables"]["lead_time_scan"]],
                "profit": [round(row["profit_per_hour"], 1) for row in inventory["tables"]["lead_time_scan"]],
            },
            "ceiling": {
                "labels": [f"{int(row['order_quantity_units'])}" for row in inventory["tables"]["pearls_order_ceiling"]],
                "waste": [round(row["waste_units"], 1) for row in inventory["tables"]["pearls_order_ceiling"]],
            },
            "pricing": {
                "labels": [str(value) for value in economics["series"]["pricing_curves"]["-0.5"]["x"]],
                "profit": [round(value, 1) for value in economics["series"]["pricing_curves"]["-0.5"]["profit_per_hour"]],
                "peak_p95": [round(value, 2) for value in economics["series"]["pricing_curves"]["-0.5"]["peak_los_p95"]],
            },
            "levers": [
                ["4th barista", round(mgmt["lever_ranking_by_profit"][0]["profit_delta_vs_baseline"], 1)],
                ["Peak pricing ×1.2", round(mgmt["lever_ranking_by_profit"][1]["profit_delta_vs_baseline"], 1)],
                ["Fairness cap 1.5", round(mgmt["lever_ranking_by_profit"][2]["profit_delta_vs_baseline"], 1)],
                ["SLA 5 min", round(mgmt["lever_ranking_by_profit"][3]["profit_delta_vs_baseline"], 1)],
            ],
            "contrasts": [
                ["Tea station · fast priority", round(strategy["fast_priority_value"][0]["profit_per_hour"]["diff"], 2)],
                ["Tea station · split delivery", round(network["tables"]["strategy_split_value"][0]["profit_per_hour"]["diff"], 2)],
                ["Ice cream · fast priority", round(strategy["fast_priority_value"][2]["profit_per_hour"]["diff"], 2)],
                ["Ice cream · split delivery", round(network["tables"]["strategy_split_value"][2]["profit_per_hour"]["diff"], 2)],
            ],
        },
    }

    OUT.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
