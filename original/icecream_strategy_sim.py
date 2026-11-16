# Illustrative discrete-event simulation for SYE5006 group project.
# Compares mixed-order delivery strategies at a bubble tea shop that also
# sells fast-melting items (soft serve). Replace the ASSUMED parameters
# below with field measurements, then rerun.

import heapq
import random

# ---- ASSUMED parameters (replace with field data) ----
ORDER_TIME = 0.4          # min, order entry
TEA_RANGE = (2.0, 4.0)    # min, uniform
CONE_RANGE = (0.5, 1.0)   # min, uniform
P_TEA, P_CONE = 0.60, 0.25  # rest are mixed orders
WORKERS = 2               # cross-trained staff, shared pool
MELT_WINDOW = 5.0         # min, cone quality threshold (swept elsewhere)
SIM_MIN = 480             # 8-hour day
WARMUP = 60
REPS = 6                  # keep small: this is a demo sweep, not the final study


def simulate(lam, seed, strategy):
    """strategy: 'A' make-serve-first | 'Bs' sync-FCFS | 'Bp' sync-jump-queue"""
    rnd = random.Random(seed)
    orders = []
    t = 0.0
    while t < SIM_MIN:
        t += rnd.expovariate(lam)
        u = rnd.random()
        typ = "tea" if u < P_TEA else ("cone" if u < P_TEA + P_CONE else "mix")
        orders.append((t, typ))

    recs = [{"arr": a, "type": k, "tea": None, "cone": None, "leave": None}
            for a, k in orders]
    heap, ready_heap, tasks, seq = [], [], {}, 0

    def add(ready_t, prio, dur, oid, kind):
        nonlocal seq
        heapq.heappush(heap, (ready_t, seq))
        tasks[seq] = (ready_t, prio, dur, oid, kind)
        seq += 1

    for i, (t0, _) in enumerate(orders):
        add(t0, 1, ORDER_TIME, i, "order")

    worker_free = [0.0] * WORKERS
    busy = 0.0

    def tea_dur():
        return rnd.uniform(*TEA_RANGE)

    def cone_dur():
        return rnd.uniform(*CONE_RANGE)

    while heap or ready_heap:
        tf = min(worker_free)
        while heap and heap[0][0] <= tf:
            s = heapq.heappop(heap)[1]
            heapq.heappush(ready_heap, (tasks[s][1], s))
        if not ready_heap:
            s = heapq.heappop(heap)[1]
            heapq.heappush(ready_heap, (tasks[s][1], s))
        _, s = heapq.heappop(ready_heap)  # priority first, FIFO within level
        ready_t, _, dur, oid, kind = tasks[s]
        w = min(range(WORKERS), key=lambda k: worker_free[k])
        start = max(ready_t, worker_free[w])
        end = start + dur
        worker_free[w] = end
        busy += dur

        rec, typ = recs[oid], recs[oid]["type"]
        if kind == "order":
            if typ == "tea":
                add(end, 1, tea_dur(), oid, "tea")
            elif typ == "cone":
                add(end, 1, cone_dur(), oid, "cone")
            elif strategy == "A":
                add(end, 1, cone_dur(), oid, "cone")   # cone first, tea chained
            else:
                add(end, 1, tea_dur(), oid, "tea")
        elif kind == "cone":
            rec["cone"] = end
            if typ == "mix":
                if strategy == "A":
                    add(end, 1, tea_dur(), oid, "tea")
                else:
                    rec["leave"] = end                  # cone last = served fresh
            else:
                rec["leave"] = end
        elif kind == "tea":
            rec["tea"] = end
            if typ == "mix":
                if strategy == "A":
                    rec["leave"] = end   # cone was made first; tea ends the visit
                else:
                    prio = 0 if strategy == "Bp" else 1
                    add(end, prio, cone_dur(), oid, "cone")
            else:
                rec["leave"] = end
    return recs, busy


def run_all():
    lams = [0.30, 0.45, 0.58]
    print(f"Assumptions: order {ORDER_TIME} min | tea {TEA_RANGE} | cone "
          f"{CONE_RANGE} | mix share {1-P_TEA-P_CONE:.0%} | "
          f"{WORKERS} cross-trained staff | melt window {MELT_WINDOW} min")
    print(f"{'lam':>5} {'strat':>5} {'melt%':>7} {'mixLOS':>7} {'teaLOS':>7} "
          f"{'coneLOS':>8} {'util':>6}")
    for lam in lams:
        for strat in ("A", "Bs", "Bp"):
            print(f"running lam={lam} strategy={strat} ...", flush=True)
            melts, mix_l, tea_l, cone_l, utils_ = [], [], [], [], []
            for rep in range(REPS):
                recs, busy = simulate(lam, 1000 * rep + hash(strat) % 997, strat)
                utils_.append(busy / (WORKERS * SIM_MIN))
                for r in recs:
                    if r["arr"] < WARMUP or r["leave"] is None:
                        continue
                    los = r["leave"] - r["arr"]
                    if r["type"] == "mix":
                        mix_l.append(los)
                        if strat == "A":
                            if r["tea"] and r["cone"]:
                                melts.append((r["tea"] - r["cone"]) > MELT_WINDOW)
                    elif r["type"] == "tea":
                        tea_l.append(los)
                    else:
                        cone_l.append(los)
            melt_pct = 100 * sum(melts) / len(melts) if melts else 0.0
            print(f"{lam:>5.2f} {strat:>5} {melt_pct:>6.1f}% "
                  f"{mean(mix_l):>7.2f} {mean(tea_l):>7.2f} "
                  f"{mean(cone_l):>8.2f} {mean(utils_):>6.1%}")
        print()


def mean(xs):
    return sum(xs) / len(xs)


if __name__ == "__main__":
    run_all()
