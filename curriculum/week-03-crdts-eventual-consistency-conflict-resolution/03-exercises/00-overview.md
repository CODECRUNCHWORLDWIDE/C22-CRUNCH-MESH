# Week 3 — Exercises

Three drills that move from "which CRDT" reasoning to implementing the zoo to property-testing the semilattice laws. Do them in order — exercise 3 verifies the very laws exercise 2 relies on. The Python file is standalone; the Go file uses only the standard library's `testing`.

## Index

1. **[Exercise 1 — Classify the CRDTs](./exercise-01-classify-crdts.md)** — for each of six data-modeling problems, pick the right CRDT (or say "this needs consensus, not a CRDT") and justify it against the Lecture 1 §5 boundary. The reasoning drill that makes the code land. (~60 min, written)
2. **[Exercise 2 — The CRDT zoo](./exercise-02-crdt-zoo.py)** — implement G-counter, PN-counter, OR-set, and LWW-register; then prove convergence by merging three replicas in a *reordered, duplicated* sequence and asserting they all reach the same value with no data lost. (~50 min, runnable)
3. **[Exercise 3 — Semilattice properties](./exercise-03-semilattice-properties.go)** — property-test that a CRDT merge is commutative, associative, and idempotent, by generating random states and asserting the three laws. (~45 min, runnable)

## How to work the exercises

- **Do Exercise 1 first.** Choosing the right CRDT (or rejecting CRDTs for consensus) is the load-bearing skill; the code reifies it. If you skip it you'll implement a CRDT for a problem that needed coordination.
- For the Python file: `python3 exercise-02-crdt-zoo.py`. Python 3.12+ assumed, standard library only.
- For the Go file: `go test -run Properties` (it's written as Go tests). Go 1.22+, standard library only.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match the shape, you're not done.
- When a merge surprises you, walk it back to the lecture: is the merge a least upper bound? Are the three laws satisfied? Name the property before you touch code.

## Running the exercises

```bash
python3 exercise-02-crdt-zoo.py
go test -v ./...        # or: go test -run Properties exercise-03-semilattice-properties.go
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-03` to compare.
