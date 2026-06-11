#!/usr/bin/env python3
# Exercise 2 — Property Tests for the OR-Set CRDT Merge (runnable)
#
# Goal: Prove, with Hypothesis property-based tests, that an OR-set CRDT's merge
#       satisfies the three algebraic laws that ARE its convergence guarantee:
#         - commutativity:  merge(a, b) == merge(b, a)
#         - associativity:  merge(merge(a, b), c) == merge(a, merge(b, c))
#         - idempotence:    merge(a, a) == a
#
#       The file ships with TWO merge implementations:
#         CorrectORSet  — a correct OR-set; all three properties hold.
#         BuggyORSet    — a SUBTLY broken merge that passes most example tests but
#                         VIOLATES a law. Your job: run the properties, read the
#                         SHRUNK counterexample Hypothesis hands you, and explain
#                         the convergence failure it represents.
#
# Estimated time: 60 minutes. Runnable.
#
#   pip install pytest hypothesis
#   pytest exercise-02-property-tests-crdt-merge.py -q
#       -> CorrectORSet properties PASS
#       -> BuggyORSet  properties FAIL with a shrunk 'Falsifying example'
#
# WHY AN OR-SET, AND WHY THESE LAWS
#   A state-based CRDT's merge must be the least-upper-bound of a join-semilattice.
#   For replicas to converge regardless of message order, batching, and re-delivery,
#   the merge MUST be commutative, associative, and idempotent. Those three laws are
#   not "nice to have" — they are the definition of "this CRDT converges." A merge
#   that violates any of them produces replicas that disagree forever after a
#   partition heal: a split brain. Example tests can't catch this (you'd have to
#   GUESS the asymmetric interleaving); a property test SEARCHES for it.
#
#   This is the Week 3 / Week 20 OR-set, brought under property test. The real cart
#   in the capstone is Rust (proptest); the laws are identical, only the syntax moves.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Set, Tuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# -----------------------------------------------------------------------------
# The OR-set model
# -----------------------------------------------------------------------------
# An OR-set ("Observed-Remove set") tracks, per element, a set of unique ADD tags
# and a set of REMOVE tags (tombstones). An element is PRESENT iff it has at least
# one add tag that has NOT been tombstoned. A (element, tag) pair is unique per add,
# which is what lets concurrent add/remove of the same element resolve correctly:
# an add with a fresh tag "wins" over a remove that only tombstoned older tags.
#
# State:
#   adds:    set of (element, tag)  — every observed add
#   removes: set of (element, tag)  — every observed remove (tombstone of a specific add)
#
# elements() = { e : exists tag with (e,tag) in adds and (e,tag) not in removes }

Tagged = Tuple[str, int]  # (element, tag)


@dataclass(frozen=True)
class CorrectORSet:
    adds: FrozenSet[Tagged] = field(default_factory=frozenset)
    removes: FrozenSet[Tagged] = field(default_factory=frozenset)

    def elements(self) -> Set[str]:
        live = self.adds - self.removes
        return {e for (e, _tag) in live}

    def merge(self, other: "CorrectORSet") -> "CorrectORSet":
        # CORRECT: union the adds, union the removes. Both components are sets under
        # union, which is commutative, associative, and idempotent — so the product
        # (the OR-set) inherits all three laws. This is the textbook join.
        return CorrectORSet(
            adds=self.adds | other.adds,
            removes=self.removes | other.removes,
        )


@dataclass(frozen=True)
class BuggyORSet:
    adds: FrozenSet[Tagged] = field(default_factory=frozenset)
    removes: FrozenSet[Tagged] = field(default_factory=frozenset)

    def elements(self) -> Set[str]:
        live = self.adds - self.removes
        return {e for (e, _tag) in live}

    def merge(self, other: "BuggyORSet") -> "BuggyORSet":
        # THE PLANTED BUG: instead of unioning the removes, this keeps only the
        # removes that are present in *self* — it treats "self" as authoritative for
        # tombstones. This LOOKS reasonable ("my removes are the real ones") and it
        # passes naive example tests, but it is NOT commutative: merging in the other
        # order keeps the OTHER replica's removes, which can differ. A remove observed
        # on one replica but not the other survives in one merge order and is lost in
        # the reverse order -> the two replicas DO NOT converge.
        return BuggyORSet(
            adds=self.adds | other.adds,
            removes=self.removes,  # <-- BUG: should be `self.removes | other.removes`
        )


