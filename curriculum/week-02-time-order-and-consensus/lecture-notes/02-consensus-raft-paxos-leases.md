# Lecture 2 — Consensus: Raft Deeply, Paxos in Overview, and Leases with Fencing

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can trace Raft through an election, a replication round, and a leader failure; explain the safety argument; contrast it honestly with Paxos; and use leases with fencing tokens to make a lock safe against the slow-vs-dead problem.

Lecture 1 gave you logical order without a clock. This lecture uses it to solve **consensus** — getting a cluster to agree on a single value (or, repeatedly, a sequence of values: a replicated log) despite crashes and an unreliable network. Recall from Week 1 that FLP forbids *guaranteed* consensus in a fully asynchronous network; Raft and Paxos escape via the partial-synchrony hatch (timeouts). This lecture is that escape hatch, built.

If you remember one sentence:

> **Consensus is solved by a majority quorum (any two majorities overlap, so two conflicting decisions cannot both gather one) plus a logical-clock "term/ballot" to order leadership epochs — and the price you pay for FLP is an election timeout that occasionally fires wrongly, costing liveness but never safety.**

---

## Part 1 — Raft, deeply

Raft was designed for *understandability* — its explicit goal was to be a consensus algorithm a working engineer could implement correctly, unlike Paxos's reputation. It decomposes consensus into three subproblems: **leader election**, **log replication**, and **safety**. Master those three and you understand Raft.

Before the details, fix the mental model: **Raft is state-machine replication.** Every server runs the *same* deterministic state machine (for etcd, a key-value store). If every server applies the *same* sequence of commands in the *same* order, every server ends in the *same* state — that is the whole goal. The "replicated log" is the agreed-upon sequence of commands; consensus is just "agree on the next entry in the log." Leader election picks *who decides the order*; log replication *propagates the order*; safety guarantees *the order is never rewritten in a way that loses a committed command*. Keep that frame and every detail below is in service of "keep the logs identical so the state machines stay identical." This is the same idea Lamport's totally-ordered multicast (Lecture 1 §3.4) hinted at — Raft is the production-grade, fault-tolerant realization of it.

### 1.1 The state machine and the roles

Every Raft server is in one of three states:

- **Follower** — passive. Responds to RPCs from leaders and candidates. Starts as a follower.
- **Candidate** — a follower that timed out waiting for a leader and is now campaigning for votes.
- **Leader** — the single server (per term) that handles all client requests and drives log replication.

Time is divided into **terms**, each identified by a monotonically increasing integer (the cluster-wide logical clock from Lecture 1 §2). Each term begins with an election. There is **at most one leader per term** — that invariant is the spine of Raft's safety.

```
        times out,                  receives votes
        starts election             from majority
 ┌──────────┐ ───────────► ┌───────────┐ ──────────► ┌────────┐
 │ Follower │              │ Candidate │             │ Leader │
 └──────────┘ ◄─────────── └───────────┘ ◄────────── └────────┘
       ▲   discovers leader      │  discovers server      │
       │   or new term           │  with higher term      │
       └─────────────────────────┴────────────────────────┘
                   steps down to follower
```

### 1.2 Leader election (the FLP escape hatch in code)

Each follower runs a randomized **election timeout** (typically 150–300 ms). If it receives no `AppendEntries` (heartbeat) from a current leader before the timeout fires, it assumes there is no leader and starts an election:

1. Increment its **current term**.
2. Transition to **candidate**, vote for itself.
3. Send `RequestVote` RPCs to all other servers, including its last log index and term.
4. Outcomes:
   - **Wins** (gets votes from a majority): becomes leader, immediately sends heartbeats to assert authority.
   - **Loses** (another server, with an at-least-as-up-to-date log, becomes leader): on receiving a heartbeat from a legitimate leader of a term ≥ its own, it steps down to follower.
   - **Split vote** (no one gets a majority — e.g., two candidates campaign simultaneously): the timeout fires again, terms increment, and a *new* election starts.

The **randomized** timeout is what breaks split votes: because each server picks a random timeout in the range, it is unlikely two servers campaign at exactly the same time repeatedly, so elections resolve quickly in practice. *This randomization is the practical answer to FLP's split-vote stall* — it does not violate FLP (an adversarial schedule could still stall forever in theory), but under partial synchrony it terminates fast.

