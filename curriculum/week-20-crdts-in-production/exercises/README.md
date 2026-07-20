# Week 20 — Exercises

Three focused drills that take CRDTs from theory to a converging, *correct* active-active cart. Each takes 45–90 minutes. Do them in order — exercise 1 models the cart as an OR-set and proves convergence by hand, exercise 2 runs a real Automerge active-active cart through a partition-and-heal, and exercise 3 builds the application-layer conflict resolution for the fields a CRDT can't auto-merge. The recurring theme: not "did it converge" (it will) but "did it converge to the value the user intended."

## Index

1. **[Exercise 1 — The OR-set cart: partition, heal, converge](exercise-01-or-set-cart-partition-heal.md)** — model the cart's items as an OR-set, partition two replicas, write to both, heal, and prove convergence *with every concurrent add preserved* — then show what LWW would have lost. (~75 min, guided)
2. **[Exercise 2 — The Automerge active-active cart](exercise-02-automerge-active-active-cart.mjs)** — a runnable Automerge cart: two replicas diverge during a partition (concurrent adds, removes, quantity changes), merge, and converge to a *correct, lossless* state — with the convergence AND correctness both asserted. (~60 min, runnable)
3. **[Exercise 3 — Vector-clock conflict resolution](exercise-03-vector-clock-conflict-resolution.py)** — detect concurrent writes with vector clocks, produce siblings, and resolve them with application-layer business logic — the case where automatic merge is the wrong policy. (~60 min, runnable)

## How to work the exercises

- Have **Node.js 20+** (`node --version`) for exercise 2 (`npm i @automerge/automerge`) and **Python 3.10+** for exercise 3 (no external deps — pure vector clocks).
- Have the **Week 3 CRDT theory** fresh: OR-set add-wins/observed-remove, PN-counter, LWW-register, the convergence guarantee. We build on it.
- Have the **Week 2 vector-clock** literacy: you can tell concurrent from causally-ordered. Exercise 3 lives on this.
- **Check correctness, not just convergence, after every merge.** Convergence (the two replicas are equal) is necessary but not sufficient — the exercises make you *also* assert losslessness (every concurrent add survived) and intent (the quantity is the sum, the remove only undid what it saw). The OR-set/Automerge equality is the easy half; the correctness assertion is the half that matters.
- When a merge "loses" data, don't assume the CRDT is broken — assume you picked the *wrong type for the field* (an LWW where you needed an OR-set). That diagnosis is the whole week.
- Each runnable exercise ends with an **expected output** block. If it says CONVERGED but not LOSSLESS, you've reproduced the footgun, not the fix.

## Running the exercises

The `.mjs` exercise is a Node ES module:

```bash
npm init -y && npm i @automerge/automerge
node exercise-02-automerge-active-active-cart.mjs
```

The `.py` exercise is standard-library Python:

```bash
python3 exercise-03-vector-clock-conflict-resolution.py
```

The header of each file lists the exact prerequisites. The OR-set exercise (1) is guided modeling you can do by hand or in a few lines of any language; the file points you at the minimal structure.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-20` to compare.