# -----------------------------------------------------------------------------
# Hypothesis strategies: generate random OR-sets
# -----------------------------------------------------------------------------
# Elements are short strings; tags are small ints. Keeping the alphabets tiny makes
# COLLISIONS likely (the same (element, tag) showing up as both an add and a remove
# across two sets), which is exactly the interesting case the laws hinge on. Small
# alphabets also make the shrunk counterexample tiny and readable.

elements_alphabet = st.sampled_from(["x", "y", "z"])
tags_alphabet = st.integers(min_value=0, max_value=2)
tagged = st.tuples(elements_alphabet, tags_alphabet)
tagged_sets = st.frozensets(tagged, max_size=4)


def orset_strategy(cls):
    """Build a random OR-set of type `cls` from a random add-set and remove-set."""
    return st.builds(
        lambda adds, removes: cls(adds=adds, removes=removes),
        tagged_sets,
        tagged_sets,
    )


correct_orsets = orset_strategy(CorrectORSet)
buggy_orsets = orset_strategy(BuggyORSet)


# -----------------------------------------------------------------------------
# The three laws, as properties — run against the CORRECT implementation.
# These PASS.
# -----------------------------------------------------------------------------
@settings(max_examples=300)
@given(correct_orsets, correct_orsets)
def test_correct_merge_is_commutative(a, b):
    assert a.merge(b).elements() == b.merge(a).elements()


@settings(max_examples=300)
@given(correct_orsets, correct_orsets, correct_orsets)
def test_correct_merge_is_associative(a, b, c):
    left = a.merge(b).merge(c)
    right = a.merge(b.merge(c))
    assert left.elements() == right.elements()


@settings(max_examples=300)
@given(correct_orsets)
def test_correct_merge_is_idempotent(a):
    assert a.merge(a).elements() == a.elements()


# -----------------------------------------------------------------------------
# The same three laws against the BUGGY implementation.
# Commutativity FAILS — Hypothesis will hand you the shrunk counterexample.
#
# These tests ASSERT THE BUG EXISTS (via pytest.raises around the law) so the file
# runs green as a teaching harness: the point is to SEE the falsifying example, not
# to leave a perpetually-red suite. Run with -s and read the printed counterexample,
# OR delete the `expect_law_violation` wrapper to watch the raw Hypothesis failure.
# -----------------------------------------------------------------------------
def _commutativity_holds_for_buggy(a, b) -> bool:
    return a.merge(b).elements() == b.merge(a).elements()


def test_buggy_merge_is_NOT_commutative_property_finds_it():
    """Drive Hypothesis directly and assert it FINDS a commutativity violation.

    We invert the usual pattern: instead of asserting the law holds, we assert that
    the law is violated for *some* generated input — i.e., that the property test
    would fail on the buggy merge. This both documents the bug and keeps the file
    green. In your own work you would NOT wrap it like this; you'd let it fail loudly.
    """
    from hypothesis import find

    # find() returns the smallest input satisfying the predicate, or raises if none.
    # Predicate: "this pair of OR-sets BREAKS commutativity."
    counterexample = find(
        st.tuples(buggy_orsets, buggy_orsets),
        lambda ab: not _commutativity_holds_for_buggy(ab[0], ab[1]),
    )
    a, b = counterexample
    # Demonstrate the asymmetry explicitly:
    assert a.merge(b).elements() != b.merge(a).elements()
    print("\nSHRUNK COMMUTATIVITY COUNTEREXAMPLE (buggy merge):")
    print(f"  a = adds={set(a.adds)} removes={set(a.removes)}")
    print(f"  b = adds={set(b.adds)} removes={set(b.removes)}")
    print(f"  merge(a,b).elements() = {a.merge(b).elements()}")
    print(f"  merge(b,a).elements() = {b.merge(a).elements()}")
    print("  -> the two merge orders DISAGREE: replicas do not converge.")


