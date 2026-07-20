# Challenge 1 — The LWW That Ate the Cart

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. The cart service went active-active across two regions last sprint — both regions accept writes, a "CRDT" merges them on sync, and the launch was declared a success: convergence demos passed, the partition-heal test was green, no errors in production. This morning, support is escalating: **customers are reporting that items disappear from their carts.** They add a product on their phone (routed to region B), then open their laptop (routed to region A), and the phone's item is *gone* — no error, no warning, it simply isn't there.

Here's the twist that makes it a real incident: **the system says it's working perfectly.** There are no exceptions in the logs. The "did the replicas converge?" check is green — region A and region B are in *perfect agreement* about every cart. The CRDT convergence metric reads 100%. By every signal the team built, the system is healthy. And yet data is being lost.

Your job: prove the data loss is real and that the system "converged" anyway, name *why* (the cart's items are modeled as an **LWW-register over the whole cart**, so on a partition heal the cart with the later timestamp wins *entirely* and the other region's concurrent adds are discarded), and fix it by changing the **type** — to an OR-set / multiset whose merge is add-wins. "Sync more often," "add retries," and "always prefer region A" are *not* answers — they don't fix a wrong type, they just change which writes get eaten or how often.

This mirrors the most dangerous real CRDT incident there is. A CRDT that errors is visible. A CRDT that *converges to a value that lost data* is invisible to every health check, because convergence — the thing the team monitored — *did* succeed. The bug isn't in the convergence; it's in choosing a type whose correct-by-construction convergence lands on the wrong value.

## The harness

Reproduce it. Model the cart the buggy way (LWW over the whole cart) and run the partition-heal:

```python
# buggy_cart.py — the cart's items as a SINGLE last-write-wins value.
# The whole item-set is one register; the write with the latest timestamp wins.
class LWWCart:
    def __init__(self):
        self.items = {}          # sku -> qty
        self.ts = 0              # last-write timestamp of the WHOLE cart

    def write(self, items, ts):  # a client writes its ENTIRE cart state
        if ts >= self.ts:        # last-write-wins over the whole cart
            self.items = dict(items)
            self.ts = ts

    def merge(self, other):      # on heal: keep whichever WHOLE cart is newer
        if other.ts > self.ts:
            self.items, self.ts = dict(other.items), other.ts
        # (if equal/older, keep ours) -> THIS is where the other region's adds die
```

```python
# the scenario: a user shops from two devices during a partition
A, B = LWWCart(), LWWCart()
# pre-partition both have {BREAD:1} at ts=100 (synced)
A.write({"BREAD": 1}, 100); B.write({"BREAD": 1}, 100)

# PARTITION. Each region accepts the user's local writes:
B.write({"BREAD": 1, "PHONE_ITEM": 1}, 101)   # phone (region B) adds an item, ts=101
A.write({"BREAD": 1, "LAPTOP_ITEM": 1}, 102)  # laptop (region A) adds an item, ts=102

# HEAL: merge.
A.merge(B); B.merge(A)
print("region A:", A.items)   # {'BREAD': 1, 'LAPTOP_ITEM': 1}
print("region B:", B.items)   # {'BREAD': 1, 'LAPTOP_ITEM': 1}  -- CONVERGED
# ...and PHONE_ITEM is GONE. The user added it, got a confirmation, and it vanished.
```

Run it. The replicas converge (A == B, the green metric is honest) and `PHONE_ITEM` — a real item the customer added — is silently gone. That's the incident. Diagnose it from the outside before reading the fix.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Symptom** — exactly what you observe: the converged state on both replicas (equal — convergence "passed"), and the specific item that's missing (`PHONE_ITEM`) despite having been added and acknowledged. Show that the convergence check is *green* while data is lost.
2. **Proof the loss is real and convergence "succeeded"** — the specific evidence: both replicas are byte-identical (so any "are we converged?" monitor reads healthy), AND a write that was acknowledged (`PHONE_ITEM` added at ts=101 in B) is absent from the converged state. Convergence ✔, data loss ✔, simultaneously.
3. **The mechanism** — name it precisely: the cart's items are modeled as a **single LWW-register over the whole cart**, so the merge keeps the cart with the later *whole-cart* timestamp and *discards the entire other cart*, including its concurrent adds. LWW converges (it's a valid CRDT) but its merge rule — "newest whole-cart wins" — is wrong for a *set* of items where concurrent adds are all real.
4. **The fix** — change the **type**, not the plumbing. Model items as an **OR-set / multiset** (Exercise 1 / Exercise 2): each add is an independent, tagged element, so a concurrent add in region B survives a concurrent write in region A. Show the *same* scenario under the OR-set converging to `{BREAD, LAPTOP_ITEM, PHONE_ITEM}` — every add preserved.
5. **Why the non-fixes don't work** — state explicitly why "sync more often" (shrinks the partition window but still loses adds whenever there *is* a partition), "add retries" (the writes didn't fail — there's nothing to retry), and "always prefer region A" (just makes the loss deterministic — region B's adds *always* die) all fail to address the wrong-type root cause.

