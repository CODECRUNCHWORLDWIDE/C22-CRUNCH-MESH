# Week 3 — Resources

Every resource here is **freely available**. The Shapiro et al. CRDT papers are open via INRIA/author pages. The Bayou paper is a classic, widely mirrored. The Riak, Redis, and AntidoteDB docs are public. The Automerge/Yjs projects are open source. No paywalled material is linked.

The two readings you must actually do this week are the **Shapiro et al. CRDT paper** (for the definitions and the convergence argument) and **Kleppmann's DDIA §5** (for the replication context).

## Required reading (work it into your week)

- **Shapiro, Preguiça, Baquero & Zawirski, "Conflict-free Replicated Data Types"** (2011) — the paper that named and formalized CRDTs. Read the SEC definition and the OR-set; skim the proofs:
  <https://inria.hal.science/inria-00609399/document>
- **Shapiro et al., "A comprehensive study of Convergent and Commutative Replicated Data Types"** (INRIA tech report, 2011) — the long version, the catalog of every CRDT and its correctness argument. A reference, not a cover-to-cover read:
  <https://inria.hal.science/inria-00555588/document>
- **Kleppmann, *Designing Data-Intensive Applications*, Chapter 5 ("Replication")** — the multi-leader and leaderless replication context, last-writer-wins, and why concurrent writes need merging. Read the "Detecting Concurrent Writes" section closely.
- **Terry et al., "Managing Update Conflicts in Bayou"** (SOSP 1995) — the ancestor of all eventual-consistency-with-reconciliation systems; where session guarantees and application-level merge came from:
  <https://people.cs.umd.edu/~keleher/ ... >  (search "Bayou managing update conflicts" — widely mirrored)

## CRDTs in depth

- **Baquero & Preguiça, "Why Logical Clocks are Easy"** (ACM Queue, 2016) — the version-vector and dot machinery that CRDTs use, explained well:
  <https://queue.acm.org/detail.cfm?id=2917756>
- **"Delta State Replicated Data Types"** — Almeida, Shoker & Baquero (2016) — how to ship only the delta instead of the whole state, the fix for state-based CRDT bandwidth:
  <https://arxiv.org/abs/1603.01529>
- **"Dotted Version Vectors"** — Preguiça et al. — the metadata refinement that lets a single replica accept concurrent client writes without conflating them:
  <https://arxiv.org/abs/1011.5808>
- **Marc Shapiro's CRDT page** — links to the talks, papers, and the canonical catalog:
  <https://crdt.tech/>

## CRDTs in production

- **Riak data types** — the production OR-set, counters, maps, registers; the system the Bet365 case study runs on:
  <https://docs.riak.com/riak/kv/latest/developing/data-types/>
- **Redis Active-Active (CRDB) / Redis CRDTs** — Redis Enterprise's geo-distributed CRDTs:
  <https://redis.io/docs/latest/operate/rs/databases/active-active/>
- **AntidoteDB** — the research-grade transactional CRDT database (highly available transactions + CRDTs):
  <https://www.antidotedb.eu/>
- **Bet365 + Riak case study** — how a betting platform used Riak CRDTs for high-availability state. Search "Bet365 Riak CRDT" for the talks and writeups; the lesson is the operational reality of CRDTs at scale.

## Collaborative editing CRDTs (the stretch goal)

- **Automerge** — a JSON CRDT library for local-first apps; read its internals for a real sequence CRDT:
  <https://automerge.org/>
- **Yjs** — the CRDT behind many collaborative editors; fast, battle-tested:
  <https://yjs.dev/>
- **Kleppmann, "CRDTs: The Hard Parts"** (talk, 2020) — the honest take on where CRDTs get genuinely difficult (text editing, garbage collection, undo). Essential viewing:
  search "Kleppmann CRDTs The Hard Parts" — posted free.

## Talks worth your time (free, no signup)

- **Martin Kleppmann, "CRDTs: The Hard Parts"** — the best honest overview of CRDT limits.
- **Marc Shapiro, CRDT talks** — the originator explaining strong eventual consistency.
- **"A CRDT Primer"** and the Riak/Basho talks — operational war stories from running CRDTs in production.

## Tools you'll use this week

- **Python 3.12+** — the CRDT zoo and the cart. Standard library only.
- **Go 1.22+** — the semilattice property test (uses `testing`/`testing/quick`-style property checks).
- **A diagram tool / paper** — for the semilattice (Hasse diagram) and the partition-heal traces. Drawing the lattice of a G-set is the fastest way to internalize "merge = least upper bound."

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Eventual consistency** | If writes stop, replicas eventually converge — but says nothing about *how* or whether data is lost. |
| **Strong eventual consistency (SEC)** | Replicas that received the same updates are *identical*, with convergence by construction (no conflict resolution). |
| **CRDT** | A data type whose merge is commutative+associative+idempotent, guaranteeing SEC with no coordination. |
| **CvRDT (state-based)** | Replicas hold a state and periodically merge whole states via a join (least upper bound). |
| **CmRDT (op-based)** | Replicas broadcast operations that commute; needs reliable causal delivery. |
| **Join-semilattice** | A partial order where every pair has a least upper bound (the merge) — the algebraic heart of CRDTs. |
| **Commutative** | `merge(a,b) == merge(b,a)` — order of merges doesn't matter. |
| **Associative** | `merge(merge(a,b),c) == merge(a,merge(b,c))` — grouping doesn't matter. |
| **Idempotent** | `merge(a,a) == a` — duplicate merges don't matter. |
| **G-counter** | Grow-only counter: per-replica counts, merge = element-wise max, value = sum. |
| **PN-counter** | Two G-counters (P for increments, N for decrements); value = sum(P) - sum(N). |
| **OR-set** | Observed-remove set: each add gets a unique tag; remove drops observed tags; add-wins on concurrency. |
| **LWW-register** | Last-writer-wins by timestamp — converges, but *discards* concurrent writes (a footgun). |
| **MV-register** | Multi-value register: keeps concurrent writes as siblings for the app to resolve. |
| **Tombstone** | A marker for a removed element, kept so the removal propagates; a source of metadata growth. |
| **Delta-CRDT** | Ships only the change (delta), not the whole state — the bandwidth fix for state-based CRDTs. |

---

*If a link 404s, please open an issue so we can replace it. These are classic papers and active project docs; mirrors are abundant.*