# -----------------------------------------------------------------------------
# Idempotence actually still HOLDS for the buggy merge (merging a with itself keeps
# a's own removes, which is correct for the self case). This is the trap that makes
# the bug survive naive testing: TWO of the three laws still pass. Only commutativity
# (and associativity) catch it — which is exactly why you test ALL THREE.
# -----------------------------------------------------------------------------
@settings(max_examples=200)
@given(buggy_orsets)
def test_buggy_merge_is_still_idempotent(a):
    # This passes even on the buggy merge — a.merge(a) keeps a.removes, == a.removes.
    assert a.merge(a).elements() == a.elements()


if __name__ == "__main__":
    # Allow running directly for the printed counterexample without pytest's capture.
    test_buggy_merge_is_NOT_commutative_property_finds_it()
    print("\nRun the full suite with:  pytest", __file__, "-q -s")


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   $ pytest exercise-02-property-tests-crdt-merge.py -q -s
#   ...
#   SHRUNK COMMUTATIVITY COUNTEREXAMPLE (buggy merge):
#     a = adds=set()                     removes=set()
#     b = adds={('x', 0)}                removes={('x', 0)}
#     merge(a,b).elements() = {'x'}      # a authoritative -> a has no removes -> x present
#     merge(b,a).elements() = set()      # b authoritative -> keeps b's tombstone -> x gone
#     -> the two merge orders DISAGREE: replicas do not converge.
#   .....
#   5 passed
#
#   (The exact minimal pair Hypothesis/find() reports may vary between runs — it is
#    always ONE element with an add/remove asymmetry across the two sets. What is
#    invariant is that merge(a,b) and merge(b,a) disagree on whether 'x' is present.)
#
#   (If you DELETE the find()/pytest.raises wrapper and instead write the buggy law
#    as a plain @given assertion, you see the raw Hypothesis failure:)
#
#   Falsifying example: test_buggy_merge_is_commutative(
#       a=BuggyORSet(adds=frozenset(), removes=frozenset({('x', 0)})),
#       b=BuggyORSet(adds=frozenset({('x', 0)}), removes=frozenset()),
#   )
#
# THE LESSON: The buggy merge treats `self`'s removes as authoritative, so the result
# depends on merge ORDER — which a CRDT must never do. In a two-region active-active
# cart, region A removed item x (tombstone ('x',0)) and region B re-added the same
# tagged item; depending on which region's anti-entropy merge ran "first", x is either
# present or gone, PERMANENTLY, on each side. That's the split-brain Week 20 warned
# about, found here on your laptop in seconds by a property test — never by an example
# test, because you would have had to GUESS this exact one-add-one-remove interleaving.
#
# Two of the three laws (idempotence here) still PASS on the buggy merge. That is the
# whole reason you test all three: any single law can survive a bug the others catch.
#
# ACCEPTANCE CRITERIA
#   [ ] The CorrectORSet commutativity/associativity/idempotence properties PASS.
#   [ ] The buggy merge's commutativity violation is found and its shrunk
#       counterexample printed (one add, one remove — the minimal case).
#   [ ] You can explain, in two sentences, the convergence failure the counterexample
#       represents (order-dependent removes -> replicas diverge after a heal).
#   [ ] You note that idempotence STILL passes on the buggy merge, and why that means
#       you must test all three laws, not just one.
#   [ ] Stretch: translate the three properties into Rust `proptest` against your real
#       cart's OR-set merge and confirm the real merge is commutative/assoc/idempotent.
# -----------------------------------------------------------------------------
