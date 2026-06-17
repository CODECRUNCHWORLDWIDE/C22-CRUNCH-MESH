# Week 1 — The Literature: CAP, PACELC, and FLP

Welcome to the week that earns you the right to argue about consistency at a whiteboard. Crunch Mesh deliberately resists letting you write a service in week 1. The single biggest source of broken distributed systems is not a bug in the code — it is a reasoning error in the design, made by an engineer who conflated two consistency models, or believed a guarantee the system never offered. The corrective is reading, slowly, the three results that bound what any distributed system can do: **CAP**, **PACELC**, and **FLP**.

By Friday you will be able to look at any storage system — Postgres, DynamoDB, etcd, Cassandra, Spanner — and state, without hand-waving, what it gives up under a partition, what it gives up in the *absence* of a partition, and why no amount of engineering will let it dodge the FLP impossibility result in an asynchronous network. You will read a vendor's marketing page that claims "strong consistency *and* high availability" and know exactly which word is doing the lying.

The one thing to internalize before you read another line: **CAP is not "pick two of three." It is a statement about one specific moment — the moment a network partition occurs — and at that moment you choose between consistency and availability. The rest of the time CAP says nothing, which is exactly why PACELC exists.** The "pick two" mnemonic has done more damage to distributed-systems literacy than any other sentence in the field, because it lets people believe "CA" is an achievable category for a distributed system. It is not. A single-node database is CA. The moment your data lives on two machines connected by a network that can drop packets, the only real choice is CP or AP.

This week is where you stop reciting CAP as trivia and start using it as a design tool.

## Learning objectives

By the end of this week, you will be able to:

- **State** the CAP theorem precisely — Gilbert and Lynch's formalization, not the napkin version — and explain why "CA" is not a coherent category for a system that spans a network.
- **Distinguish** the consistency models that the word "consistency" hides: **linearizable**, **sequential**, **causal**, and **eventual** — and place real systems on that lattice.
- **Apply** PACELC to separate the partition-time tradeoff (C vs A) from the steady-state tradeoff (latency vs consistency), and classify systems as PC/EC, PA/EL, PC/EL, or PA/EC.
- **Explain** the FLP impossibility result — that no deterministic consensus protocol can guarantee termination in an asynchronous network with even one crash failure — and why real systems (Raft, Paxos) escape it in practice with timeouts and randomization.
- **Separate** a **safety** property ("nothing bad ever happens") from a **liveness** property ("something good eventually happens"), and recognize which one each guarantee in a spec is.
- **Build** a two-node register in Go with a controllable, simulated network partition, and **experimentally exhibit** the CP regime (reject writes to stay consistent), the AP regime (accept writes and diverge), and the impossibility of being both during the partition.
- **Read** a system's documentation and translate its consistency claims into the precise model it actually provides, calling out where the marketing and the manual disagree.

## Prerequisites

This week assumes the C22 entry bar (see the course `README.md`): production backend experience, comfort with Go or Python, and Kubernetes basics. Specifically for this week:

- **Go 1.22+** installed (`go version` works). The lab register is written in Go; the algorithms are simple, so even a Go beginner can follow them, but you should be able to read a goroutine and a channel without a tutorial.
- Comfort reading a **research paper's theorem statement** — you do not need to follow every proof line, but you must be willing to sit with a formal definition until it stops being intimidating.
- A mental model of a **network as an unreliable channel**: messages can be dropped, delayed, reordered, and duplicated, and a node cannot distinguish "the other node is dead" from "the other node is slow or unreachable." If that distinction is new to you, this week makes it permanent.
- Basic familiarity with **HTTP semantics** (status codes, request/response) — we use them as a metaphor for read/write operations on a register.

You do **not** need prior consensus or replication experience. We start at the theorems and build the intuition from first principles. This is the foundation the entire rest of Crunch Mesh stands on.

## Topics covered

