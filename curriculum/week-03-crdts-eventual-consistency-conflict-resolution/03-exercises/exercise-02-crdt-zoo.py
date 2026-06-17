#!/usr/bin/env python3
# Exercise 2 — The CRDT zoo (implement them; prove they converge)
#
# Goal: Implement the four canonical CRDTs -- G-counter, PN-counter, OR-set, and
#       LWW-register -- and demonstrate the week's headline promise: three replicas
#       take DIFFERENT concurrent updates during a partition, then merge in ANY
#       order with DUPLICATES, and all three converge to the SAME value with NO
#       data lost (for the counters and the OR-set).
#
# It also demonstrates LWW's footgun: the LWW-register converges too, but it
# SILENTLY DISCARDS a concurrent write -- the exact behavior CRDTs exist to beat.
#
# HOW TO RUN
#
#   python3 exercise-02-crdt-zoo.py
#
# It runs a partition-and-heal scenario for each CRDT, merging replicas in a
# shuffled+duplicated order, and self-checks convergence.
#
# ACCEPTANCE CRITERIA
#
#   [ ] G-counter: 3 replicas each increment their own slot; after merging in a
#       reordered+duplicated sequence, all hold the same value = the TRUE total.
#   [ ] PN-counter: increments and decrements across replicas converge correctly.
#   [ ] OR-set: concurrent adds all survive; a concurrent remove/re-add resolves
#       add-wins; all replicas converge to the same set.
#   [ ] LWW-register: converges, but the self-check SHOWS a concurrent write was
#       discarded -- the documented footgun.
#   [ ] Self-check prints "ALL CHECKS PASS".
#
# Expected output (shape) is at the bottom of this file.

from __future__ import annotations

import itertools
import random


# ---------------------------------------------------------------------------
# G-counter
# ---------------------------------------------------------------------------

class GCounter:
    def __init__(self, replica_id: int, n: int):
        self.id = replica_id
        self.counts = [0] * n

    def increment(self, by: int = 1):
        self.counts[self.id] += by

    def value(self) -> int:
        return sum(self.counts)

    def merge(self, other: "GCounter"):
        self.counts = [max(a, b) for a, b in zip(self.counts, other.counts)]

    def copy(self) -> "GCounter":
        c = GCounter(self.id, len(self.counts))
        c.counts = list(self.counts)
        return c


# ---------------------------------------------------------------------------
# PN-counter (two G-counters)
# ---------------------------------------------------------------------------

class PNCounter:
    def __init__(self, replica_id: int, n: int):
        self.P = GCounter(replica_id, n)
        self.N = GCounter(replica_id, n)

    def increment(self, by: int = 1): self.P.increment(by)
    def decrement(self, by: int = 1): self.N.increment(by)
    def value(self) -> int:           return self.P.value() - self.N.value()

    def merge(self, other: "PNCounter"):
        self.P.merge(other.P)
        self.N.merge(other.N)

    def copy(self) -> "PNCounter":
        c = PNCounter(self.P.id, len(self.P.counts))
        c.P = self.P.copy()
        c.N = self.N.copy()
        return c


# ---------------------------------------------------------------------------
# OR-set (observed-remove set)
# ---------------------------------------------------------------------------

class ORSet:
    def __init__(self, replica_id: int):
        self.id = replica_id
        self.counter = 0
        self.adds: set[tuple] = set()      # (element, tag)
        self.removes: set[tuple] = set()   # tags

    def _fresh_tag(self) -> tuple:
        self.counter += 1
        return (self.id, self.counter)

    def add(self, e):
        self.adds.add((e, self._fresh_tag()))

    def remove(self, e):
        observed = {tag for (elem, tag) in self.adds if elem == e}
        self.removes |= observed

    def value(self) -> set:
        live_tags = {tag for (_, tag) in self.adds} - self.removes
        return {e for (e, tag) in self.adds if tag in live_tags}

    def merge(self, other: "ORSet"):
        self.adds |= other.adds
        self.removes |= other.removes

    def copy(self) -> "ORSet":
        c = ORSet(self.id)
        c.counter = self.counter
        c.adds = set(self.adds)
        c.removes = set(self.removes)
        return c


# ---------------------------------------------------------------------------
# LWW-register (the footgun)
# ---------------------------------------------------------------------------

class LWWRegister:
    def __init__(self, replica_id: int):
        self.id = replica_id
        self.value_ts = (None, -1, -1)   # (value, timestamp, replica_id tiebreak)

    def set(self, value, timestamp: int):
        self.value_ts = (value, timestamp, self.id)

    def value(self):
        return self.value_ts[0]

    def merge(self, other: "LWWRegister"):
        # Higher timestamp wins; tie broken by replica id. This is the footgun:
        # the losing concurrent write is silently DISCARDED.
        _, ts_a, id_a = self.value_ts
        _, ts_b, id_b = other.value_ts
        if (ts_b, id_b) > (ts_a, id_a):
            self.value_ts = other.value_ts

    def copy(self) -> "LWWRegister":
        c = LWWRegister(self.id)
        c.value_ts = self.value_ts
        return c


# ---------------------------------------------------------------------------
# Convergence harness: merge replicas in a shuffled + duplicated order
# ---------------------------------------------------------------------------

