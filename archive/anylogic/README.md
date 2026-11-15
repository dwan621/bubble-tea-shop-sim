# AnyLogic model archive (not re-runnable here)

This folder contains a frozen snapshot of the AnyLogic PLE model that produced
the E-series experiment results in `docs/experiment_log.md`.

| File | Description |
|---|---|
| `MIXUE_Model.alp` | AnyLogic 8 project snapshot, taken 2026-11-14 |
| `3d/person.dae` | 3D pedestrian asset referenced by the model |

**Important:** the model is archived evidence, *not* a reproducible part of this
repository. AnyLogic is proprietary desktop software; the CI environment and the
people reproducing this study do not have it. Treat `docs/experiment_log.md`
E1–E6 rows, and the screenshots in `docs/assets/slides/`, as archival records.

To check the archive against the open engine, see
`analysis/reproduce_anylogic_ledger.py` (and `results/anylogic_ledger.json` when
generated): it reimplements the same model logic with `bubble_tea_sim` and
reports the deviation from the archived AnyLogic numbers.

To run the archived model yourself:

1. Install AnyLogic 8 PLE (`https://www.anylogic.com/`).
2. Open `MIXUE_Model.alp`.
3. Set `workers`, `lambdaArrival`, `mixSplit`, `fastPriority` on the Main canvas
   and the stop time (1000 minutes for the E-series runs).
4. The file was exported from a machine with a local course-material folder;
   any absolute resource path inside it is stale by design and must be relinked
   to `3d/person.dae` in this folder.

Model flow: `sourceTea / sourceBread / sourceIce` → shared `seizeClerk` →
`delayMake` → `releaseClerk` → `selectByType` → type-specific timing → `sink`.
