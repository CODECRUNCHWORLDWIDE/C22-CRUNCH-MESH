# Week 4 — Exercises

Three focused drills that take you from reading a domain to scoring a topology to detecting a smell in code. Each takes 30–60 minutes. Do them in order — exercise 3 reuses the topology format you build in exercise 2. The first is a paper-and-thinking exercise; the second and third are runnable tools you'll actually use on your own designs.

## Index

1. **[Exercise 1 — Draw the context map](./exercise-01-draw-the-context-map.md)** — read a monolith description and produce a context map with named contexts, owners, and DDD relationship patterns at every boundary. (~45 min, guided)
2. **[Exercise 2 — Score a topology against the heuristics](./exercise-02-decompose-the-monolith.py)** — a runnable Python analyzer that takes a proposed topology and scores it against the four decomposition heuristics, flagging entity-service and shared-database smells. (~50 min, runnable)
3. **[Exercise 3 — The distributed-monolith smell detector](./exercise-03-distributed-monolith-smell.go)** — a Go tool that detects synchronous-call-chain and shared-database smells in a topology spec and exits non-zero when it finds one. (~45 min, runnable)

## How to work the exercises

- Have **Go 1.23+** and **Python 3.12+** installed: `go version` and `python3 --version` both work.
- Exercise 1 produces a markdown artifact you'll reuse in the homework and the challenge. Do it carefully; it's not busywork.
- The runnable exercises (`.py`, `.go`) are standalone — no external dependencies, no network, no database. They read a topology described as data and reason about it. This is deliberate: a decomposition tool that needs a running cluster to tell you your boundaries are wrong is a tool you'll never run.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match, you're not done.
- When a topology "looks fine" but a tool flags it, trust the tool and re-read the relevant anti-pattern in Lecture 2. The whole point is that these smells are invisible to the naked eye until you've trained on them.

## Running the Python exercise

```bash
python3 exercise-02-decompose-the-monolith.py
```

No `pip install` required — it uses only the standard library.

## Running the Go exercise

```bash
go run exercise-03-distributed-monolith-smell.go
```

No `go get` required — standard library only.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-04` to compare.