def converge_all(replicas: list, label: str) -> bool:
    """Merge every replica into every other, in a shuffled order WITH duplicates,
    then assert all replicas reach the same value. This stress-tests commutativity,
    associativity, and idempotence at once."""
    snapshots = [r.copy() for r in replicas]

    # Build a merge schedule: all ordered pairs, shuffled, then DUPLICATED.
    pairs = list(itertools.permutations(range(len(replicas)), 2))
    random.shuffle(pairs)
    schedule = pairs + pairs  # duplicate every merge (idempotence test)
    random.shuffle(schedule)

    for (i, j) in schedule:
        replicas[i].merge(snapshots[j])   # merge a fixed snapshot of j into i

    # Run a second full round so everyone has seen everyone (gossip to fixpoint).
    final_snaps = [r.copy() for r in replicas]
    for i in range(len(replicas)):
        for j in range(len(replicas)):
            if i != j:
                replicas[i].merge(final_snaps[j])

    values = [r.value() for r in replicas]
    converged = all(_eq(v, values[0]) for v in values)
    print(f"  [{label}] final values per replica: {values}  -> "
          f"{'CONVERGED' if converged else 'DIVERGED'}")
    return converged, values[0]


def _eq(a, b) -> bool:
    if isinstance(a, set) and isinstance(b, set):
        return a == b
    return a == b


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_gcounter() -> bool:
    print("=== G-counter: 3 regions count clicks during a partition ===")
    r = [GCounter(i, 3) for i in range(3)]
    r[0].increment(5)   # region 0: 5 clicks
    r[1].increment(3)   # region 1: 3 clicks
    r[2].increment(2)   # region 2: 2 clicks
    converged, val = converge_all(r, "g-counter")
    ok = converged and val == 10   # 5+3+2, NOTHING lost
    print(f"  expected total = 10 (no increment lost), got {val} -> {'OK' if ok else 'FAIL'}\n")
    return ok


def scenario_pncounter() -> bool:
    print("=== PN-counter: likes and unlikes across 3 replicas ===")
    r = [PNCounter(i, 3) for i in range(3)]
    r[0].increment(4)   # +4 likes
    r[1].increment(3)   # +3 likes
    r[1].decrement(2)   # -2 unlikes
    r[2].decrement(1)   # -1 unlike
    converged, val = converge_all(r, "pn-counter")
    ok = converged and val == (4 + 3 - 2 - 1)   # = 4
    print(f"  expected net = 4, got {val} -> {'OK' if ok else 'FAIL'}\n")
    return ok


def scenario_orset() -> bool:
    print("=== OR-set: concurrent cart edits + add-wins remove/re-add ===")
    r = [ORSet(i) for i in range(3)]
    r[0].add("milk")           # all three start by adding different items
    r[1].add("eggs")
    r[2].add("bread")
    # Replica 0 syncs milk to replica 1, which then removes it...
    r[1].merge(r[0].copy())
    r[1].remove("milk")        # r1 observed milk's tag, removes it
    # ...meanwhile replica 2 concurrently RE-ADDS milk (a fresh, unobserved tag).
    r[2].add("milk")
    converged, val = converge_all(r, "or-set")
    # add-wins: the concurrent re-add of milk survives r1's remove.
    expected = {"milk", "eggs", "bread"}
    ok = converged and val == expected
    print(f"  expected {expected} (add-wins keeps re-added milk), got {val} -> "
          f"{'OK' if ok else 'FAIL'}\n")
    return ok


def scenario_lww() -> bool:
    print("=== LWW-register: converges, but DISCARDS a concurrent write (footgun) ===")
    r = [LWWRegister(i) for i in range(3)]
    r[0].set("Loves hiking", timestamp=100)
    r[1].set("PhD candidate", timestamp=101)   # concurrent, higher timestamp
    r[2].set("Coffee addict", timestamp=99)    # concurrent, lower timestamp
    converged, val = converge_all(r, "lww-register")
    # Converges to the highest-timestamp value; the other TWO writes are GONE.
    ok = converged and val == "PhD candidate"
    print(f"  converged to {val!r}; the writes 'Loves hiking' and 'Coffee addict' "
          f"were SILENTLY DISCARDED.")
    print(f"  -> {'OK (and footgun demonstrated)' if ok else 'FAIL'}\n")
    return ok


def main() -> None:
    random.seed(42)   # determinism for the expected-output block
    results = [
        scenario_gcounter(),
        scenario_pncounter(),
        scenario_orset(),
        scenario_lww(),
    ]
    print("=================== THE LESSON ===================")
    print("  The G-counter, PN-counter, and OR-set converged AND preserved every")
    print("  concurrent update -- no data lost, regardless of merge order/duplication.")
    print("  The LWW-register also converged, but DISCARDED concurrent writes. That")
    print("  difference -- lossless merge vs lossy last-writer-wins -- is the week.\n")

    print("=================== SUMMARY ===================")
    print("ALL CHECKS PASS" if all(results) else f"SOME CHECKS FAILED: {results}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Expected output (shape; with seed 42 the values are deterministic)
# ---------------------------------------------------------------------------
#
# === G-counter: 3 regions count clicks during a partition ===
#   [g-counter] final values per replica: [10, 10, 10]  -> CONVERGED
#   expected total = 10 (no increment lost), got 10 -> OK
#
# === PN-counter: likes and unlikes across 3 replicas ===
#   [pn-counter] final values per replica: [4, 4, 4]  -> CONVERGED
#   expected net = 4, got 4 -> OK
#
# === OR-set: concurrent cart edits + add-wins remove/re-add ===
#   [or-set] final values per replica: [{'milk','eggs','bread'}, ...]  -> CONVERGED
#   expected {'milk','eggs','bread'} (add-wins keeps re-added milk), got {...} -> OK
#
# === LWW-register: converges, but DISCARDS a concurrent write (footgun) ===
#   [lww-register] final values per replica: ['PhD candidate', ...]  -> CONVERGED
#   converged to 'PhD candidate'; the writes 'Loves hiking' and 'Coffee addict'
#   were SILENTLY DISCARDED.
#   -> OK (and footgun demonstrated)
#
# =================== SUMMARY ===================
# ALL CHECKS PASS
