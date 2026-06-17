#!/usr/bin/env python3
# Exercise 2 — Lamport and vector clocks (detect the concurrency Lamport hides)
#
# Goal: Implement Lamport timestamps and vector clocks, run both on the SAME
#       recorded message trace, and demonstrate the one thing vector clocks can do
#       that Lamport cannot: DETECT CONCURRENCY. Two genuinely concurrent events get
#       equal-ish Lamport numbers (ordered arbitrarily by tiebreak) but INCOMPARABLE
#       vectors (correctly flagged concurrent).
#
# This is Lecture 1 made executable: "Lamport gives a total order but cannot detect
# concurrency; vector clocks detect concurrency at O(N) metadata cost."
#
# HOW TO RUN
#
#   python3 exercise-02-vector-clocks.py
#
# It builds a 3-process event trace with a known concurrent pair, runs both clocks,
# prints each event's Lamport timestamp and vector, then classifies every pair of
# events as happens-before / happens-after / CONCURRENT using the vector clock, and
# shows where the Lamport timestamp would have misled you.
#
# ACCEPTANCE CRITERIA
#
#   [ ] Every event prints a Lamport timestamp and a vector clock.
#   [ ] The clock condition holds: for every causal edge a -> b, L(a) < L(b).
#   [ ] The known concurrent pair is flagged CONCURRENT by the vector clock.
#   [ ] The program demonstrates a pair where Lamport timestamps are equal (or give
#       a misleading order) but the vector clock correctly says "concurrent".
#   [ ] Self-check prints "ALL CHECKS PASS".
#
# Expected output (shape) is at the bottom of this file.

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------

class LamportClock:
    """A single integer counter. Total order consistent with happens-before, but
    CANNOT detect concurrency."""

    def __init__(self) -> None:
        self.t = 0

    def tick(self) -> int:
        self.t += 1
        return self.t

    def receive(self, msg_t: int) -> int:
        self.t = max(self.t, msg_t) + 1
        return self.t


class VectorClock:
    """One counter per process. Partial order that CAN detect concurrency:
    incomparable vectors == concurrent events."""

    def __init__(self, node_id: int, n: int) -> None:
        self.id = node_id
        self.v = [0] * n

    def tick(self) -> list[int]:
        self.v[self.id] += 1
        return list(self.v)

    def receive(self, msg_v: list[int]) -> list[int]:
        self.v = [max(a, b) for a, b in zip(self.v, msg_v)]
        self.v[self.id] += 1
        return list(self.v)


def vc_leq(a: list[int], b: list[int]) -> bool:
    """a <= b iff a[k] <= b[k] for all k."""
    return all(x <= y for x, y in zip(a, b))


def relation(a: list[int], b: list[int]) -> str:
    """Classify two vector clocks: 'a->b', 'b->a', 'equal', or 'concurrent'."""
    if a == b:
        return "equal"
    if vc_leq(a, b):
        return "a->b (a happens-before b)"
    if vc_leq(b, a):
        return "b->a (b happens-before a)"
    return "concurrent (a || b)"


# ---------------------------------------------------------------------------
# A recorded event trace
# ---------------------------------------------------------------------------

@dataclass
class Event:
    name: str
    proc: int
    kind: str                 # "local", "send", "recv"
    msg_id: int | None = None  # send/recv share a msg_id
    lamport: int = 0
    vector: list[int] = field(default_factory=list)


def build_trace() -> list[Event]:
    """Three processes (0,1,2). Hand-built so we KNOW the causal structure.

    Causal edges (happens-before):
      P0: a0 -> b0(send m1) -> e0
      P1: a1 -> recv m1 (d1) -> f1(send m2)
      P2: a2 -> recv m2 (g2)
      cross: b0 -> d1 (m1), f1 -> g2 (m2)

    KNOWN concurrent pairs: a0 || a1 || a2 (the three initial local events on
    different processes, none caused by another); also e0 || (most of P1/P2).
    """
    return [
        Event("a0", 0, "local"),
        Event("b0", 0, "send", msg_id=1),
        Event("a1", 1, "local"),
        Event("d1", 1, "recv", msg_id=1),
        Event("f1", 1, "send", msg_id=2),
        Event("e0", 0, "local"),
        Event("a2", 2, "local"),
        Event("g2", 2, "recv", msg_id=2),
    ]


def run_clocks(trace: list[Event], n: int) -> None:
    """Replay the trace, stamping each event with a Lamport timestamp and a vector.

    We process events in a causally valid order: a send is processed before its
    matching recv. The trace above is already in such an order.
    """
    lamports = [LamportClock() for _ in range(n)]
    vectors = [VectorClock(i, n) for i in range(n)]
    sent_lamport: dict[int, int] = {}
    sent_vector: dict[int, list[int]] = {}

    for ev in trace:
        p = ev.proc
        if ev.kind in ("local", "send"):
            ev.lamport = lamports[p].tick()
            ev.vector = vectors[p].tick()
            if ev.kind == "send":
                sent_lamport[ev.msg_id] = ev.lamport
                sent_vector[ev.msg_id] = list(ev.vector)
        else:  # recv
            ev.lamport = lamports[p].receive(sent_lamport[ev.msg_id])
            ev.vector = vectors[p].receive(sent_vector[ev.msg_id])


