# Week 2 — Exercises

Three drills that move from hand-tracing consensus to implementing logical clocks to fixing a real distributed-locking bug. Do them in order — exercise 3 reuses the fencing intuition that Lecture 2 §3 builds. The two Python files are standalone (`python3` them directly, standard library only).

## Index

1. **[Exercise 1 — Trace a Raft election](./exercise-01-trace-a-raft-election.md)** — by hand, trace a Raft cluster through a leader failure, an election, and a log-replication round; then check yourself against the official visualization. The drill that makes Raft real. (~60 min, written + interactive)
2. **[Exercise 2 — Lamport and vector clocks](./exercise-02-vector-clocks.py)** — implement both clocks, run them on a recorded message trace, and use the vector clock to *detect concurrency* that the Lamport timestamp hides. (~50 min, runnable)
3. **[Exercise 3 — Fencing tokens](./exercise-03-fencing-tokens.py)** — reproduce the lease-without-fencing data-corruption bug (a GC-paused client writing after its lease expired), then fix it with a monotonic fencing token the storage checks. (~50 min, runnable)

## How to work the exercises

- **Do Exercise 1 on paper first.** Trace the election before you open the visualization. The point is to predict, then verify — not to watch an animation and nod.
- For the Python files: `python3 exercise-02-vector-clocks.py`. Python 3.12+ assumed, standard library only — nothing to `pip install`.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match the shape, you're not done.
- When a result surprises you, walk it back to the lecture: which guarantee (clock condition, election restriction, fencing rule) is in play? Name it before you touch code.

## Running the Python exercises

```bash
python3 exercise-02-vector-clocks.py
python3 exercise-03-fencing-tokens.py
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-02` to compare.
