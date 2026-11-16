# Original course scripts (provenance only)

These three files are **verbatim copies** of the original course scripts used
for the 2026-11 AnyLogic homework. They are kept in the repository for two
reasons: the `docs/experiment_log.md` ledger cites their outputs, and the unified
engine's regression tests were validated against them.

They are **superseded** by the `bubble_tea_sim` package. New work should use the
package; these scripts are not maintained.

| Original script | What it does | Unified replacement | Regression test |
|---|---|---|---|
| `mixed_order_sim.py` | Mixed-order study: Synchro vs Split delivery, 200 reps × 4 loads | `scenarios.mixed_order_baseline()` | `tests/test_anchors.py::test_mixed_order_anchor` |
| `bread_priority_sim.py` | Fast-item priority (bread/ice) vs FCFS, 6 reps × 3 loads | `scenarios.bread_priority_baseline()` | `tests/test_anchors.py::test_bread_priority_anchor` |
| `icecream_strategy_sim.py` | Early melt-risk demo with a melt window | `scenarios.study(..., split_mix=...)` + `mix_ice_priority` | direction-only tests in `tests/test_behaviour.py` |

Known caveats, documented instead of silently fixed:

* `icecream_strategy_sim.py` seeds each replicate with `hash(strat) % 997`.
  Python randomises string hashing per process, so **that script's numbers are
  not reproducible**, which is one reason it was retired. The unified engine
  replaces it with the deterministic melt-risk policy (`mix_ice_priority`) and
  the dynamic-priority behaviour study.
* `mixed_order_sim.py` contains an earlier M1 version that mixed up completion
  fields and included a melt metric; only the corrected M2 results are cited in
  the ledger. The unified engine implements the corrected semantics.
* `bread_priority_sim.py` averages a *pooled* customer list, while
  `mixed_order_sim.py` averages *per-replicate means*. Both are valid estimators;
  `bubble_tea_sim.stats.replicate()` uses per-replicate means and
  `bubble_tea_sim.stats.pooled_los()` reproduces the pooled one.

Run them with `python original/<script>.py` (standard library only).