# ---------------------------------------------------------------------------
# Reporting and self-checks
# ---------------------------------------------------------------------------

def main() -> None:
    n = 3
    trace = build_trace()
    run_clocks(trace, n)

    by_name = {ev.name: ev for ev in trace}

    print("=================== EVENT STAMPS ===================")
    print(f"{'event':6} {'proc':4} {'kind':6} {'lamport':>7}  vector")
    for ev in trace:
        print(f"{ev.name:6} {ev.proc:<4} {ev.kind:6} {ev.lamport:>7}  {ev.vector}")
    print()

    # Self-check 1: the clock condition on every known causal edge.
    causal_edges = [
        ("a0", "b0"), ("b0", "e0"),          # P0 process order
        ("a1", "d1"), ("d1", "f1"),          # P1 process order
        ("a2", "g2"),                        # P2 process order
        ("b0", "d1"),                        # m1 send->recv
        ("f1", "g2"),                        # m2 send->recv
    ]
    print("=========== CLOCK CONDITION (a->b => L(a)<L(b)) ===========")
    clock_ok = True
    for a, b in causal_edges:
        la, lb = by_name[a].lamport, by_name[b].lamport
        rel = relation(by_name[a].vector, by_name[b].vector)
        ok = la < lb and rel.startswith("a->b")
        clock_ok = clock_ok and ok
        print(f"  {a} -> {b}:  L({a})={la} < L({b})={lb}  [{'OK' if la<lb else 'FAIL'}]"
              f"   vector says: {rel}")
    print()

    # Self-check 2: the KNOWN concurrent pairs are flagged concurrent by vectors.
    print("=========== CONCURRENCY DETECTION (vector clocks) ===========")
    concurrent_pairs = [("a0", "a1"), ("a1", "a2"), ("a0", "a2"), ("e0", "f1")]
    concurrency_ok = True
    for a, b in concurrent_pairs:
        rel = relation(by_name[a].vector, by_name[b].vector)
        is_conc = rel.startswith("concurrent")
        concurrency_ok = concurrency_ok and is_conc
        la, lb = by_name[a].lamport, by_name[b].lamport
        print(f"  {a} vs {b}: vector -> {rel:35} | Lamport: L({a})={la}, L({b})={lb}"
              f" (Lamport would impose an arbitrary order, HIDING the concurrency)")
    print()

    # The headline demonstration: a pair Lamport orders but vectors call concurrent.
    print("=========== THE LESSON ===========")
    a, b = "a1", "a2"
    la, lb = by_name[a].lamport, by_name[b].lamport
    rel = relation(by_name[a].vector, by_name[b].vector)
    print(f"  {a} (L={la}, V={by_name[a].vector}) and {b} (L={lb}, V={by_name[b].vector}):")
    print(f"    Lamport timestamps differ or tie and would pick a WINNER by tiebreak,")
    print(f"    silently asserting an order. The vector clock says: {rel}.")
    print(f"    Detecting that they are concurrent is the prerequisite for MERGING")
    print(f"    them (Week 3 CRDTs) instead of discarding one via last-writer-wins.")
    print()

    print("=================== SUMMARY ===================")
    if clock_ok and concurrency_ok:
        print("ALL CHECKS PASS")
    else:
        print(f"SOME CHECKS FAILED (clock_ok={clock_ok}, concurrency_ok={concurrency_ok})")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Expected output (shape)
# ---------------------------------------------------------------------------
#
# =================== EVENT STAMPS ===================
# event  proc kind   lamport  vector
# a0     0    local        1  [1, 0, 0]
# b0     0    send         2  [2, 0, 0]
# a1     1    local        1  [0, 1, 0]
# d1     1    recv         3  [2, 2, 0]
# f1     1    send         4  [2, 3, 0]
# e0     0    local        3  [3, 0, 0]
# a2     2    local        1  [0, 0, 1]
# g2     2    recv         5  [2, 3, 2]
#
# =========== CLOCK CONDITION (a->b => L(a)<L(b)) ===========
#   a0 -> b0:  L(a0)=1 < L(b0)=2  [OK]   vector says: a->b (a happens-before b)
#   ... every causal edge OK, vector agrees ...
#
# =========== CONCURRENCY DETECTION (vector clocks) ===========
#   a0 vs a1: vector -> concurrent (a || b)              | Lamport: L(a0)=1, L(a1)=1 ...
#   a1 vs a2: vector -> concurrent (a || b)              | Lamport: L(a1)=1, L(a2)=1 ...
#   ...
#
# =================== SUMMARY ===================
# ALL CHECKS PASS
#
# Note: a0, a1, a2 all get Lamport timestamp 1 (they are the first event on each
# process). Lamport CANNOT tell they are concurrent -- it just hands them the same
# number and lets a process-id tiebreak impose an arbitrary order. The vector clock
# sees [1,0,0], [0,1,0], [0,0,1] are mutually incomparable => CONCURRENT. That is
# the entire difference, and the reason CRDTs carry vector-style metadata.