You must reach the diagnosis with **at least two** independent signals — e.g., the replicas being identical (convergence succeeded) *and* an acknowledged write being absent (data lost). One signal is a guess; two is a diagnosis.

## The fix, applied

Change the type. The OR-set / multiset cart (the right model):

```python
# fixed_cart.py — items as an OR-set: each add is a uniquely-tagged element.
class ORSetCart:
    def __init__(self):
        self.adds = {}            # sku -> set of unique add-tags
        self.tombs = set()        # tombstoned (removed) tags

    def add(self, sku, tag):      # tag globally unique, e.g. f"{region}:{seq}"
        self.adds.setdefault(sku, set()).add(tag)

    def remove(self, sku):        # observed-remove: tombstone tags we've SEEN
        self.tombs |= self.adds.get(sku, set())

    def merge(self, other):       # union adds, union tombstones -> add-wins
        for sku, tags in other.adds.items():
            self.adds.setdefault(sku, set()).update(tags)
        self.tombs |= other.tombs

    def items(self):              # present iff it has a live (non-tombstoned) tag
        return {sku for sku, tags in self.adds.items() if tags - self.tombs}
```

Re-run the scenario: B adds `PHONE_ITEM` (tag `B:1`), A adds `LAPTOP_ITEM` (tag `A:1`), heal merges the tag-sets, and the converged cart contains *both* — because each add is its own tagged element, not a value that overwrites the whole cart. No acknowledged add is ever lost.

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You show the buggy LWW cart **converging** (A == B) **and** silently dropping `PHONE_ITEM` — convergence green, data gone, both demonstrated.
- [ ] You name the mechanism precisely: LWW-register over the *whole cart* (a set modeled as a single overwrite-value) discards concurrent adds on merge.
- [ ] Your fix is a **type change** to an OR-set / multiset; you re-run the same scenario and show it converges to the lossless `{BREAD, LAPTOP_ITEM, PHONE_ITEM}`.
- [ ] You explain why "sync more often / retries / prefer region A" are non-fixes.
- [ ] A `fixed_cart.py` (or equivalent) checked in, demonstrating the lossless convergence.
- [ ] Committed to your Week 20 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong "fixes" you must NOT write:

- **"Sync the regions more frequently so the partition window is tiny."** This *reduces* the probability of concurrent writes but doesn't *eliminate* the bug — any time there's a real partition (the thing multi-region exists to survive), concurrent adds still get eaten. You've made the data loss rarer, not impossible, and you've papered over a correctness bug with a probability tweak. The whole point of a CRDT is to be *correct under partition*, not "correct as long as the partition is short."
- **"Make region A authoritative — always prefer A on conflict."** This makes the loss *deterministic* instead of timestamp-dependent: now region B's concurrent adds *always* lose. You've turned a flaky data-loss bug into a reliable one, which is arguably worse, and you've thrown away the entire reason for active-active (both regions accepting writes that count). Picking a winner region is not conflict *resolution*; it's conflict *deletion*.

A related real-world cousin worth naming in your writeup: the **silent quantity overwrite** — modeling an item's quantity as an LWW value so "set quantity to 2" in A and "set quantity to 3" in B converges to one of them (3 or 2), losing the other customer's intent, instead of a PN-counter that sums concurrent increments. Same disease (LWW where the field has real concurrent writes), same cure (the right CRDT type for the field's semantics).

## Stretch

- Add **quantity** correctly: extend the OR-set fix so concurrent "add 2 apples" and "add 3 apples" converge to 5 (a multiset / per-item counter), and show the LWW version would keep only 2 or 3. The quantity footgun and its fix.
- Build a **correctness monitor**, not just a convergence monitor: a check that asserts not only "the replicas agree" but "every acknowledged add is present in the converged state." Show it goes RED on the buggy LWW cart (catching the bug the convergence monitor missed) and GREEN on the OR-set fix. This is the "monitor correctness, not just convergence" lesson made into a tool.
- Run the fixed OR-set cart across the **two real Kind regions** from Week 19, with a genuine network partition, and demonstrate lossless convergence on truly separated replicas — the mini-project's active-active-across-regions goal.

## Why this matters

Every team that adopts CRDTs is one wrong type-choice away from this incident, and it's uniquely dangerous because *the monitoring the team naturally builds doesn't catch it.* You monitor "did it converge?" — and it did. You don't think to monitor "did it converge to the *right* value?" — and it didn't. The difference between a CRDT deployment that delights users (carts that survive partitions losslessly) and one that quietly loses their data is a single decision: modeling each field with the type whose convergence lands on the intended value. When you defend your `cart-crdt` mini-project at the Phase 4 review, "my cart converges *and* is lossless, here's the correctness check that proves it, and here's why every field's type is the right one" is the line that says you understand CRDTs — not just that they converge, but that converging isn't the same as being correct.
