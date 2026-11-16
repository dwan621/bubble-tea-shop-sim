# Illustrative DES: cross-trained staff serving tea (slow) plus pre-made
# bread and soft-serve ice cream (fast transactions). Each customer is one
# atomic job (order + make owned by the same clerk). Compares FCFS vs
# fast-item priority. Replace ASSUMED parameters with field data and rerun.

import heapq
import random

ORDER_TIME = 0.5          # min, order entry, 30s
TEA_RANGE = (2.0, 2.0)    # min, fixed 2 min per assumption (add variance with real data)
BREAD_TIME = 0.167        # min, 10s order + pack + pay
ICE_TIME = 0.33           # min, 20s soft-serve dispensing
P_TEA, P_BREAD, P_ICE = 0.65, 0.20, 0.15  # assumed class shares
WORKERS = 3
SIM_MIN = 480
WARMUP = 60
REPS = 6


def simulate(lam, seed, bread_first):
    rnd = random.Random(seed)
    orders = []
    t = 0.0
    while t < SIM_MIN:
        t += rnd.expovariate(lam)
        u = rnd.random()
        typ = "tea" if u < P_TEA else ("bread" if u < P_TEA + P_BREAD else "ice")
        orders.append((t, typ))

    recs = [{"arr": a, "type": k, "leave": None} for a, k in orders]
    heap, ready_heap, tasks, seq = [], [], {}, 0

    def add(ready_t, prio, dur, oid, kind):
        nonlocal seq
        heapq.heappush(heap, (ready_t, seq))
        tasks[seq] = (ready_t, prio, dur, oid, kind)
        seq += 1

    # Fast-item times above are make-only; prepend the shared order step so the
    # workload matches the AnyLogic model (order + make owned by one clerk).
    for i, (t0, typ) in enumerate(orders):
        if typ == "bread":
            add(t0, 0 if bread_first else 1, ORDER_TIME + BREAD_TIME, i, "bread")
        elif typ == "ice":
            add(t0, 0 if bread_first else 1, ORDER_TIME + ICE_TIME, i, "ice")
        else:
            add(t0, 1, ORDER_TIME + rnd.uniform(*TEA_RANGE), i, "tea")

    worker_free = [0.0] * WORKERS
    busy = 0.0

    while heap or ready_heap:
        tf = min(worker_free)
        while heap and heap[0][0] <= tf:
            s = heapq.heappop(heap)[1]
            heapq.heappush(ready_heap, (tasks[s][1], s))
        if not ready_heap:
            s = heapq.heappop(heap)[1]
            heapq.heappush(ready_heap, (tasks[s][1], s))
        _, s = heapq.heappop(ready_heap)
        ready_t, _, dur, oid, kind = tasks[s]
        w = min(range(WORKERS), key=lambda k: worker_free[k])
        start = max(ready_t, worker_free[w])
        end = start + dur
        worker_free[w] = end
        busy += dur

        rec, typ = recs[oid], recs[oid]["type"]
        if kind == "tea":
            rec["leave"] = end
        else:  # bread transaction done
            rec["leave"] = end

    los = {"tea": [], "bread": [], "ice": []}
    for r in recs:
        if r["arr"] >= WARMUP and r["leave"] is not None:
            los[r["type"]].append(r["leave"] - r["arr"])
    return los, busy / (WORKERS * SIM_MIN)


def mean(xs):
    return sum(xs) / len(xs)


def run_all():
    import sys
    global WORKERS
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else WORKERS
    lams = [float(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 \
        else [0.30, 0.50, 0.62]
    WORKERS = workers
    print(f"Assumptions: order {ORDER_TIME} min | tea make {TEA_RANGE} min | "
          f"bread {BREAD_TIME} min | ice {ICE_TIME} min | shares tea {P_TEA:.0%} / "
          f"bread {P_BREAD:.0%} / ice {P_ICE:.0%} | "
          f"{WORKERS} cross-trained staff")
    print(f"{'lam':>5} {'policy':>8} {'breadLOS':>9} {'iceLOS':>7} "
          f"{'teaLOS':>7} {'allLOS':>7} {'util':>6}")
    print(f"workers={workers}")
    for lam in lams:
        for bread_first in (False, True):
            pol = "FCFS" if not bread_first else "BreadPri"
            los_all, utils_ = {"tea": [], "bread": [], "ice": []}, []
            for rep in range(REPS):
                los, util = simulate(lam, 7000 * rep + rep, bread_first)
                utils_.append(util)
                for k in los_all:
                    los_all[k].extend(los[k])
            all_flat = los_all["tea"] + los_all["bread"] + los_all["ice"]
            print(f"{lam:>5.2f} {pol:>8} {mean(los_all['bread']):>9.2f} "
                  f"{mean(los_all['ice']):>7.2f} {mean(los_all['tea']):>7.2f} "
                  f"{mean(all_flat):>7.2f} {mean(utils_):>6.1%}")
        print()


if __name__ == "__main__":
    run_all()
