# Exercise 1 — Trace a Raft Election

**Goal:** By hand, trace a 5-node Raft cluster through a leader crash, a leader election, and one round of log replication — naming the term, the votes, the commit rule, and the election restriction at each step. Then verify your trace against the official Raft visualization. You will train the single most important consensus skill: predicting what a Raft cluster does *before* you watch it.

**Estimated time:** 60 minutes. Written, then interactive.

---

## Setup

You need paper (or a markdown file) and a browser for the visualization:

- The Raft visualization: <https://raft.github.io/> (the embedded "raftscope" simulator)
- "The Secret Lives of Data" animated walkthrough: <http://thesecretlivesofdata.com/raft/>

Do the paper trace **first**. Predict, then verify. Watching the animation before tracing teaches you nothing.

---

## Part A — Trace a leader election (on paper)

A 5-node cluster: S1, S2, S3, S4, S5. All start as followers in **term 3**, with **S1 the leader**. Every server's log is identical: entries `[1:a][2:b][3:c]` (term:command). Now **S1 crashes**.

Fill in this trace. At each step, write down (1) each server's state (follower/candidate/leader), (2) its current term, and (3) what RPC was sent.

| Step | Event | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|---|
| 0 | steady state | leader t3 | foll t3 | foll t3 | foll t3 | foll t3 |
| 1 | S1 crashes | down | foll t3 | foll t3 | foll t3 | foll t3 |
| 2 | S3's timeout fires first; it campaigns | down | ? | ? | ? | ? |
| 3 | S3 sends RequestVote(term=4) to all | down | ? | ? | ? | ? |
| 4 | S2, S4, S5 grant votes (logs equal) | down | ? | ? | ? | ? |
| 5 | S3 has 4 votes (incl. self) = majority | down | ? | ? | ? | ? |
| 6 | S3 sends heartbeats | down | ? | ? | ? | ? |

**Questions to answer in prose:**

1. In step 3, what `lastLogIndex` and `lastLogTerm` did S3 include in its RequestVote, and why do they matter?
2. In step 4, the other servers granted their votes. Under what condition would a server have *refused* (the election restriction)?
3. How many votes does S3 need to win, and why is that number a *majority* and not "all"?
4. When S1 eventually restarts (still thinking it's leader of term 3), what happens on the first heartbeat it receives from S3 (term 4)?

---

## Part B — Trace a log-replication round (on paper)

S3 is now leader in term 4. A client sends command `d`.

| Step | Event | S3 (leader) | S2 | S4 | S5 |
|---|---|---|---|---|---|
| 1 | client sends `d` to S3 | append [4:d] @ idx4 | — | — | — |
| 2 | S3 sends AppendEntries(prevIdx=3, prevTerm=3, entries=[4:d]) | — | ? | ? | ? |
| 3 | followers check prevIdx=3/prevTerm=3 matches | — | ? | ? | ? |
| 4 | followers append [4:d], reply success | — | ? | ? | ? |
| 5 | S3 sees [4:d] on a majority | commit idx4 | — | — | — |
| 6 | S3 applies `d`, returns to client; next AppendEntries carries leaderCommit=4 | — | apply `d` | apply `d` | apply `d` |

**Questions:**

5. In step 5, exactly how many servers (including S3) must have `[4:d]` before S3 commits it?
6. The commit rule says an entry is committed when it's on a majority **and** the leader has an entry from its current term. Is `[4:d]` (term 4, S3's current term) enough on its own? Why does this clause matter for entries from *earlier* terms?
7. Suppose S2 had a divergent entry `[3:x]` at index 3 instead of `[3:c]`. Walk through how the AppendEntries consistency check (prevIdx/prevTerm) would catch it and what S3 would do.

---

## Part C — Verify against the visualization

Open <https://raft.github.io/>. Using the simulator:

1. Let a leader get elected. Note the term and the leader.
2. **Stop the leader** (click it, "stop"). Watch a follower time out and campaign. Confirm: the term increments, a new leader emerges with a majority of votes.
3. **Resume the old leader.** Confirm it discovers the higher term and steps down to follower — exactly your Part A step.
4. Send a few client requests to the new leader. Watch entries replicate and commit (the simulator marks committed entries). Confirm the majority rule.
5. **Partition the leader** into a minority. Watch the majority side elect a new leader and keep committing, while the minority leader *cannot* commit (no majority). Heal and watch the stale leader's uncommitted entries get overwritten.

Record three observations where the visualization matched your paper trace and one where it surprised you.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] Part A's table is fully filled, with S3 ending as leader in term 4 and all others followers in term 4.
- [ ] You correctly answered why S3 needs 3 votes (majority of 5), not 5.
- [ ] You correctly described S1 stepping down on seeing term 4 (a higher term always wins).
- [ ] Part B's table is filled, with `[4:d]` committed once on a majority (3 of 5).
- [ ] You answered why a *previous-term* entry on a majority is not automatically committed (the Figure-8 subtlety).
- [ ] Part C: you ran the visualization through an election, a stale-leader step-down, a commit, and a partition, and recorded observations.
- [ ] Committed to your Week 2 repo under `exercises/exercise-01/`.

---

## Stretch

- In the simulator, create a **split vote** (stop the leader and quickly make two followers time out together). Watch the term increment without a leader emerging, then a fresh round resolve it. This is FLP's split-vote stall being defeated by randomized timeouts.
- Trace, on paper, the **Figure 8** scenario from the Raft paper (§5.4.2): a previous-term entry on a majority that gets *overwritten* because it was never committed via a current-term entry. This is the deepest safety subtlety in Raft; if you can explain it, you understand the commit rule.
- Change the simulator's network speed / message loss and observe how it affects election frequency. Relate it to Lecture 2 §3.3b (election timeout tuning).

When this feels comfortable, move to [Exercise 2 — Lamport and vector clocks](exercise-02-vector-clocks.py).
