# Week 2 — Resources

Every resource here is **freely available**. Lamport's paper, the Raft paper, and "Paxos Made Simple" are open via author pages. The Raft visualization is a free interactive site. The etcd docs are open. No paywalled material is linked.

The two papers you must actually read this week are **Lamport 1978** and the **Raft paper** — they are short, foundational, and directly implemented in the labs.

## Required reading (work it into your week)

- **Lamport, "Time, Clocks, and the Ordering of Events in a Distributed System"** (1978) — the paper that invented happens-before and logical clocks. One of the most influential papers in CS; read it Monday and again Tuesday:
  <https://lamport.azurewebsites.net/pubs/time-clocks.pdf>
- **Ongaro & Ousterhout, "In Search of an Understandable Consensus Algorithm (Extended Version)" (Raft)** (2014) — read §5 (the core algorithm) closely; it is the heart of Wednesday and the mini-project:
  <https://raft.github.io/raft.pdf>
- **The Raft visualization (raftscope / "The Secret Lives of Data")** — watch an election and a replication round animate. Do this *before* Exercise 1:
  <https://raft.github.io/> and <http://thesecretlivesofdata.com/raft/>
- **Kleppmann, *Designing Data-Intensive Applications*, Chapter 8 ("The Trouble with Distributed Systems")** — the clock-skew, GC-pause, and fencing-token material. Chapter 9 (consensus) continues from Week 1.

## Consensus in depth

- **Lamport, "Paxos Made Simple"** (2001) — the readable reformulation of the original Paxos paper. Read it for Thursday's overview; you are not implementing Paxos, only understanding it:
  <https://lamport.azurewebsites.net/pubs/paxos-simple.pdf>
- **Chandra, Griesemer & Redstone, "Paxos Made Live"** (2007) — what it actually took to ship Paxos in Google's Chubby lock service. The gap between the paper and production:
  <https://research.google/pubs/pub33002/>
- **Ongaro, "Consensus: Bridging Theory and Practice"** (PhD thesis, 2014) — the full Raft treatment, including membership changes and log compaction, for the stretch goals:
  <https://github.com/ongardie/dissertation>

## Clocks and ordering

- **Lamport's happens-before, distilled** — Kleppmann's DDIA §5 (replication) and §8 (clocks) reframe it with modern examples.
- **"There is No Now"** (Justin Sheehy, ACM Queue, 2015) — a short, sharp essay on why "now" is not a thing you can rely on across machines:
  <https://queue.acm.org/detail.cfm?id=2745385>
- **Google Spanner / TrueTime** (OSDI 2012) — the one system that makes *bounded* physical time a usable ordering primitive, by measuring its uncertainty:
  <https://research.google/pubs/pub39966/>

## Leases, fencing, and locks

- **Kleppmann, "How to do distributed locking"** (2016) — the canonical explanation of why a lease without a fencing token is unsafe, written as a critique of a Redis locking pattern. Required for Thursday:
  <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html>
- **The Chubby paper (Burrows, OSDI 2006)** — Google's lock service, the origin of much lease/sequencer thinking:
  <https://research.google/pubs/pub27897/>

## The coordination services (the Raft consumers you'll operate)

- **etcd documentation** — the Raft-backed key-value store you run on Kind this week:
  <https://etcd.io/docs/latest/>
- **etcd Raft implementation** — the most-used production Raft library (also powering CockroachDB, Kubernetes' own store):
  <https://github.com/etcd-io/raft>
- **ZooKeeper / Zab** — the older coordination service; Zab is Raft-adjacent (atomic broadcast):
  <https://zookeeper.apache.org/doc/current/>
- **HashiCorp Consul + the `hashicorp/raft` library** — another production Raft you can read:
  <https://github.com/hashicorp/raft>

## Talks worth your time (free, no signup)

- **Diego Ongaro, "Raft: A Consensus Algorithm for Replicated Logs"** — the author explaining Raft. The clearest 60 minutes on the topic:
  search the Stanford / USENIX archives for the Raft talk.
- **John Ousterhout, "Raft (or, How to Build a Highly Available Storage System)"** — the co-author's lecture version.
- **Camille Fournier, "Hopelessly Distributed: The Reality of Building Distributed Systems"** — operational wisdom on running coordination services like ZooKeeper in anger.

## Tools you'll use this week

- **Python 3.12+** — the Lamport/vector-clock and fencing-token labs. Standard library only.
- **Kind + kubectl + Docker/Podman** — the 3-node etcd cluster.
- **`etcdctl`** — the etcd CLI: `etcdctl endpoint status --write-out=table`, `member list`, `move-leader`. Your primary tool for watching elections.
- **A whiteboard or paper** — Exercise 1 is a hand-trace of a Raft election. Do it on paper before you check it against the visualization.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Happens-before (`→`)** | a → b if a could have caused b: same-process order, or send→receive, or transitively. |
| **Concurrent (`∥`)** | a ∥ b if neither happens-before the other — no causal relationship. |
| **Lamport timestamp** | A single counter per process; gives a total order consistent with → but cannot detect concurrency. |
| **Vector clock** | One counter per process; a partial order that *can* detect concurrency (incomparable vectors). |
| **Clock skew** | The difference between two machines' clocks at an instant. |
| **Clock drift** | The rate at which a clock gains/loses time relative to true time. |
| **NTP step** | A correction that can move a clock *backward* — why monotonic time exists. |
| **Term (Raft)** | A logical clock for the cluster: a monotonically increasing number, one leader per term. |
| **Election timeout** | The time a follower waits without hearing from a leader before starting an election (the FLP escape hatch). |
| **AppendEntries** | The Raft RPC that replicates log entries and serves as the leader's heartbeat. |
| **RequestVote** | The Raft RPC a candidate uses to gather votes during an election. |
| **Commit (Raft)** | An entry is committed once it is replicated on a majority and the leader has an entry from its current term. |
| **Quorum** | A majority of nodes; any two quorums overlap, which is what makes consensus safe. |
| **Lease** | A time-bounded lock — held until it expires unless renewed. |
| **Fencing token** | A monotonically increasing number issued with a lock; storage rejects writes carrying an old token. |
| **Paxos** | The original consensus protocol: proposers, acceptors, learners; prepare/promise, accept/accepted. |

---

*If a link 404s, please open an issue so we can replace it. These are classic papers and active project docs; mirrors are abundant.*
