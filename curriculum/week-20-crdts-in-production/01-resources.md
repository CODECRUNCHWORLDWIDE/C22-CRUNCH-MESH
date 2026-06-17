# Week 20 — Resources

Every resource here is **free** and **open**. Automerge and Yjs are open-source libraries with openly published docs; the CRDT papers are freely available preprints; Redis is open-source (and the Active-Active/CRDB semantics are documented openly even where the geo-distributed product is commercial — we use the *concepts* and run the open data types locally). No paywalled books are linked, though *Designing Data-Intensive Applications* (Ch. 5) is the canonical secondary reading and worth owning.

This week targets **Automerge 2.x** (the Rust-core, WASM-backed rewrite — the line you should use in 2026), **Yjs 13+**, and **Redis 7+** for the local data-type modeling. The convergence *concepts* are stable; only library APIs move, so pin to your installed versions.

## Required reading (work it into your week)

- **Shapiro, Preguiça, Baquero, Zawirski — "Conflict-free Replicated Data Types" (2011)** — the foundational paper: state-based vs op-based, the join-semilattice, the convergence proof. Re-read it now that you're deploying, not just defining:
  <https://inria.hal.science/inria-00609399/document>
- **Automerge — documentation** — the JSON-document CRDT you'll run; concepts, the change/merge model, and the actor identity:
  <https://automerge.org/docs/>
- **Yjs — documentation** — the high-performance shared-data CRDT behind many collaborative editors:
  <https://docs.yjs.dev/>
- **Redis — Active-Active geo-distributed (CRDT) databases** — how Redis models counters/sets/registers as CRDTs at the data tier, and the conflict-resolution rules:
  <https://redis.io/docs/latest/operate/rs/databases/active-active/>
- **Martin Kleppmann — "CRDTs: The Hard Parts"** (talk + writing) — the honest treatment of metadata cost, tombstones, and why local-first CRDTs are harder than the demos:
  <https://www.youtube.com/watch?v=x7drE24geUw>

## The CRDT types in depth (skim, then refer back)

- **The OR-set (observed-remove set)** — add-wins semantics, tombstones, and why it's the right type for a cart's items. The Shapiro paper §3.3.5 specifies it; Automerge's set/list types implement the idea.
- **PN-counter / G-counter** — increment-only and increment/decrement counters; the Shapiro paper §3 — and the caveat about a PN-counter going negative when you model removal as arithmetic.
- **LWW-register** — last-write-wins by timestamp: it converges, and it *discards* concurrent writes. Read it as the cautionary type, the footgun this week names repeatedly.
- **Automerge — "How it works"** — the op-based document model, the change history, and where the metadata lives:
  <https://automerge.org/docs/under-the-hood/>

## Conflict resolution and vector clocks

- **Amazon Dynamo paper (DeCandia et al., 2007), §4.4 (Data Versioning)** — vector clocks producing *siblings* and the application-layer (or client-side) reconciliation model — the alternative to automatic CRDT merge:
  <https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf>
- **Riak — conflict resolution / siblings** — the production system that exposes Dynamo's sibling model; read it for *how* an app resolves concurrent values:
  <https://docs.riak.com/riak/kv/latest/developing/usage/conflict-resolution/index.html>
- **The Bayou system (Terry et al., 1995)** — the ancestor of application-defined conflict resolution; the merge-procedure idea CRDTs later formalized. Find the paper freely online.
- **Week 2 (this course) — vector clocks and happens-before** — the prerequisite mechanism for detecting concurrency; revisit your own notes.

## When NOT to use a CRDT

- **Designing Data-Intensive Applications (Kleppmann), Ch. 5 (Replication) & Ch. 7 (Transactions)** — the strong-consistency tools (single-leader, transactions, linearizability) that are the *correct* answer when data cannot tolerate divergence. The contrast that makes "when a CRDT is wrong" concrete.
- **Jepsen analyses** — Kyle Kingsbury's reports on real systems' consistency claims; read one to internalize how subtle "it converged" can be while still being wrong:
  <https://jepsen.io/analyses>

## Production experience reports (free, no signup)

- **"CRDTs in production"–style talks** — search the CNCF / Strange Loop / local-first archives for production CRDT war stories (Figma's multiplayer, Linear's sync engine, Riak at Bet365 — the Week 3 case study, revisited at scale).
- **Local-first software (Kleppmann, Wiggins, van Hardenberg, McGranaghan)** — the essay that frames *why* CRDTs matter for a class of apps:
  <https://www.inkandswitch.com/local-first/>

## Tools you'll use this week

- **Node.js + `@automerge/automerge`** — the runnable active-active cart (Exercise 2). `npm i @automerge/automerge`.
- **Yjs (`yjs`)** — for the stretch / structured-data modeling.
- **Python + `redis`** — the OR-set / counter modeling against a local Redis (Exercise 3 uses pure-Python vector clocks; the Redis CRDB semantics are explained for where you'd run them).
- **Redis 7+** — run locally for the data-type modeling; the Active-Active geo-distributed semantics are documented for the multi-region case.
- **The two Kind regions from Week 19** — the stretch and mini-project run the CRDT cart across genuinely separated replicas with a real network partition.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **CRDT** | Conflict-free Replicated Data Type: a data type whose replicas always converge to the same state under concurrent updates, with no coordination. |
| **Strong eventual consistency (SEC)** | Replicas that have delivered the same set of updates are in the same state — regardless of the order they arrived in. |
| **Convergence** | All replicas reach the same state. NOTE: convergence is *agreement*, not *correctness* — it says nothing about whether the agreed value is the one users wanted. |
| **State-based (CvRDT)** | Replicas exchange full state and merge via a join (least-upper-bound); merge is commutative, associative, idempotent. |
| **Op-based (CmRDT)** | Replicas exchange *operations*; ops must commute (and need causal delivery). Automerge is op-based. |
| **LWW-register** | Last-write-wins by timestamp. Converges, but *discards* the losing concurrent write — the footgun. |
| **OR-set** | Observed-remove set: add-wins; a remove only removes adds it has *observed*, so a concurrent add survives. The right type for a cart's items. |
| **PN-counter** | A counter supporting increment and decrement (two G-counters). Right for a two-way quantity; can go negative if you model removal as arithmetic. |
| **Tombstone** | A marker for a removed element that the OR-set must remember (to prevent the element "resurrecting"); a major source of metadata cost. |
| **Causal delivery** | Delivering operations in an order consistent with happens-before; required for op-based CRDT correctness. |
| **Causal stability** | The point at which all replicas have seen an operation, so its metadata (tombstones, history) can be safely garbage-collected. |
| **Sibling** | A concurrent, unresolved value (Dynamo/Riak model): when the system *can't* auto-merge, it surfaces multiple values for the app to reconcile. |
| **Vector clock** | Per-actor version vector used to detect whether two writes are concurrent (siblings) or causally ordered. |
| **Active-active** | Multiple regions accept writes to the same data simultaneously; a CRDT is one way to make that safe (convergent). |
| **Automerge** | An op-based JSON-document CRDT (Rust core, WASM) for rich, mergeable application state. |
| **Yjs** | A high-performance CRDT for shared text/structured data; the backbone of many collaborative editors. |
| **Redis Active-Active (CRDB)** | Geo-distributed Redis where counters/sets/registers are CRDTs at the data tier. |

---

*If a link 404s, please open an issue so we can replace it.*
