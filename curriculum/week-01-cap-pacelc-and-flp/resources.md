# Week 1 — Resources

Every resource here is **freely available** — the original papers are open via author pages or institutional mirrors, the canonical book chapters are widely excerpted, and the talks are free with no signup. Distributed-systems theory has the rare property that the *primary sources* are both authoritative and readable; you should read the originals, not third-hand summaries.

When a paper has a canonical PDF on the author's university page, that URL is given. If a link 404s, the paper's title is enough to find a mirror — these are among the most-cited papers in computer science.

## Required reading (work it into your week)

- **Gilbert & Lynch, "Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services"** (2002) — the paper that turned CAP from a conjecture into a theorem. Read it Monday, then again Thursday:
  <https://groups.csail.mit.edu/tds/papers/Gilbert/Brewer2.pdf>
- **Abadi, "Consistency Tradeoffs in Modern Distributed Database System Design" (PACELC)** (IEEE Computer, 2012) — the reformulation that fixes CAP's biggest blind spot. This is the most practically useful single reading of the week:
  <https://www.cs.umd.edu/~abadi/papers/abadi-pacelc.pdf>
- **Fischer, Lynch & Paterson, "Impossibility of Distributed Consensus with One Faulty Process" (FLP)** (1985) — the impossibility result. Read the theorem statement and §3 (the bivalence argument); skim the rest:
  <https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf>
- **Brewer, "CAP Twelve Years Later: How the 'Rules' Have Changed"** (IEEE Computer, 2012) — Brewer himself walking back the "pick two" framing. Read this *after* Gilbert–Lynch so you appreciate the correction:
  <https://www.infoq.com/articles/cap-twelve-years-later-how-the-rules-have-changed/>

## The canonical chapters

- **Kleppmann, *Designing Data-Intensive Applications*, Chapter 9 ("Consistency and Consensus")** — the single best book treatment of linearizability, the CAP debate, and consensus. If you own one distributed-systems book, this is it. Chapter 5 (replication) and Chapter 7 (transactions, isolation levels) are the supporting cast.
- **Kleppmann, "Please stop calling databases CP or AP"** (blog, 2015) — a sharp argument that the CAP labels are too coarse and you should name the actual consistency model instead. Read it; then disagree with it productively:
  <https://martin.kleppmann.com/2015/05/11/please-stop-calling-databases-cp-or-ap.html>

## Consistency models — the lattice in depth

- **Bailis et al., "Highly Available Transactions: Virtues and Limitations"** (VLDB 2014) — maps the isolation/consistency models onto what is achievable under partition. The diagram alone is worth printing:
  <https://www.vldb.org/pvldb/vol7/p181-bailis.pdf>
- **Viotti & Vukolić, "Consistency in Non-Transactional Distributed Storage Systems"** (ACM Computing Surveys, 2016) — the definitive map of *every* consistency model and how they relate. A reference, not a cover-to-cover read:
  <https://arxiv.org/abs/1512.00168>
- **Jepsen — "Consistency Models"** — Kyle Kingsbury's interactive lattice diagram. The single best one-page mental model of how the models nest:
  <https://jepsen.io/consistency>

## Linearizability and history checking (for the exercises)

- **Herlihy & Wing, "Linearizability: A Correctness Condition for Concurrent Objects"** (1990) — the paper that defines linearizability. The "is this history linearizable?" question in Exercise 3 comes straight from here:
  <https://cs.brown.edu/~mph/HerlihyW90/p463-herlihy.pdf>
- **Jepsen / Knossos & Elle** — the real linearizability checkers used to find consistency bugs in production databases. Read how they model histories:
  <https://jepsen.io/analyses>

## PACELC classifications you can trust

- **Abadi's PACELC table** (in the paper above) — the original classifications: Dynamo/Cassandra/Riak as PA/EL, fully-ACID single-master systems as PC/EC, PNUTS as PC/EL.
- **Spanner: "Spanner: Google's Globally-Distributed Database"** (OSDI 2012) — the system that uses TrueTime to be effectively PC/EC at global scale by *bounding* clock uncertainty rather than denying it:
  <https://research.google/pubs/pub39966/>

## Talks worth your time (free, no signup)

- **Kyle Kingsbury (aphyr), "Jepsen" conference talks** — testing real databases against their consistency claims and watching them fail. Search the Strange Loop and GOTO archives; every one is posted free.
- **Peter Bailis, "Silence is Golden: Coordination-Avoiding Systems"** — why avoiding coordination (the CAP "A" side) is sometimes correct and how to do it safely.
- **Martin Kleppmann, "Transactions: myths, surprises and opportunities"** — the consistency/isolation confusion, untangled, by the DDIA author.

## Tools you'll use this week

- **Go 1.22+** — `go run`, `go test`. The register and the linearizability checker are pure-Go, no external dependencies.
- **`go test -race`** — the race detector. You will run the register lab under it to prove your partition simulation has no accidental shared-state bugs.
- **A diagram tool** (Excalidraw, draw.io, or pen and paper) — for the consistency lattice and the partition argument. Drawing the two-node CAP proof yourself is the fastest way to internalize it.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **CAP** | Under a network **P**artition, a distributed system must choose **C**onsistency or **A**vailability — it cannot keep both. |
| **Consistency (CAP sense)** | Linearizability: every read sees the most recent completed write, as if there were one copy of the data. |
| **Availability (CAP sense)** | Every request to a non-failing node returns a non-error response (eventually, not necessarily quickly). |
| **Partition tolerance** | The system keeps operating even when the network drops arbitrarily many messages between nodes. |
| **Linearizable** | There is a single, real-time-respecting total order of operations; the strongest single-object model. |
| **Sequential** | A single total order exists, but it need not respect real-time across clients. |
| **Causal** | Causally related operations are seen in the same order everywhere; concurrent ones may differ. |
| **Eventual** | If writes stop, all replicas eventually converge to the same value. The weakest useful guarantee. |
| **PACELC** | **P** → choose **A** or **C**; **E**lse (no partition) → choose **L**atency or **C**onsistency. CAP plus the steady state. |
| **FLP** | In an asynchronous network with one possible crash, no deterministic protocol guarantees consensus *terminates*. |
| **Safety** | "Nothing bad ever happens." Violated by a finite prefix of an execution. |
| **Liveness** | "Something good eventually happens." Violated only by an infinite execution. |
| **Partial synchrony** | The assumption that the network is *eventually* timely — the escape hatch that lets Raft/Paxos work despite FLP. |
| **Quorum** | A subset of nodes (usually a majority) whose agreement is required to commit; majority quorums guarantee any two overlap. |

---

*If a link 404s, please open an issue so we can replace it. These are classic papers; mirrors are abundant.*
