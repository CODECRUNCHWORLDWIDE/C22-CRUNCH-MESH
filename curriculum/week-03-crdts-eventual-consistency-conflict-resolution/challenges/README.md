# Week 3 — Challenges

The exercises drill the CRDT mechanics. **The challenge makes you the engineer who finds the data-loss bug.** You reproduce last-writer-wins silently destroying a concurrent write — the exact failure CRDTs exist to prevent — then fix it with the right CRDT and prove, with a test, that no data is lost.

## Index

1. **[Challenge 1 — Catch LWW losing data, then fix it](challenge-01-lww-data-loss.md)** — build a tiny replicated store that uses last-writer-wins, drive it through a concurrent-write scenario, and demonstrate a write silently vanishing. Then replace the LWW field with the correct CRDT (OR-set or MV-register), re-run the scenario, and prove the concurrent write survives. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the **capstone's cart-CRDT convergence demo**, where you partition two regions, heal, and prove the cart converged with all items intact. Reproducing the LWW bug first — *feeling* the data loss — is what makes you never reach for LWW carelessly again. The skill — recognizing "this field uses last-writer-wins and these writes are concurrent, so we are losing data" in a code review — is what separates an engineer who "knows CRDTs" from one who catches the latent data-loss bug before it ships.
