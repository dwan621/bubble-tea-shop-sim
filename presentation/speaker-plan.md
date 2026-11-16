# Six-person speaker plan

**Project:** discrete-event simulation of a bubble-tea shop — scheduling, inventory and pricing across four layers
**Format:** 18-slide deck, 18 minutes of speaking + 5 minutes of Q&A
**Control notes:** Member F keeps time and hands over between speakers; Member A sets the tone in the opening; every number quoted must match the slides and `results/*.json`, and answers should lead with the paired comparison plus its confidence interval.

> Member A–F are placeholders for the six speakers: substitute the real names in the table below and on slide 18.

---

## 1. Division of work (by slide and clock time)

| Speaker | Slides | Time | Topic | One-line message | Q&A ownership |
|---|---|---|---|---|---|
| Member A | 1–3 | 3:00 | Opening, three questions, model | One shared clerk pool plus four order classes: questions first, evidence second | Model setup, parameter definitions, project background |
| Member B | 4–5 | 2:30 | Experiment design, cost of the peak | 16 scenarios compared in pairs; the peak shape is itself a cost | Scenario provenance, statistics, confidence intervals |
| Member C | 6–7 | 2:30 | Variability and patience, bottleneck migration | Both the mean and the daily average lie; ask where the bottleneck moves before buying equipment | Randomness, queueing theory, bottleneck identification |
| Member D | 8–9 | 2:30 | Policy × bottleneck, skills and shifts | Fast-item priority is not a universal fix; for the same wage bill, generalists are worth more | Scheduling policy, skill matrix, rosters |
| Member E | 10–12 | 3:00 | Inventory, pricing, SLA and fairness | Fill rate is cheap, lead time and shelf life are not; an SLA is a transfer | Inventory / BOM, price elasticity, SLA and fairness metrics |
| Member F | 13–18 | 4:30 | Bundle, rules, evidence, demo, limits, Q&A | Capacity first, pricing second; price the SLA explicitly | Integration, reproducibility, live demo, closing |

**Timeline:** 0:00 → 3:00 → 5:30 → 8:00 → 10:30 → 13:30 → 18:00; Q&A runs 18:00–23:00.

---

## 2. Speaker scripts

### Member A (slides 1–3, 3 minutes)

**Task:** pull the audience into the problem and set up the model; do not rush to conclusions.

- **Slide 1 (30 s):** greeting plus one-sentence positioning. "We study a small shop that sells bubble tea, bread and ice cream at the same time: demand has peaks, staff have to be allocated, equipment has bottlenecks, ingredients spoil, and waiting can be converted into money. Today one simulation engine answers four layers of questions, and every number can be reproduced."
- **Slide 2 (60 s):** one sentence per question: splitting a mixed order versus synchronising it (almost free at low load, reversing at about 80% utilisation); fast-item priority (a stronger lever, but it depends on the bottleneck); how to price waiting and fairness (service-neutral markup ×1.1–1.2, an SLA is a transfer).
- **Slide 3 (60 s):** model and parameters. Emphasise "the shared clerk pool is the bottleneck" and "with total workload fixed, scheduling only changes who waits". Prices, wages and waiting costs are all written explicitly into the scenario files.
- **Handover:** "With the model fixed, we validate it with 16 scenarios and paired comparisons — over to Member B."

**Q&A defence:** why three staff? why 2 minutes for tea? — Answer: course assumptions, recorded with source and uncertainty in the scenario files, and replaceable with real data later.

### Member B (slides 4–5, 2 min 30 s)

**Task:** show that the conclusions are not guesswork, then explain the cost of the peak.

- **Slide 4 (75 s):** a 16-scenario library (campus, downtown, mall, extreme demand, small and large shops, three station bottlenecks, inventory, pricing, SLA); every scenario carries source / method / uncertainty and none of it is passed off as measured shop data. Statistical protocol: common random numbers, paired comparison, 95% CI, 100 replications (60 in the overloaded region); 69 tests, 16/16 scenarios conserving flow, and a bit-for-bit match with the course model when every new layer is off.
- **Slide 5 (75 s):** same daily arrivals, only the shape squeezed into a peak: p95 +3.72 min, balk 15.1% vs 6.9%, profit 296.0 → 239.3 /h; daily utilisation actually falls from 60.6% to 54.9% (the balking customers take their work away). Conclusion: staff to the peak, not to the daily average.
- **Handover:** "The peak is not the only hidden cost — variability and patience also lift the tail. Over to Member C."

**Q&A defence:** why only 60 replications in the overloaded region? — variance is high there and each run is longer, so 60 already gives a sufficiently narrow CI; every cell reports its replication count.

### Member C (slides 6–7, 2 min 30 s)

**Task:** explain the mechanism behind "the mean and the daily average both lie", then introduce bottleneck migration.

- **Slide 6 (75 s):** service-time variability: fixed service gives p95 8.6 min, lognormal CV 0.75 gives 10.8 min, the exponential (CV = 1) gives 15.3 min, while the mean barely moves; patience: balk 3 min → 29.3% lost, 12 min → 3.2%; under arrive-and-assess waiting, reneging almost never triggers.
- **Slide 7 (75 s):** tea-station capacity 1–4: critical capacity at λ = 0.6 / 0.9 / 1.2 is 3 / 3 / 4, profit-optimal is 2 / 2 / 3; hold two baristas fixed and add only tea stations — from k ≥ 2 on, waiting, p95 and profit are identical while tea-station utilisation falls 85% → 43%, so the constraint has migrated to the labour pool.
- **Handover:** "Since the constraint moves, the value of a policy moves with it — over to Member D."

