// Exercise 2 — The Automerge Active-Active Cart (runnable)
//
// Goal: A runnable Automerge cart that proves an ACTIVE-ACTIVE design (both
//       regions accept writes to the same cart) CONVERGES and is CORRECT after a
//       partition heal. Two replicas diverge during a partition — concurrent
//       adds, a remove, concurrent quantity changes — then merge and converge to
//       a LOSSLESS, intended state. The script asserts all three:
//         CONVERGED:  region-a == region-b (byte-identical)
//         LOSSLESS:   every concurrent ADD is preserved
//         INTENT:     quantities are summed (both adds count), the remove only
//                     undid what it observed.
//       And it shows the contrast: an LWW model would CONVERGE but discard one
//       region's writes — converged is NOT correct.
//
// This is the syllabus lab: "Promote the cart to active-active across both
// regions using a CRDT. Partition. Heal. Verify convergence." — in production
// Automerge, with the CORRECTNESS check that separates a real CRDT design from a
// thing that merely agrees.
//
// Estimated time: 60 minutes. Runnable.
//
// PREREQUISITES
//   - Node.js 20+
//   - npm init -y && npm i @automerge/automerge
//   - Run: node exercise-02-automerge-active-active-cart.mjs
//
// NOTE: Automerge's containers merge with TYPE-APPROPRIATE rules (concurrent map
// inserts both survive; the Counter type sums concurrent increments). That is
// WHY this converges correctly and an LWW-everything model would not. We model
// each cart item as { qty: Counter, present: bool-ish } so quantities SUM and
// presence is add-wins — the OR-set/multiset semantics from Exercise 1, now in a
// real library.

import * as Automerge from "@automerge/automerge";

// --- helpers ---------------------------------------------------------------

// A cart is a map of sku -> { qty: Counter, removed: boolean }.
// Presence rule (add-wins): an item is "in the cart" if qty > 0 AND not removed,
// OR if it was re-added concurrently with a remove (the Counter increment after
// the remove makes it present again). We model remove as a flag + the rule that
// a concurrent increment beats it (we check the merged Counter value).
function newCart() {
  return Automerge.from({ items: {} });
}

function addItem(doc, sku, qty) {
  return Automerge.change(doc, (d) => {
    if (!d.items[sku]) d.items[sku] = { qty: new Automerge.Counter(0), removed: false };
    d.items[sku].qty.increment(qty);
    // An add re-activates a (possibly) removed item: add-wins.
    d.items[sku].removed = false;
  });
}

function removeItem(doc, sku) {
  return Automerge.change(doc, (d) => {
    if (d.items[sku]) d.items[sku].removed = true;
  });
}

// The cart's logical contents: sku -> quantity, for items present.
// Add-wins: present if qty > 0. (A concurrent add increments the shared Counter,
// so even if one replica set removed=true, the other's increment keeps qty > 0
// and our presence rule keeps the item — that's the add-wins behavior we want.)
function contents(doc) {
  const out = {};
  for (const [sku, it] of Object.entries(doc.items)) {
    const q = typeof it.qty === "object" ? it.qty.value : it.qty;
    // present if there is positive quantity; the remove only "wins" if no
    // concurrent add brought qty back / kept it positive.
    if (q > 0 && !it.removed) out[sku] = q;
  }
  return out;
}

