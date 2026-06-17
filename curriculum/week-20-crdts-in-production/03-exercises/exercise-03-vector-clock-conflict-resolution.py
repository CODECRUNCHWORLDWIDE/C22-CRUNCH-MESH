#!/usr/bin/env python3
# Exercise 3 — Vector-Clock Conflict Resolution (runnable)
#
# Goal: Build the conflict-resolution mechanism for the fields a CRDT CANNOT
#       auto-merge — the Dynamo/Riak model. Use VECTOR CLOCKS to detect whether
#       two writes are concurrent (a conflict) or causally ordered (one supersedes
#       the other). When concurrent, keep BOTH as SIBLINGS and resolve them with
#       APPLICATION-LAYER business logic (or, for a field where no automatic
#       resolution is safe, surface them to the user).
#
#       This is the case Lecture 2 §1 is about: automatic merge is the WRONG
#       policy for some fields (a shipping address), so you detect concurrency
#       and reconcile deliberately instead of silently picking a loser.
#
# Estimated time: 60 minutes. Runnable.
#
# WHAT THIS DEMONSTRATES
#   1. Causally-ordered writes: one vector clock dominates the other -> the later
#      write supersedes; NO conflict. (This is the easy case.)
#   2. Concurrent writes: neither clock dominates -> CONFLICT -> keep both as
#      siblings.
#   3. Application-layer resolution: two reconciliation strategies, chosen per
#      field semantics:
#        - MERGEABLE field (e.g. cart line-items): business logic merges siblings.
#        - NON-MERGEABLE field (e.g. shipping address): surface both; the user
#          must choose. Silent LWW here is data loss disguised as success.
#
# PREREQUISITES
#   - Python 3.10+. No external dependencies (pure standard library).
#   - The Week 2 vector-clock / happens-before mental model.
#
#   Run: python3 exercise-03-vector-clock-conflict-resolution.py

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any


# --- vector clocks ---------------------------------------------------------

VectorClock = dict[str, int]  # actor -> counter


def vc_dominates(a: VectorClock, b: VectorClock) -> bool:
    """True if clock `a` dominates `b`: every component a >= b AND a != b.

    Domination means a happened-after b (b is in a's causal past). If a
    dominates b, the write tagged with a SUPERSEDES the write tagged with b.
    """
    actors = set(a) | set(b)
    ge_all = all(a.get(k, 0) >= b.get(k, 0) for k in actors)
    strictly_gt = any(a.get(k, 0) > b.get(k, 0) for k in actors)
    return ge_all and strictly_gt


def vc_concurrent(a: VectorClock, b: VectorClock) -> bool:
    """True if a and b are CONCURRENT: neither dominates the other.

    Concurrent writes are a CONFLICT — they happened without knowledge of each
    other, so neither supersedes. This is the case that produces siblings.
    """
    return not vc_dominates(a, b) and not vc_dominates(b, a) and a != b


def vc_merge(a: VectorClock, b: VectorClock) -> VectorClock:
    """The component-wise max — the clock for a value derived from both."""
    return {k: max(a.get(k, 0), b.get(k, 0)) for k in set(a) | set(b)}


# --- a versioned value: a value plus the vector clock it was written under ---

@dataclass
class Versioned:
    value: Any
    clock: VectorClock = field(default_factory=dict)


def reconcile(writes: list[Versioned]) -> list[Versioned]:
    """Given concurrent/causal writes, return the set of SIBLINGS to keep.

    Drop any write that is dominated by another (it's been superseded). Keep the
    rest — if more than one survives, they are concurrent SIBLINGS the
    application must resolve.
    """
    survivors: list[Versioned] = []
    for w in writes:
        dominated = any(vc_dominates(other.clock, w.clock) for other in writes if other is not w)
        if not dominated:
            survivors.append(w)
    return survivors


# --- application-layer resolution strategies (chosen PER FIELD) -------------

def resolve_mergeable(siblings: list[Versioned]) -> Versioned:
    """For a field with a CORRECT business merge (e.g. cart line-items): union the
    items and SUM the quantities across siblings. The app KNOWS how to merge this
    field, so it does — automatically, but with field-specific logic, not LWW.
    """
    merged: dict[str, int] = {}
    clock: VectorClock = {}
    for s in siblings:
        for sku, qty in s.value.items():
            merged[sku] = merged.get(sku, 0) + qty
        clock = vc_merge(clock, s.clock)
    return Versioned(merged, clock)


def resolve_user_choice(siblings: list[Versioned]) -> Versioned:
    """For a NON-MERGEABLE field (e.g. a shipping address): there is NO safe
    automatic merge. The honest behavior is to SURFACE both siblings and require
    the user to choose. Here we simulate the user picking; in a real app you'd
    return both siblings to the client and prompt. The point: we did NOT silently
    LWW-discard one — that would be data loss disguised as success.
    """
    print("    [conflict] non-mergeable field has concurrent edits; surfacing siblings:")
    for i, s in enumerate(siblings):
        print(f"        sibling {i}: {s.value!r}  (clock {s.clock})")
    chosen = siblings[0]  # simulate the user choosing the first
    print(f"    [resolved] user chose sibling 0: {chosen.value!r}")
    return chosen