**Q&A defence:** why does critical capacity change with λ? — because higher demand changes the relative tightness of equipment versus the labour pool; we define "critical" with paired marginal profit.

### Member D (slides 8–9, 2 min 30 s)

**Task:** make both "policy" and "people" clear.

- **Slide 8 (75 s):** tea-station bottleneck: split −2.01/h, fast +1.33/h; ice-cream-machine bottleneck: split +15.98/h, fast +1.70/h; split plus fast is +18.99/h under the ice-cream bottleneck. Rule: find the bottleneck first; a fast lane pays only when its own station has slack.
- **Slide 9 (75 s):** skills: same four staff on the same wage bill, all-generalist is +84.5 ± 5.1/h; one-way cross-training is +0.17/h ≈ 0. Shifts: a staggered 30-minute break pushes peak waiting 5.19 → 7.37 min and costs −49.4/h of profit; an extra mid-shift barista without an extra tea machine changes peak waiting by +0.06 min (not significant) and profit by −6.2/h.
- **Handover:** "Beyond people, ingredients and prices also decide profit — over to Member E."

**Q&A defence:** why do generalists earn more? — not because wages fall (the wage bill is identical) but because a shared queue reduces waiting and balking.

### Member E (slides 10–12, 3 minutes)

**Task:** cover the three "economics layer" blocks: inventory, pricing, SLA and fairness.

- **Slide 10 (60 s):** inventory: fill rate 98.0% → 99.95% is almost free (profit difference around 0.1/h); the lead-time cliff: 120 min → 80%, 240 min → 72%; perishable pearls start to waste above roughly 100 units per batch; when ice cream is short, "mixed order → tea" recovers +14.1/h, while a pearl shortage cannot be substituted.
- **Slide 11 (60 s):** pricing: service-neutral multiplier ×1.2 (ε = −0.5), profit +20–37%, 97.9% of demand retained; the profit optimum usually sits at the boundary because the model only charges waiting cost to customers who stay; recommend quoting ×1.1–1.2.
- **Slide 12 (60 s):** SLA: 3 / 5 / 8 min promises attain 41.9 / 61.4 / 81.9%, costing 38.4 / 25.5 / 11.9 CNY per hour, and compensation changes no service level — an SLA is a transfer. Fairness: the cap spends 5.06/h to cut p95 by 11%, but the mean-based fairness_gap rises, so we claim tail protection only; recommend a cap of 1.5–3 min.
- **Handover:** "None of these levers on its own beats the bundle — over to Member F."

**Q&A defence:** why can an SLA not raise attainment to 100%? — compensation does not change queueing; attainment only moves with capacity or a flatter peak.

### Member F (slides 13–18, 4 min 30 s)

**Task:** bundle, rules, evidence, demo, limits, closing; also keeps time and hands over between speakers.

- **Slide 13 (75 s):** the bundle: +118.1 ± 5.1/h, profit 240.1 → 358.2/h, p95 11.8 → 5.7 min, balking 101.7 → 16.2; single-lever ranking: capacity +76.6, pricing +76.0, fairness −6.7, SLA −25.5. This does not trade service for money — profit and waiting improve together.
- **Slide 14 (45 s):** four rules: staff to the peak; find the bottleneck before choosing a policy; protect the tail rather than the mean; price the SLA explicitly.
- **Slide 15 (45 s):** evidence: Python is reproducible (69 tests, 16 scenarios, fixed seeds, standard library only); report and demo run offline; the scenario library has auditable provenance; the AnyLogic archive cannot be rerun and feeds no number.
- **Slide 16 (45 s):** the 60-second live demo: switch scenario and policy, drag the demand-curve slider, play the queue timeline; everything is precomputed and the browser runs no simulation.
- **Slide 17 (30 s):** limits: synthetic scenarios, single-day model, waiting cost charged only to customers who stay, homogeneous skills; next steps: calibrate on real orders, multi-day inventory and rosters, customer-behaviour A/B.
- **Slide 18 (30 s):** Q&A ownership and thanks; remind A–F which areas they own.

**Q&A defence:** is the data real? — No: the scenarios are synthetic teaching cases, each flagged with uncertainty; the model is a mechanism-comparison tool, not a shop forecast.

---

## 3. Handovers and contingencies

- **Fixed handover line:** one sentence per speaker, for example "With the model fixed, we validate it with 16 scenarios — over to Member B."
- **Timing:** F must start slide 13 at 13:30; if running late, merge slide 17 into a single sentence — "limits are in section 14 of the report".
- **Demo failure:** say plainly "the demo page is precomputed data; the screenshot on slide 16 is the same result set", then cut to slide 18 and start Q&A.
- **Numbers pressed in Q&A:** always answer "paired comparison, 95% CI in the report table", point to `docs/experiments-layers.md`, and never recompute live.
- **Division slide (18):** replace Member A–F with the real names; add "speaker / backup" labels if the course requires them.

---

## 4. Rehearsal checklist

1. Each speaker walks through their own script first, making sure they **do not read the slides aloud** — conclusions and mechanisms only.
2. Two full run-throughs: the first for timing (within ±20 s), the second without the script, slides only.
3. Check that the numbers on slides 5, 7, 8, 10 and 12 can be quoted without notes — these are the pages most likely to draw questions.
4. Prepare three likely questions with one-sentence answers each (see each speaker's Q&A defence).
5. Ten minutes before presenting: open `demo/index.html` (locally) and the report page; leave a backup screenshot on the desktop.