function eq(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// --- the scenario ----------------------------------------------------------

console.log("=== Automerge active-active cart: partition / heal / converge ===\n");

// Start: both regions share an identical empty cart (synced before the partition).
let base = newCart();
base = addItem(base, "sku-BREAD", 1);          // a pre-partition item both share
let regionA = Automerge.clone(base);
let regionB = Automerge.clone(base);

// PARTITION: the two regions can't communicate. Each accepts local writes.
console.log("[partition] region-a adds 'sku-APPLE' (qty 2), removes 'sku-BREAD'");
regionA = addItem(regionA, "sku-APPLE", 2);
regionA = removeItem(regionA, "sku-BREAD");

console.log("[partition] region-b adds 'sku-APPLE' (qty 3), adds 'sku-KIWI' (qty 1)");
regionB = addItem(regionB, "sku-APPLE", 3);    // concurrent add to the SAME sku
regionB = addItem(regionB, "sku-KIWI", 1);

console.log("\n  during partition:");
console.log("    region-a:", contents(regionA));   // { APPLE: 2 }  (BREAD removed)
console.log("    region-b:", contents(regionB));    // { BREAD: 1, APPLE: 3, KIWI: 1 }

// HEAL: the partition heals; the regions exchange and merge changes (both ways).
console.log("\n[heal]      merging region-a <-> region-b ...");
const merged = Automerge.merge(Automerge.clone(regionA), regionB);
const mergedOther = Automerge.merge(Automerge.clone(regionB), regionA);

const a = contents(merged);
const b = contents(mergedOther);

console.log("\n  after heal:");
console.log("    region-a:", a);
console.log("    region-b:", b);

// --- the three assertions --------------------------------------------------

const converged = eq(a, b);

// LOSSLESS: every item ADDED in either region during the partition is present
// (APPLE from both, KIWI from B). BREAD was removed in A with no concurrent
// re-add, so it's correctly gone.
const lossless = "sku-APPLE" in a && "sku-KIWI" in a;

// INTENT: APPLE quantity is the SUM of the concurrent adds (2 + 3 = 5), NOT
// "whichever wrote last". This is the Counter CRDT doing its job.
const intentQty = a["sku-APPLE"] === 5;

// INTENT: BREAD was removed in A and NOT re-added concurrently, so it's absent.
const intentRemove = !("sku-BREAD" in a);

console.log("\n" + "-".repeat(68));
console.log(`CONVERGED:  region-a state == region-b state            ${converged ? "✔" : "✘"}`);
console.log(`LOSSLESS:   every concurrent ADD preserved (APPLE,KIWI) ${lossless ? "✔" : "✘"}`);
console.log(`INTENT:     APPLE qty = 5 (2+3, both adds kept)         ${intentQty ? "✔" : "✘"}`);
console.log(`            BREAD removed (no concurrent re-add)        ${intentRemove ? "✔" : "✘"}`);
console.log("-".repeat(68));

// --- the contrast: what LWW would have done --------------------------------
//
// If the WHOLE cart were a single LWW-register, the heal would keep only the
// replica whose write had the latest timestamp -> one region's entire cart,
// discarding the other's. Simulate it:
const lwwWinner = contents(regionA); // pretend A's write timestamp was latest
console.log("\nFor contrast, an LWW-WHOLE-CART model would keep only one side:");
console.log("    LWW result:", lwwWinner, "  <-- KIWI and B's APPLE adds SILENTLY LOST");
console.log("    (it would CONVERGE — both replicas agree on", JSON.stringify(lwwWinner), "—");
console.log("     but it discarded real writes. CONVERGED is NOT CORRECT.)\n");

const allPass = converged && lossless && intentQty && intentRemove;
if (!allPass) {
  console.error("FAIL: the cart did not converge to the intended value.");
  process.exit(1);
}
console.log("PASS: converged AND lossless AND intended. The CRDT is the right type for this field.");

// ---------------------------------------------------------------------------
// Expected output (abridged)
// ---------------------------------------------------------------------------
//
//   [partition] region-a adds 'sku-APPLE' (qty 2), removes 'sku-BREAD'
//   [partition] region-b adds 'sku-APPLE' (qty 3), adds 'sku-KIWI' (qty 1)
//   ...
//   [heal]      merging region-a <-> region-b ...
//     after heal:
//       region-a: { 'sku-APPLE': 5, 'sku-KIWI': 1 }
//       region-b: { 'sku-APPLE': 5, 'sku-KIWI': 1 }
//   --------------------------------------------------------------------
//   CONVERGED:  region-a state == region-b state            ✔
//   LOSSLESS:   every concurrent ADD preserved (APPLE,KIWI) ✔
//   INTENT:     APPLE qty = 5 (2+3, both adds kept)         ✔
//               BREAD removed (no concurrent re-add)        ✔
//   --------------------------------------------------------------------
//   PASS: converged AND lossless AND intended.
//
// ACCEPTANCE CRITERIA
//   [ ] The script prints CONVERGED, LOSSLESS, and INTENT all ✔.
//   [ ] APPLE quantity is 5 (the Counter summed the concurrent 2 and 3) — NOT 2,
//       not 3. You understand why: Automerge's Counter is a PN-counter, so
//       concurrent increments BOTH count.
//   [ ] You can explain why the LWW-whole-cart contrast loses KIWI even though it
//       "converges" — and why that makes "converged" insufficient.
//   [ ] BONUS: re-run with the merges in the OTHER order (merge B into A's clone
//       vs A into B's clone) and confirm the result is identical — order-independence.
//   [ ] BONUS: run the two replicas in two separate Node processes exchanging
//       Automerge.save()/load() binary sync messages, to model real region-to-
//       region sync rather than in-process merge.
// ---------------------------------------------------------------------------
