# Mixed-order fulfillment study. A customer orders tea + ice cream together:
#   Synchro: one clerk makes order + tea + ice cream as a single 2.83 min
#            atomic job, hands everything over when the tea is done.
#   Split:   the ice cream component jumps the queue (fast item), the tea
#            component waits in the normal FCFS queue; the customer leaves
#            when the tea is ready. Melting is out of scope by design: both
#            policies exist to avoid it.

import heapq
import random

ORDER_TIME = 0.5      # min, taken once per order
TEA_TIME = 2.0        # min
ICE_TIME = 0.333      # min
BREAD_TIME = 0.167    # min
# order shares: tea-only / bread-only / ice-only / mixed(tea+ice)
P_TEA, P_BREAD, P_ICE, P_MIX = 0.55, 0.20, 0.05, 0.20
WORKERS = 3
SIM_MIN = 480
WARMUP = 60
REPS = 200


def simulate(lam, seed, split_delivery):
    rnd = random.Random(seed)
    jobs, seq = [], 0

    def add(t0, prio, dur, kind, cid):
        nonlocal seq
        jobs.append((t0, seq, prio, dur, kind, cid))
        seq += 1

    customers = []
    t = 0.0
    while t < SIM_MIN:
        t += rnd.expovariate(lam)
        cid = len(customers)
        u = rnd.random()
        if u < P_TEA:
            add(t, 1, ORDER_TIME + TEA_TIME, "tea", cid)
            customers.append({"arr": t, "tea": None, "ice": None, "kind": "tea"})
        elif u < P_TEA + P_BREAD:
            add(t, 1, ORDER_TIME + BREAD_TIME, "bread", cid)
            customers.append({"arr": t, "tea": None, "ice": None, "kind": "bread"})
        elif u < P_TEA + P_BREAD + P_ICE:
            add(t, 1, ORDER_TIME + ICE_TIME, "ice", cid)
            customers.append({"arr": t, "tea": None, "ice": None, "kind": "ice"})
        else:
            customers.append({"arr": t, "tea": None, "ice": None, "kind": "mix"})
            if split_delivery:
                add(t, 0, ORDER_TIME + ICE_TIME, "mixIce", cid)  # fast item
                add(t, 1, TEA_TIME, "mixTea", cid)               # queues normally
            else:
                add(t, 1, ORDER_TIME + TEA_TIME + ICE_TIME, "mixAll", cid)

    jobs.sort()
    task = {s: (prio, dur, kind, cid, t0) for t0, s, prio, dur, kind, cid in jobs}
    heap = [(t0, s) for t0, s, *_ in jobs]
    heapq.heapify(heap)
    ready, worker_free = [], [0.0] * WORKERS
    busy = 0.0
    while heap or ready:
        tf = min(worker_free)
        while heap and heap[0][0] <= tf:
            t0, s = heapq.heappop(heap)
            heapq.heappush(ready, (task[s][0], s))
        if not ready:
            t0, s = heapq.heappop(heap)
            heapq.heappush(ready, (task[s][0], s))
        _, s = heapq.heappop(ready)
        prio, dur, kind, cid, t0 = task[s]
        w = min(range(WORKERS), key=lambda k: worker_free[k])
        start = max(t0, tf)
        end = start + dur
        worker_free[w] = end
        busy += dur
        if kind in ("tea", "mixTea", "mixAll", "bread", "ice"):
            customers[cid]["tea"] = end
        elif kind in ("ice", "mixIce"):
            customers[cid]["ice"] = end

    all_los, mix_los, ice_hand, bread_los = [], [], [], []
    served = 0
    for c in customers:
        if c["arr"] < WARMUP or c["tea"] is None:
            continue
        ice_done = c["ice"] if c["ice"] is not None else c["tea"]
        depart = max(c["tea"], ice_done)
        all_los.append(depart - c["arr"])
        served += 1
        if c["kind"] == "mix":
            mix_los.append(depart - c["arr"])
            ice_hand.append(ice_done - c["arr"])
        elif c["kind"] == "bread":
            bread_los.append(depart - c["arr"])
    return {
        "los": sum(all_los) / max(1, len(all_los)),
        "mix": sum(mix_los) / max(1, len(mix_los)),
        "icehand": sum(ice_hand) / max(1, len(ice_hand)),
        "bread": sum(bread_los) / max(1, len(bread_los)),
        "served": served,
        "util": busy / (WORKERS * SIM_MIN),
    }


def run_all():
    import sys
    global WORKERS
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else WORKERS
    lams = [float(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 \
        else [0.5, 0.8, 1.1, 1.25]
    WORKERS = workers
    print(f"mixed-order study (no melt) | shares tea {P_TEA:.0%} / bread "
          f"{P_BREAD:.0%} / ice {P_ICE:.0%} / MIXED {P_MIX:.0%} | {workers} staff")
    print(f"{'lam':>5} {'policy':>8} {'allLOS':>7} {'mixLOS':>7} "
          f"{'iceHand':>8} {'bread':>6} {'served':>7} {'util':>6}")
    for lam in lams:
        for split in (False, True):
            pol = "Synchro" if not split else "Split"
            acc = {}
            for rep in range(REPS):
                r = simulate(lam, 9000 * rep + rep, split)
                for k, v in r.items():
                    acc[k] = acc.get(k, 0.0) + v
            m = {k: v / REPS for k, v in acc.items()}
            print(f"{lam:>5.2f} {pol:>8} {m['los']:>7.2f} {m['mix']:>7.2f} "
                  f"{m['icehand']:>8.2f} {m['bread']:>6.2f} {m['served']:>7.0f} "
                  f"{m['util']:>6.1%}")
        print()


if __name__ == "__main__":
    run_all()