# --- the demonstrations ----------------------------------------------------

def demo_causal():
    print("=== Case 1: causally-ordered writes (NO conflict) ===")
    # B read A's write (clock {A:1}) then wrote, so B's clock {A:1, B:1} dominates.
    w1 = Versioned({"addr": "123 Oak St"}, {"A": 1})
    w2 = Versioned({"addr": "123 Oak St, Portland"}, {"A": 1, "B": 1})
    print(f"  w1 clock {w1.clock}, w2 clock {w2.clock}")
    print(f"  w2 dominates w1? {vc_dominates(w2.clock, w1.clock)}  -> w2 supersedes, keep only w2")
    survivors = reconcile([w1, w2])
    assert len(survivors) == 1 and survivors[0] is w2
    print(f"  survivors: {[s.value for s in survivors]}  (1 winner, no siblings)\n")


def demo_concurrent_mergeable():
    print("=== Case 2: concurrent writes to a MERGEABLE field (cart line-items) ===")
    # Two regions wrote concurrently: neither knew about the other.
    a = Versioned({"sku-APPLE": 2}, {"A": 2, "B": 1})
    b = Versioned({"sku-KIWI": 1}, {"A": 1, "B": 2})
    print(f"  A clock {a.clock}, B clock {b.clock}")
    print(f"  concurrent? {vc_concurrent(a.clock, b.clock)}  -> CONFLICT -> siblings")
    siblings = reconcile([a, b])
    assert len(siblings) == 2, "both concurrent writes should survive as siblings"
    resolved = resolve_mergeable(siblings)
    print(f"  app-merged (union + sum): {resolved.value}  (both writes preserved)\n")
    assert resolved.value == {"sku-APPLE": 2, "sku-KIWI": 1}


def demo_concurrent_nonmergeable():
    print("=== Case 3: concurrent writes to a NON-MERGEABLE field (shipping address) ===")
    a = Versioned({"street": "123 Oak St", "city": "Salem"}, {"A": 2, "B": 1})
    b = Versioned({"street": "456 Pine Ave", "city": "Portland"}, {"A": 1, "B": 2})
    print(f"  A clock {a.clock}, B clock {b.clock}")
    print(f"  concurrent? {vc_concurrent(a.clock, b.clock)}  -> CONFLICT -> siblings")
    siblings = reconcile([a, b])
    assert len(siblings) == 2
    resolved = resolve_user_choice(siblings)
    print(f"  resolved address: {resolved.value}")
    print("  (NOTE: silently LWW-picking one would have DROPPED a real edit. We")
    print("   surfaced both instead — the correct behavior when no safe merge exists.)\n")


def main() -> int:
    demo_causal()
    demo_concurrent_mergeable()
    demo_concurrent_nonmergeable()
    print("-" * 68)
    print("THE LESSON: vector clocks DETECT concurrency; the app RESOLVES it.")
    print("  - causally-ordered writes -> the later supersedes (no conflict).")
    print("  - concurrent + mergeable field -> app merges siblings with business logic.")
    print("  - concurrent + non-mergeable field -> surface siblings; user chooses.")
    print("  Silent LWW on a concurrent write is data loss disguised as success.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected output (abridged)
# -----------------------------------------------------------------------------
#
#   === Case 1: causally-ordered writes (NO conflict) ===
#     w2 dominates w1? True  -> w2 supersedes, keep only w2
#     survivors: [{'addr': '123 Oak St, Portland'}]  (1 winner, no siblings)
#
#   === Case 2: concurrent writes to a MERGEABLE field (cart line-items) ===
#     concurrent? True  -> CONFLICT -> siblings
#     app-merged (union + sum): {'sku-APPLE': 2, 'sku-KIWI': 1}  (both writes preserved)
#
#   === Case 3: concurrent writes to a NON-MERGEABLE field (shipping address) ===
#     concurrent? True  -> CONFLICT -> siblings
#     [conflict] non-mergeable field has concurrent edits; surfacing siblings:
#         sibling 0: {'street': '123 Oak St', 'city': 'Salem'}  (clock {'A': 2, 'B': 1})
#         sibling 1: {'street': '456 Pine Ave', 'city': 'Portland'}  (clock {'A': 1, 'B': 2})
#     [resolved] user chose sibling 0: ...
#
# ACCEPTANCE CRITERIA
#   [ ] Causally-ordered writes resolve to ONE winner (the dominating clock); no siblings.
#   [ ] Concurrent writes produce TWO siblings (neither dominates) — proven via the
#       vector clocks, not guessed.
#   [ ] The mergeable field is resolved by business logic (union + sum), preserving
#       BOTH writes — not LWW.
#   [ ] The non-mergeable field SURFACES both siblings rather than silently picking
#       one; you can state why that's the correct behavior when no safe merge exists.
#   [ ] You can map this onto the cart: items -> auto-merge (OR-set / mergeable),
#       shipping address -> siblings, last-modified -> LWW. One object, three policies.
# -----------------------------------------------------------------------------