- **The CAP theorem, formally.** Brewer's 2000 PODC conjecture; the Gilbert–Lynch 2002 proof; the precise definitions of *consistency* (linearizability), *availability* (every request to a non-failing node returns a non-error response), and *partition tolerance* (the network may drop arbitrarily many messages). Why "CA" describes a single node, not a distributed system.
- **What "consistency" actually means.** The consistency lattice: **linearizable** (the strongest single-object model — there is one real-time order), **sequential** (a single total order, but not necessarily real-time), **causal** (causally related operations are seen in order; concurrent ones may differ across replicas), and **eventual** (replicas converge if writes stop). Where "strong consistency," "read-your-writes," and "monotonic reads" sit.
- **PACELC.** Daniel Abadi's 2012 reformulation: **if** there is a **P**artition, trade **A**vailability against **C**onsistency; **e**lse, in normal operation, trade **L**atency against **C**onsistency. The four-corner taxonomy (PA/EL, PC/EC, PA/EC, PC/EL) and how it classifies DynamoDB, Cassandra, Spanner, etcd, and a default single-leader Postgres.
- **The FLP impossibility result.** Fischer, Lynch, and Paterson (1985): in a fully asynchronous system, no deterministic protocol solves consensus if even one process may crash, because you cannot distinguish a slow process from a dead one. What FLP does and does **not** forbid, and the three escape hatches real systems use: **partial synchrony** (timeouts), **randomization**, and **failure detectors**.
- **Safety vs liveness.** Lamport's distinction: a **safety** property says "nothing bad ever happens" (violated by a finite execution prefix); a **liveness** property says "something good eventually happens" (violated only by an infinite execution). Why FLP is fundamentally a *liveness* result — consensus protocols stay *safe* (never decide two different values) but cannot guarantee *liveness* (always eventually decide).
- **Reading systems through this lens.** A field guide: taking a real system's consistency documentation and translating it into linearizable/sequential/causal/eventual, PACELC corner, and which guarantees are safety vs liveness.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | CAP formally; the consistency lattice                  |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | PACELC; classifying real systems                       |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | FLP impossibility; the three escape hatches            |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Safety vs liveness; reading systems critically         |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The two-node register; exhibiting CP/AP experimentally |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                 |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, writeup polish                           |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The original papers, the canonical chapters, and the talks worth your time |
| [lecture-notes/01-cap-and-the-consistency-lattice.md](./02-lecture-notes/01-cap-and-the-consistency-lattice.md) | CAP formally, the four consistency models, and why "CA" is a category error |
| [lecture-notes/02-pacelc-flp-safety-liveness.md](./02-lecture-notes/02-pacelc-flp-safety-liveness.md) | PACELC, the FLP impossibility proof, the escape hatches, and safety vs liveness |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-classify-the-systems.md](./03-exercises/exercise-01-classify-the-systems.md) | Place ten real systems on the consistency lattice and the PACELC grid, with justification |
| [exercises/exercise-02-partitioned-register.go](./03-exercises/exercise-02-partitioned-register.go) | A two-node register with a simulated partition; switch it between CP and AP and observe the difference |
| [exercises/exercise-03-linearizability-checker.go](./03-exercises/exercise-03-linearizability-checker.go) | A history checker that decides whether a recorded execution is linearizable |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-audit-a-real-system.md](./04-challenges/challenge-01-audit-a-real-system.md) | Audit a real system's consistency claims against its actual guarantees and write the verdict |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the consistency-audit memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The instrumented two-node register that experimentally exhibits all three CAP regimes |

## The "name the tradeoff" promise

C22 uses a recurring marker for every exercise that ends in a *named, defended* tradeoff. When you finish the partitioned-register lab, you should be able to fill in this template for the system you built, without hesitation:

```
During a partition, my register is in ___ mode (CP / AP).
- If CP: it refuses ___ (reads / writes / both) on the minority side to preserve ___.
- If AP: it accepts ___ and the cost is ___ (stale reads / divergent state needing reconciliation).
In the absence of a partition (the "else" of PACELC), it trades ___ for ___.
```

If you cannot fill every blank with a specific, defensible answer, you have built a system whose behavior you don't understand — which is the only kind of distributed system worth never shipping. The point of week 1 is to make filling in that template reflexive.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Gilbert–Lynch proof** (the 2002 SIGACT paper) line by line until you can reproduce the partition argument from memory: two nodes, a dropped message, and the proof that you cannot be both available and consistent. It is four pages and worth every minute.
- Read the **FLP paper's** "bivalent configuration" argument and write a one-paragraph plain-English summary of why a deterministic protocol always has a reachable configuration from which either decision is still possible.
- Extend your register from the lab to **three nodes with majority quorum** and show that a minority partition (1 node) cannot make progress in CP mode while the majority (2 nodes) can — the seed of the consensus material in Week 2.
- Run **Jepsen** against a local single-node service of your choice (or read the most recent Jepsen report for a database you use) and map every violation it reports back to a consistency-model name from this week.

## Up next

Week 2 takes the impossibility results you internalized here and shows how real systems *route around* them: logical clocks to order events without a global clock, and Raft/Paxos to reach consensus despite FLP, using the partial-synchrony escape hatch. The register you built this week becomes a Raft replicated log next week. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
