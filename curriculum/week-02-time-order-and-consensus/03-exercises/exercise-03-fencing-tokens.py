#!/usr/bin/env python3
# Exercise 3 — Fencing tokens (reproduce, then fix, the distributed-locking bug)
#
# Goal: Reproduce the famous lease-without-fencing data-corruption bug -- a client
#       that holds a lease, gets GC-paused past its expiry, and then writes to
#       storage while a NEW lease holder is also writing -- and then FIX it with a
#       monotonic fencing token that the storage layer checks.
#
# This is Lecture 2 Part 3 made executable. The lock service does nothing wrong;
# the bug is that a lease alone cannot stop a paused-then-resumed client. The fix
# is enforced at STORAGE, not at the client, via a monotonic token.
#
# HOW TO RUN
#
#   python3 exercise-03-fencing-tokens.py
#
# It runs TWO scenarios on a simulated timeline (no real sleeping):
#   Scenario A (UNSAFE): storage accepts any write. The paused old holder corrupts
#                        the data written by the new holder. Demonstrates the bug.
#   Scenario B (SAFE):   storage rejects writes carrying a stale fencing token. The
#                        paused old holder's write is FENCED OFF. Bug fixed.
#
# ACCEPTANCE CRITERIA
#
#   [ ] Scenario A shows the old (paused) holder OVERWRITING the new holder's value
#       -> data corruption. Prints "BUG REPRODUCED".
#   [ ] Scenario B shows the old holder's stale-token write REJECTED by storage,
#       so the new holder's value survives -> "BUG FIXED".
#   [ ] You can name the policy storage enforces (reject token < highest_seen) and
#       why it closes the slow-vs-dead gap from Week 1.
#   [ ] Self-check prints "ALL CHECKS PASS".
#
# Expected output (shape) is at the bottom of this file.

from __future__ import annotations


# ---------------------------------------------------------------------------
# A lock service that issues leases + monotonic fencing tokens
# ---------------------------------------------------------------------------

class LockService:
    """Raft-backed lock service (simulated). Each grant returns a fencing token
    that strictly increases, exactly like etcd revisions or ZooKeeper zxids."""

    def __init__(self) -> None:
        self._token = 0
        self._holder: str | None = None

    def acquire(self, client: str) -> int:
        """Grant the lease to `client`, returning a fresh monotonic fencing token.
        (We assume the previous lease already expired -- the service's job.)"""
        self._token += 1
        self._holder = client
        return self._token


# ---------------------------------------------------------------------------
# Two storage backends: one unsafe, one fenced
# ---------------------------------------------------------------------------

class UnsafeStorage:
    """Accepts any write. This is the bug: it trusts the client's belief that it
    holds the lock, with no way to reject a stale holder."""

    def __init__(self) -> None:
        self.data: str | None = None
        self.writes: list[tuple[str, int]] = []

    def write(self, value: str, token: int) -> bool:
        self.data = value
        self.writes.append((value, token))
        return True  # always accepted -- no fencing


class FencedStorage:
    """Rejects any write carrying a token lower than the highest already seen.
    This is the FIX: the truth is enforced at storage by a monotonic number, not
    by the client's (possibly stale) belief about who holds the lock."""

    def __init__(self) -> None:
        self.data: str | None = None
        self.highest_token = 0
        self.writes: list[tuple[str, int, bool]] = []

    def write(self, value: str, token: int) -> bool:
        if token < self.highest_token:
            self.writes.append((value, token, False))  # rejected
            return False
        self.highest_token = token
        self.data = value
        self.writes.append((value, token, True))       # accepted
        return True


# ---------------------------------------------------------------------------
# The scenario: client1 acquires, gets GC-paused past expiry; client2 acquires
# and writes; then client1 WAKES and tries to write with its stale token.
# ---------------------------------------------------------------------------

