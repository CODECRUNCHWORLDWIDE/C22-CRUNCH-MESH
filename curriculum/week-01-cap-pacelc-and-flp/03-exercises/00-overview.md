# Week 1 — Exercises

Three focused drills that move from paper reasoning to running code. Do them in order — exercise 3 reuses the linearizability intuition you build in 1 and 2. The two Go files are standalone (`go run` them directly, no modules to fetch).

## Index

1. **[Exercise 1 — Classify the systems](./exercise-01-classify-the-systems.md)** — place ten real systems on the consistency lattice and the PACELC grid, with a one-sentence justification each. The reasoning drill that makes the rest of the week land. (~60 min, written)
2. **[Exercise 2 — The partitioned register](./exercise-02-partitioned-register.go)** — a two-node replicated register with a controllable network partition. Run it in **CP mode** (refuse writes on the minority to stay consistent) and **AP mode** (accept and diverge), and watch the CAP tradeoff happen in your terminal. (~50 min, runnable)
3. **[Exercise 3 — The linearizability checker](./exercise-03-linearizability-checker.go)** — a checker that takes a recorded history of register operations and decides whether it is linearizable, by searching for a valid sequential ordering. Turns the abstract definition into a yes/no algorithm. (~45 min, runnable)

## How to work the exercises

- **Do Exercise 1 first, on paper or in a markdown file.** The classification is the load-bearing skill; the code reifies it. If you skip to the code you'll write a register whose tradeoff you can't name.
- For the Go files: `go run exercise-02-partitioned-register.go`. Go 1.22+ is assumed. No third-party imports — everything is the standard library, so there is nothing to `go get`.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match the *shape*, you're not done. Exact counts vary with timing; the shape does not.
- When a register "isn't behaving," walk it back to the theorem: which property (availability or linearizability) did this mode promise, and which did it give up? Name it before you touch code.

## Running the Go exercises

```bash
# from this directory
go run exercise-02-partitioned-register.go
go run exercise-03-linearizability-checker.go

# run the register under the race detector to prove the partition sim has no data races
go run -race exercise-02-partitioned-register.go
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-01` to compare approaches.