A server grants its vote at most once per term, and only to a candidate whose log is **at least as up-to-date** as its own (the election restriction, §1.5). The vote is persisted, so a crashed-and-restarted server does not vote twice in the same term — a safety necessity.

### 1.2b A worked election trace

Three servers S1, S2, S3, all followers in term 1 with leader S1. S1 crashes. Follow the election:

| Time | Event | S1 | S2 | S3 |
|---|---|---|---|---|
| t0 | steady state, S1 leader term 1 | leader (t1) | follower (t1) | follower (t1) |
| t1 | S1 crashes | ✗ down | follower (t1) | follower (t1) |
| t2 | S2's election timeout fires first | ✗ | candidate (t2), votes self | follower (t1) |
| t3 | S2 sends RequestVote(term=2) | ✗ | candidate (t2) | grants vote (updates to t2) |
| t4 | S2 has 2 votes (self + S3) = majority | ✗ | **leader (t2)** | follower (t2) |
| t5 | S2 sends heartbeats | ✗ | leader (t2) | follower (t2), resets timeout |
| t6 | S1 restarts, still thinks term 1 | follower? | leader (t2) | follower (t2) |
| t7 | S1 gets heartbeat term 2 > its term 1 | follower (t2) | leader (t2) | follower (t2) |

Notice the term acting as a logical clock: S2's election bumps the term to 2, and when S1 comes back believing it is still leader of term 1, the first heartbeat carrying term 2 *demotes it instantly* — a message from a higher term always wins, and the stale leader steps down. There is never a moment with two leaders in the *same* term. S1's stale leadership claim (term 1) is causally dominated by term 2, exactly as an older Lamport timestamp is dominated by a newer one. That is why "at most one leader per term" plus "higher term wins" is sufficient to prevent split-brain.

If instead S2 and S3 had *both* timed out at t2 and campaigned simultaneously, they'd split the vote (each votes for itself, neither reaches majority of 2... actually with 3 nodes one could still win if the third votes), and on a true tie both would time out again with *fresh random* timeouts, making a repeat collision unlikely. That randomized backoff is the practical defeat of FLP's split-vote stall.

### 1.3 Log replication

Once elected, the leader serves all client requests:

1. The client sends a command to the leader.
2. The leader appends the command to its log as a new **entry** (with the current term and an index).
3. The leader sends `AppendEntries` RPCs to followers to replicate the entry (these double as heartbeats).
4. Once the entry is replicated on a **majority** of servers, the leader **commits** it: it applies the command to its state machine and returns the result to the client.
5. The leader tells followers the commit index in subsequent `AppendEntries`, so they apply committed entries to their state machines too.

The **log-matching property** keeps logs consistent: if two logs contain an entry with the same index and term, then (a) they store the same command, and (b) the logs are identical in all preceding entries. Raft maintains this with a **consistency check** in `AppendEntries`: each `AppendEntries` includes the index and term of the entry *immediately preceding* the new ones; a follower rejects the RPC if it does not have a matching entry there. The leader then decrements and retries, walking backward until it finds the point where the logs agree, and overwrites the follower's divergent suffix. A follower's log is forced to match the leader's, never the reverse.

```
Leader log:    [1:x] [1:y] [2:z] [3:w]   (term:command)
Follower log:  [1:x] [1:y] [2:q]          <- diverged at index 3 (had q, term 2)
                                  ^
AppendEntries(prevIndex=2, prevTerm=2, entries=[3:w]) -> follower's index-2 matches,
but its index-3 entry [2:q] conflicts with leader's [3:w]: follower deletes [2:q]
and everything after, appends [3:w]. Logs now identical. Leader's log wins.
```

### 1.3b The two RPCs, field by field

Raft has exactly two RPCs in its core. Knowing their fields makes the protocol concrete and Exercise 1 mechanical.

**RequestVote** (candidate → others):

| Field | Meaning |
|---|---|
| `term` | candidate's term |
| `candidateId` | who is asking for the vote |
| `lastLogIndex` | index of candidate's last log entry |
| `lastLogTerm` | term of candidate's last log entry |
| → `voteGranted` | true if the voter granted its vote |
| → `term` | voter's current term (so a stale candidate updates and steps down) |

