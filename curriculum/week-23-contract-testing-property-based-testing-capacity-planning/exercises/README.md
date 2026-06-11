# Week 23 — Exercises

Three focused drills, one per discipline. Each takes 45–90 minutes. Do them in order — exercise 1 (Pact) locks a boundary, exercise 2 (property tests) proves the CRDT that boundary carries, and exercise 3 (capacity) sizes the service behind it. Run them against your **capstone services** (the Python `order`/`search`, the Go `inventory`/`payment`, the Rust `cart`) where you can; each exercise names a self-contained fallback so you can do the drill even if a service isn't ready yet.

## Index

1. **[Exercise 1 — Pact consumer and provider verification](exercise-01-pact-consumer-and-provider.md)** — write a consumer-driven contract for `order` (Python) calling `inventory` (Go), generate the pact, verify it against the real provider with a provider state, publish to a local broker, and run `can-i-deploy`. Then break the provider and watch `can-i-deploy` block the deploy. (~75 min, guided)
2. **[Exercise 2 — Property tests for the CRDT merge](exercise-02-property-tests-crdt-merge.py)** — Hypothesis property tests proving the OR-set merge is commutative, associative, and idempotent. The file ships with a *correct* merge and a *planted-bug* merge; your job is to run the properties, watch the bug's shrunk counterexample, and explain the convergence failure it represents. (~60 min, runnable)
3. **[Exercise 3 — The capacity model](exercise-03-capacity-model.py)** — a runnable calculator: feed it the arrival rate and service time, and it computes the Little's-Law concurrency, the M/M/c utilization-latency curve, the replica count at a target utilization, the single-failure headroom, and a USL fit against sample load data. Its output *is* your capacity memo's numbers. (~60 min, runnable)

## How to work the exercises

- For **Exercise 1**, have **Docker** (to run the broker: `pactfoundation/pact-broker`), **Python 3.11+** with `pact-python`, and a **Go 1.22+** toolchain with `pact-go`. If your real `inventory` isn't ready, the exercise's fallback is a 30-line Go HTTP stub you stand up — the contract flow is identical.
- For **Exercise 2 and 3**, have **Python 3.11+** with `pytest`, `hypothesis`, and (for the USL fit) `numpy`. `pip install pytest hypothesis numpy`. Exercise 2 runs against the OR-set in the file; for the *real* merge from your Rust `cart`, the stretch points you at translating the same three properties into `proptest`.
- **Read the shrunk counterexample, don't skim it.** When a property fails, the `Falsifying example:` block is the whole point — it's the minimal input that breaks the law. Train the habit of reading it as a bug report, because that's exactly what it is.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match, you're not done.

## Running the exercises

The `.py` exercises run directly:

```bash
pip install pytest hypothesis numpy
pytest exercises/exercise-02-property-tests-crdt-merge.py -q       # property tests
python3 exercises/exercise-03-capacity-model.py --rps 800 --service-ms 5 --target-util 0.65
```

The Pact exercise is guided markdown — you run a broker, a consumer test, and a provider verification across two languages, with every command given.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-23` to compare.
