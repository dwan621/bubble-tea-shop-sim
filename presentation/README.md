# Presentation material

- **Slides:** `bubble-tea-shop-simulation.pptx` (18 slides, 16:9, English, speaker notes on every slide)
- **PDF version:** `bubble-tea-shop-simulation.pdf` (for distribution and printing)
- **Speaker plan:** `speaker-plan.md` (six-person division of work and scripts)
- **Build scripts:** `build_deck.js` (PptxGenJS), `extract_data.py` (pulls numbers from `results/*.json`), `render_assets.py` (renders report SVGs and demo screenshots to PNG)

## Slide structure (18 slides / 18 minutes + 5 minutes Q&A)

| Slide | Content | Speaker |
|---|---|---|
| 1 | Title and the four layers | Member A |
| 2 | Three questions, one engine | Member A |
| 3 | Model: shared clerk pool and four order classes | Member A |
| 4 | 16 scenarios × 100 replications × paired comparison | Member B |
| 5 | Peak: the daily utilisation lies | Member B |
| 6 | Variability and patience | Member C |
| 7 | The bottleneck migrates | Member C |
| 8 | Policy depends on the bottleneck | Member D |
| 9 | Skills and shifts | Member D |
| 10 | Inventory: cheap fill rate, costly shelf life | Member E |
| 11 | Pricing: the service-neutral multiplier | Member E |
| 12 | SLA and fairness | Member E |
| 13 | The management bundle | Member F |
| 14 | Four management rules | Member F |
| 15 | Reproducibility and the limits of the evidence | Member F |
| 16 | 60-second live demo | Member F |
| 17 | Limits and next steps | Member F |
| 18 | Q&A and division of work | Member F |

## Rebuilding

```powershell
# 1) Data (reads results/*.json in the repository root)
python presentation/extract_data.py

# 2) Charts and screenshots (needs Chrome/Edge; writes into presentation/assets/)
python presentation/render_assets.py

# 3) Build the PPTX (needs Node + pptxgenjs)
node presentation/build_deck.js
```

`presentation/assets/` and `presentation/slide-png/` are generated caches and are listed in `.gitignore`; the PPTX and PDF embed the images they need, so the deck opens without them.

## Notes

- "Member A–F" on slide 18 is a placeholder: substitute the real names in `slideTeam()` in `build_deck.js` and in `speaker-plan.md` together.
- Every number comes from `results/*.json`; if the study numbers change, rerun `extract_data.py` and then rebuild the deck.
- The deck is English throughout (technical terms and scenario ids kept as-is), 18 minutes + 5 minutes Q&A; adjust the timing in `speaker-plan.md` to match the course requirements.