The voter grants iff: the candidate's `term` is ≥ its own, it hasn't already voted this term, **and** the candidate's log is at least as up-to-date (`lastLogTerm` higher, or equal term with `lastLogIndex` ≥). That last clause is the election restriction (§1.5).

**AppendEntries** (leader → followers; empty `entries` = heartbeat):

| Field | Meaning |
|---|---|
| `term` | leader's term |
| `leaderId` | so followers can redirect clients |
| `prevLogIndex` | index immediately preceding the new entries |
| `prevLogTerm` | term of `prevLogIndex` entry (the consistency check) |
| `entries[]` | log entries to store (empty for heartbeat) |
| `leaderCommit` | leader's commit index, so followers advance their own |
| → `success` | true if follower had a matching entry at `prevLogIndex`/`prevLogTerm` |
| → `term` | follower's term (demotes a stale leader) |

The `prevLogIndex`/`prevLogTerm` pair is the entire log-matching mechanism: a follower says "yes" only if it agrees with the leader at the position *just before* the new entries, which inductively guarantees the logs match everywhere before that point too. When a follower says "no," the leader walks `prevLogIndex` backward until it finds agreement. That is the whole replication algorithm in two fields.

### 1.4 The commit rule (and a subtle trap)

An entry is committed once it is stored on a majority of servers **and** the leader has replicated **at least one entry from its own current term**. That second clause is subtle and important: a leader may **not** consider an entry from a *previous* term committed merely because it is on a majority — doing so can be unsafe (the famous Figure 8 in the Raft paper). The leader commits older entries only *indirectly*, by committing a current-term entry above them (which, by the log-matching property, commits everything before it). Internalize this: **commit is majority-replication + a current-term entry on top.** Skipping the second clause is the single most common way a from-scratch Raft implementation becomes subtly unsafe.

### 1.5 Safety: the election restriction

Why can a newly elected leader safely overwrite followers' logs without ever destroying a committed entry? The **election restriction**: a candidate cannot win an election unless its log is at least as up-to-date as a majority of the cluster. "Up-to-date" is defined by (last entry's term, then last entry's index). Because a committed entry is on a majority, and any winning candidate has the votes of a majority, **the two majorities overlap in at least one server** — and that server would not have voted for a candidate missing the committed entry. Therefore **every leader contains all committed entries** (the Leader Completeness property), so when it forces followers to match its log, it never deletes a committed entry; it only deletes *uncommitted* divergent suffixes that were safe to lose.

This is the heart of Raft's safety proof, and it is pure quorum-overlap reasoning — the same idea as Week 1's quorum inequality. Two majorities of an `N`-node cluster always share a node; that shared node carries the truth forward. Trace it once in Exercise 1 and it becomes obvious.

To see *why* the restriction is necessary, imagine removing it. Suppose a candidate with a *stale* log (missing a committed entry) could win an election. As the new leader, it would force its log onto the followers — **deleting the committed entry** from the majority that had it. A client that was told "your write committed" now finds it gone. That is a catastrophic *safety* violation (a lost acknowledged write, the cardinal sin from Week 1). The election restriction exists precisely to make this impossible: by requiring a winner's log to be at least as up-to-date as a majority, and because a committed entry is on a majority, the winner *must* already have every committed entry. The restriction converts "we might lose a committed write during an election" into "we provably never do." It is the single most important line in the Raft safety argument, and forgetting it is how home-grown consensus loses data.

### 1.6 Persistence, snapshots, and membership

- **Persistent state.** Before responding to any RPC, a server persists `currentTerm`, `votedFor`, and its log to stable storage. This is what makes Raft safe across crashes: a restarted server remembers who it voted for and what it logged.
- **Snapshots.** A log grows without bound. Raft compacts it with **snapshots**: a server writes its state-machine state to a snapshot, then discards log entries the snapshot covers. The `InstallSnapshot` RPC ships a snapshot to a follower that has fallen too far behind. This is the production reality your etcd cluster does automatically.
- **Membership changes.** Adding/removing servers safely requires care (you cannot just swap the config, or two disjoint majorities could form). Raft uses **joint consensus** (a transitional config requiring majorities of *both* old and new) or, more commonly in practice, single-server-at-a-time changes. You will not implement this, but know it exists and is where Raft bugs love to hide.