def run_unsafe() -> bool:
    print("============== SCENARIO A: UNSAFE (lease only) ==============")
    lock = LockService()
    storage = UnsafeStorage()

    # t=0: client1 acquires. Gets token 1.
    t1 = lock.acquire("client1")
    print(f"  t=0  client1 ACQUIRES lease, fencing token = {t1}")
    print(f"  t=2  client1 GC-PAUSES (frozen, but not dead) ...")

    # t=10: client1's lease expires; client2 acquires. Gets token 2.
    t2 = lock.acquire("client2")
    print(f"  t=10 client1's lease EXPIRED; client2 ACQUIRES, fencing token = {t2}")

    # t=11: client2 writes its value.
    storage.write("client2-data", t2)
    print(f"  t=11 client2 WRITES 'client2-data' (token {t2}) -> accepted")
    print(f"       storage now holds: {storage.data!r}")

    # t=14: client1 WAKES, still believes it holds the lock, writes with token 1.
    accepted = storage.write("client1-data-STALE", t1)
    print(f"  t=14 client1 WAKES and WRITES 'client1-data-STALE' (token {t1})"
          f" -> {'accepted' if accepted else 'REJECTED'}")
    print(f"       storage now holds: {storage.data!r}")

    corrupted = storage.data == "client1-data-STALE"
    if corrupted:
        print("  RESULT: client2's data was OVERWRITTEN by a stale holder. CORRUPTION.")
        print("  BUG REPRODUCED: a lease alone cannot stop a paused-then-resumed client.\n")
    else:
        print("  (unexpected: no corruption in the unsafe scenario)\n")
    return corrupted


def run_safe() -> bool:
    print("============== SCENARIO B: SAFE (lease + fencing token) ==============")
    lock = LockService()
    storage = FencedStorage()

    t1 = lock.acquire("client1")
    print(f"  t=0  client1 ACQUIRES lease, fencing token = {t1}")
    print(f"  t=2  client1 GC-PAUSES (frozen, but not dead) ...")

    t2 = lock.acquire("client2")
    print(f"  t=10 client1's lease EXPIRED; client2 ACQUIRES, fencing token = {t2}")

    storage.write("client2-data", t2)
    print(f"  t=11 client2 WRITES 'client2-data' (token {t2}) -> accepted")
    print(f"       storage highest_token = {storage.highest_token}, data = {storage.data!r}")

    accepted = storage.write("client1-data-STALE", t1)
    print(f"  t=14 client1 WAKES and WRITES 'client1-data-STALE' (token {t1})"
          f" -> {'accepted' if accepted else 'REJECTED (token < highest)'}")
    print(f"       storage still holds: {storage.data!r}")

    survived = storage.data == "client2-data" and not accepted
    if survived:
        print("  RESULT: the stale write was FENCED OFF; client2's data survives.")
        print("  BUG FIXED: storage rejects token 1 because it already saw token 2.\n")
    else:
        print("  (unexpected: the fence did not hold)\n")
    return survived


def main() -> None:
    bug_reproduced = run_unsafe()
    bug_fixed = run_safe()

    print("================= THE LESSON =================")
    print("  The lock service was correct in BOTH scenarios -- the lease genuinely")
    print("  expired and was reassigned. The difference is entirely at STORAGE:")
    print("    - UnsafeStorage trusts the client's belief -> a paused client corrupts data.")
    print("    - FencedStorage enforces a monotonic token -> the stale client is rejected.")
    print("  This closes the slow-vs-dead gap from Week 1: storage doesn't need to know")
    print("  WHY a token is stale (crash? pause?), only that a higher one exists.")
    print()

    print("================= SUMMARY =================")
    if bug_reproduced and bug_fixed:
        print("ALL CHECKS PASS")
    else:
        print(f"SOME CHECKS FAILED (bug_reproduced={bug_reproduced}, bug_fixed={bug_fixed})")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Expected output (shape)
# ---------------------------------------------------------------------------
#
# ============== SCENARIO A: UNSAFE (lease only) ==============
#   t=0  client1 ACQUIRES lease, fencing token = 1
#   t=2  client1 GC-PAUSES ...
#   t=10 client1's lease EXPIRED; client2 ACQUIRES, fencing token = 2
#   t=11 client2 WRITES 'client2-data' (token 2) -> accepted
#   t=14 client1 WAKES and WRITES 'client1-data-STALE' (token 1) -> accepted
#        storage now holds: 'client1-data-STALE'
#   RESULT: client2's data was OVERWRITTEN by a stale holder. CORRUPTION.
#   BUG REPRODUCED ...
#
# ============== SCENARIO B: SAFE (lease + fencing token) ==============
#   ... t=14 client1 WAKES and WRITES (token 1) -> REJECTED (token < highest)
#   RESULT: the stale write was FENCED OFF; client2's data survives.
#   BUG FIXED ...
#
# ================= SUMMARY =================
# ALL CHECKS PASS
#
# The token IS a logical clock (Lecture 1) applied to lock ownership. It is the same
# primitive as Raft's term and Paxos's ballot: a monotonic number that lets the
# system reject a stale actor without needing to distinguish "slow" from "dead".