---

## Part 2 — Paxos, in overview

You will operate Raft; you should *understand* Paxos, because it is the foundation of a generation of systems (Chubby, Spanner's underpinnings, many others) and the language senior engineers use.

### 2.0 Why learn Paxos if you'll run Raft?

Three reasons, all practical. First, **the foundational systems speak Paxos** — Chubby (Google's lock service that inspired ZooKeeper), Spanner's underpinnings, Megastore, and a generation of papers. You cannot read the literature or operate those systems without it. Second, **the interview**: staff-level system-design loops routinely ask "how does Paxos differ from Raft?" and a crisp answer signals depth. Third, and most importantly, **understanding Paxos clarifies what Raft's design choices buy you** — Raft's first-class leader and log are *responses* to Paxos being hard to implement; you appreciate the response only if you understand the problem. So: you'll run Raft, but you must be conversant in Paxos.

### 2.1 Single-decree Paxos

Paxos solves consensus on a *single* value with three roles (often co-located on the same servers): **proposers**, **acceptors**, and **learners**. It runs in two phases:

- **Phase 1 (Prepare/Promise).** A proposer picks a **ballot number** `n` (a logical clock, monotonically increasing and unique per proposer) and sends `Prepare(n)` to a majority of acceptors. An acceptor that has not promised a higher ballot replies `Promise(n)`, including any value it has already accepted. By promising, it agrees not to accept any proposal numbered less than `n`.
- **Phase 2 (Accept/Accepted).** If the proposer gets promises from a majority, it sends `Accept(n, v)` where `v` is **either** the value from the highest-numbered already-accepted proposal it learned about in Phase 1 **or**, if none, its own value. Acceptors accept unless they have since promised a higher ballot. Once a majority accepts `(n, v)`, `v` is **chosen**.

The safety comes from the same quorum overlap as Raft: any two majorities share an acceptor, and the Phase-1 rule "adopt the highest already-accepted value" ensures that once a value is chosen, every later proposal proposes that same value. No two different values can both be chosen.

A tiny worked Paxos run, 3 acceptors A1/A2/A3, two proposers racing:

| Step | Action | Result |
|---|---|---|
| 1 | Proposer P picks ballot `n=1`, sends `Prepare(1)` to A1,A2,A3 | A1,A2 promise (1); none had accepted yet |
| 2 | P got majority promises with no prior value → sends `Accept(1, "X")` | A1,A2 accept (1,"X") → **"X" is chosen** (majority) |
| 3 | Proposer Q picks ballot `n=2`, sends `Prepare(2)` | A1,A2 promise (2), and **report they accepted (1,"X")** |
| 4 | Q learned a prior accepted value → it MUST propose "X", not its own | sends `Accept(2, "X")` |
| 5 | A1,A2 accept (2,"X") | "X" still chosen — consistency preserved |

The magic is step 4: because Q's Phase-1 promises surfaced the already-accepted `(1,"X")`, the protocol *forces* Q to re-propose "X" rather than its own value. Once a value is chosen, the quorum-overlap guarantee ensures every future proposer learns it and re-proposes it. That is why Paxos never chooses two different values — the same safety Raft gets from the election restriction, reached by a different route.

### 2.2 Multi-Paxos and why Raft exists

Single-decree Paxos agrees on *one* value. Real systems need a *sequence* (a log). **Multi-Paxos** runs an instance per log slot and optimizes the common case by electing a stable leader that can skip Phase 1 for subsequent entries (amortizing the prepare). At that point Multi-Paxos and Raft are doing structurally similar things — a stable leader appending to a replicated log with majority commit.

The honest comparison:

| Dimension | Raft | Paxos (Multi-Paxos) |
|---|---|---|
| Design goal | Understandability | Minimality / generality |
| Leader | First-class, always present | Optional optimization on top of basic Paxos |
| Log | Central concept; logs forced to match leader | Per-slot instances; reconciliation is subtler |
| Reputation | "I can implement this correctly" | "Notoriously easy to get subtly wrong" |
| Where you'll meet it | etcd, Consul, CockroachDB, TiKV | Chubby, Spanner internals, Megastore, legacy systems |
| Membership changes | Specified (joint consensus / single-server) | Underspecified in the original paper; each system invents its own |

The takeaway senior engineers actually use: **Raft and Paxos are equivalent in power; Raft is easier to implement correctly because it makes the leader and the log first-class.** Most new systems in 2026 choose Raft for exactly that reason. Paxos remains important to *read* because the foundational systems and much of the literature speak it. "Paxos Made Live" (the resources) is the essential companion: it catalogs everything the original paper omits that production forces you to confront.

---

## Part 3 — Leases and fencing tokens

Consensus gives you agreement; now you want to *use* it to build a **distributed lock** (only one worker processes a queue, writes to a file, holds a resource). This is where a famous, subtle bug lives, and it ties directly back to Week 1's slow-vs-dead indistinguishability.

### 3.0 Why consensus alone does not give you a safe lock

A common misunderstanding: "I have etcd, which is linearizable, so a lock built on it is automatically safe." Consensus makes the *lock service* agree on *who currently holds the lock* — that part is correct and strongly consistent. But the lock service cannot control what the *client* does after acquiring the lock, and the client lives outside the consensus group. The client can be paused, descheduled, or GC-frozen *after* it acquires the lock and *before* it acts, and during that pause the lease can expire and be reassigned. The consensus layer did its job perfectly; the gap is between "the lock service knows who holds the lock" and "the holder knows whether it still holds the lock." That gap is unbridgeable from the client's side — which is exactly why the *storage* must enforce the fencing token. Consensus gives you a correct lock *registry*; fencing tokens give you a correct lock *effect*. You need both, and conflating them is the bug.

### 3.1 A lease is a time-bounded lock

A naive lock held forever is dangerous: if the holder crashes, the lock is held forever and nobody else can proceed. The fix is a **lease** — a lock with an expiry. The holder must *renew* it before it expires; if the holder crashes, the lease expires and someone else can acquire it. etcd, ZooKeeper, and Consul all give you leases (etcd calls them leases; ZooKeeper uses ephemeral nodes + sessions; Consul uses sessions).

### 3.2 The bug: a lease is not enough

Here is the failure that Kleppmann's "How to do distributed locking" essay made famous. Client 1 acquires a 10-second lease and starts writing to shared storage. Then:

1. Client 1 acquires the lease at `t=0`.
2. Client 1 suffers a **stop-the-world GC pause** (or is descheduled, or its disk stalls) from `t=2` to `t=14` — *twelve seconds* during which it does nothing but is not dead.
3. At `t=10` the lease *expires*. The lock service correctly hands the lease to Client 2.
4. Client 2 acquires the lease and writes to storage.
5. At `t=14` Client 1 **wakes up**, still believing it holds the lease (its own clock didn't notice the pause was that long), and writes to storage.

Now **two clients wrote to storage believing they held the lock.** The lock service did nothing wrong — the lease genuinely expired. The problem is that Client 1 could not tell it had been paused past expiry. This is *exactly* the slow-vs-dead problem from Week 1, §FLP: from the lock service's view, a paused client is indistinguishable from a dead one, and the lease has to assume the worst.

```
 t=0    Client1 acquires lease (expires t=10)
 t=2    ░░░░░░░░░░░░ Client1 GC-paused ░░░░░░░░░░░░  (still "holds" lease in its mind)
 t=10                         lease expires; Client2 acquires
 t=11                         Client2 writes (token 34) ──► storage OK
 t=14   Client1 wakes, writes (token 33, STALE) ──────────► storage MUST reject
```

### 3.3 The fix: fencing tokens

The lock service issues, with every lease grant, a **monotonically increasing fencing token** — a number that goes up by one each time the lock is granted. Every write to storage carries the token. **The storage system remembers the highest token it has seen and rejects any write carrying a lower one.**

In the scenario above: Client 1 holds token 33; Client 2 is granted the lease and gets token 34. Client 2 writes with token 34; storage records "highest seen = 34." When Client 1 wakes and writes with token 33, **storage rejects it** (33 < 34). The stale write is fenced off. Safety is preserved *even though* Client 1 wrongly believed it held the lock, because the truth is enforced at the storage layer by a monotonic number, not by the client's belief.

```python
class FencedStorage:
    """Storage that rejects writes carrying a stale fencing token."""
    def __init__(self):
        self._highest_token = 0
        self._data = None

    def write(self, value, token: int) -> bool:
        if token < self._highest_token:
            # A holder that THINKS it still owns the lock, but was fenced.
            return False  # rejected: stale token
        self._highest_token = token
        self._data = value
        return True
```

The fencing token is the lock-service analogue of Raft's term and Paxos's ballot — a monotonic logical number that lets the system reject stale actors. It is the same idea (Lecture 1's logical clocks) applied to locking. **A lock API that hands you a lease but no fencing token cannot be made safe against pauses; recognizing that absence on sight is a senior skill.** When you evaluate a locking library, the first question is "where is my fencing token, and does my storage check it?" If the answer is "there isn't one," the lock is unsafe under exactly the GC-pause scenario above, and no amount of careful client code fixes it.

### 3.3b Operating Raft: the knobs that bite

When you run etcd on Friday, three settings determine its behavior, and all three trace back to FLP and the partial-synchrony bet:

- **Election timeout (etcd `--election-timeout`, default ~1000 ms).** How long a follower waits without a heartbeat before campaigning. *Too low:* a momentarily slow network triggers needless elections (churn, brief write pauses). *Too high:* a genuinely dead leader leaves the cluster write-unavailable for longer. This is the FLP liveness bet, exposed as a flag.
- **Heartbeat interval (etcd `--heartbeat-interval`, default ~100 ms).** How often the leader sends `AppendEntries` heartbeats. The rule of thumb: election timeout should be **~10×** the heartbeat interval, so a single dropped heartbeat doesn't trigger an election but a real outage is detected within a few intervals.
- **Snapshot count / disk latency.** Raft must `fsync` its log before responding — so **disk latency is consensus latency.** A slow disk on the leader stalls every commit. Production etcd is notoriously sensitive to disk fsync latency; a noisy-neighbor disk looks, to Raft, like a slow leader, and can trigger elections. This is the operational face of "a slow process is indistinguishable from a dead one."

A 2026 operational heuristic: **run etcd on dedicated, fast (NVMe) disks, keep the cluster to 3 or 5 members, place them in different failure domains but with low inter-node latency, and watch the `etcd_server_leader_changes_seen_total` metric** — a rising leader-change count is your cluster paying the FLP tax, and it usually means disk or network trouble, not a Raft bug.

### 3.4 The Raft consumers that give you these primitives

- **etcd** — leases (`Grant`, `KeepAlive`), and revision numbers that serve as fencing tokens. The mini-project and Friday's lab use etcd.
- **ZooKeeper** — ephemeral znodes tied to a session (auto-deleted on disconnect) and the `zxid` (a monotonic transaction id) usable as a fence.
- **Consul** — sessions and locks, with `ModifyIndex` as the monotonic fence.

All three are Raft/Zab-backed: the lock's *correctness* rests on the consensus layer agreeing on who holds it, and the *safety against pauses* rests on you carrying the fencing token through to storage.

> **The interview tell:** ask a candidate to design a distributed lock and watch whether they mention the fencing token. Designing a lease without one is the most common "I read about distributed locking but never operated it" mistake. The lease handles *crashes* (the holder dies, the lease expires); the fencing token handles *pauses* (the holder freezes past expiry and wakes up stale). You need both, because FLP guarantees you cannot distinguish the two from the outside. A lock design that only handles crashes is unsafe, and you should be able to name the exact GC-pause scenario that breaks it.

---

## Part 3b — Five consensus misconceptions to kill

- **"Raft needs all nodes up to work."** No — it needs a *majority*. A 5-node cluster tolerates 2 failures; a 3-node cluster tolerates 1. The minority is what becomes unavailable (the CP choice from Week 1). This is also why you run *odd* cluster sizes: 4 nodes tolerate the same 1 failure as 3 but pay more coordination — a wasted node.
- **"More nodes = more available."** More nodes = more *fault tolerance* but *slower* commits (larger quorum to gather) and, past a point, *worse* availability per the larger surface for partitions. 3 or 5 nodes is the sweet spot for most coordination clusters; 7 is rare; 9 is almost always a mistake.
- **"The leader's reads are always linearizable for free."** A leader can be a *stale* leader — partitioned away while a new leader was elected — and not yet know it. A truly linearizable read must confirm the node is still leader (a heartbeat round / `ReadIndex`, or a lease). etcd's "serializable" reads skip this and can be stale; its "linearizable" reads pay the round trip. This is the EL/EC choice from Week 1, living inside etcd's read API.
- **"An entry on a majority is committed."** Only if the leader has also replicated a *current-term* entry (§1.4). The Figure-8 scenario shows a majority-replicated *previous-term* entry can still be overwritten. Commit = majority + current-term entry on top.
- **"Paxos and Raft are fundamentally different algorithms."** They are the same idea (leader + log + majority + a logical ballot/term) with different presentations. Raft made the leader and log first-class for understandability; Multi-Paxos arrives at nearly the same structure by optimizing basic Paxos. Equivalent power, different pedagogy.

## 4. Putting it together

```
 Logical clocks (Lecture 1)
        │  give "order without a wall clock"
        ▼
 Term / ballot number  ── a cluster-wide logical clock for leadership epochs
        │
        ▼
 Majority quorum  ── any two majorities overlap, so two conflicting
        │             decisions can't both gather one
        ▼
 Consensus (Raft / Paxos)  ── agree on a replicated log, despite FLP,
        │                      via the partial-synchrony (timeout) escape
        ▼
 Coordination service (etcd / ZK / Consul)  ── leader election, leases
        │
        ▼
 Lease + FENCING TOKEN  ── a safe distributed lock even under GC pauses
```

Every layer rests on the one below. Logical clocks give order; quorum overlap gives safety; consensus gives an agreed log; the coordination service packages it; and the fencing token makes the lock you build on top safe against the slow-vs-dead problem FLP guarantees you cannot avoid.

This stack is also the architectural backbone of the rest of Crunch Mesh. The capstone's `inventory-service` uses leases + fencing tokens for single-writer-per-SKU. Phase 4's multi-region work runs Raft-replicated state across regions. Every "how do we agree?" question in the course resolves to "run it through this stack." You are not learning Raft as trivia; you are learning the primitive that every coordination decision in the next 22 weeks will lean on.

## 5. Recap

You should now be able to:

- Trace **Raft** through leader election (randomized timeout, RequestVote, majority), log replication (AppendEntries, log-matching, the consistency check), and a leader failure.
- State Raft's **commit rule** (majority replication + a current-term entry on top) and the **election restriction** that guarantees Leader Completeness via quorum overlap.
- Explain **Paxos** at the level of Prepare/Promise and Accept/Accepted, why Multi-Paxos exists, and why Raft is generally easier to implement correctly.
- Describe the **lease-without-fencing bug** (a GC-paused client writing after its lease expired) and fix it with a **monotonic fencing token** the storage layer checks.
- Recognize a lock API that lacks a fencing token as unsafe under pauses, and name the Raft consumers (etcd, ZooKeeper, Consul) that provide these primitives.

A final synthesis to carry forward: **consensus is how a distributed system manufactures a single source of truth out of unreliable parts.** Quorum overlap gives it safety; a logical-clock term/ballot gives it order; the partial-synchrony timeout gives it (eventual) liveness despite FLP; and the fencing token extends that truth all the way to the storage layer where real work happens. Every coordination problem you will face — who is the leader, what is the next log entry, who holds the lock, which config is current — is the same problem in different clothes, and the answer is always this stack. When you operate etcd on Friday and watch a term increment on a leader kill, you are watching every idea in this lecture execute at once.

Next: the exercises put this in your hands — trace a Raft election, implement vector clocks and detect concurrency, and reproduce-then-fix the fencing bug. Continue to [the exercises](../exercises/README.md).

---

## References

- *In Search of an Understandable Consensus Algorithm (Raft)* — Ongaro & Ousterhout (2014): <https://raft.github.io/raft.pdf>
- *Paxos Made Simple* — Lamport (2001): <https://lamport.azurewebsites.net/pubs/paxos-simple.pdf>
- *Paxos Made Live* — Chandra, Griesemer & Redstone (2007): <https://research.google/pubs/pub33002/>
- *How to do distributed locking* — Kleppmann (2016): <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html>
- *The Chubby lock service* — Burrows (OSDI 2006): <https://research.google/pubs/pub27897/>
- *etcd Raft library*: <https://github.com/etcd-io/raft>
