# Week 23 — Resources

Every resource here is **free** and **open**. Pact is an open-source project (the spec, the broker, and the language libraries are all OSS); the four property-testing libraries are open-source; the queueing-theory references are either freely published papers or chapters of books you already own from earlier weeks (DDIA, the SRE workbook). No paywalled material is required.

A version note: Pact's spec is versioned (v2, v3, v4), and the broker and `can-i-deploy` semantics are stable across recent releases. Target the **Pact v3/v4 message and broker model** and a current **PactFlow/pact-broker** for the broker. The property-testing libraries move slowly and the *concepts* (generator, invariant, shrinker) are identical across all four — only the API surface differs.

## Required reading (work it into your week)

- **Pact — Introduction & "How Pact works"** — consumer-driven contracts, the pact file, the verification flow. Read it Monday:
  <https://docs.pact.io/>
- **Pact — The Pact Broker** — publishing pacts, verification results, tagging, and `can-i-deploy`:
  <https://docs.pact.io/pact_broker>
- **Pact — `can-i-deploy`** — the gate that refuses a breaking deploy:
  <https://docs.pact.io/pact_broker/can_i_deploy>
- **Hypothesis — "What you can generate and how"** — strategies, `@given`, shrinking. The canonical property-testing tutorial:
  <https://hypothesis.readthedocs.io/en/latest/>
- **The Universal Scalability Law (Gunther)** — the contention + coherency model; the short form is in the USL primer:
  <https://www.vanguardsw.com/wp-content/uploads/2014/06/Universal-Scalability-Law.pdf>

## Contract testing (Pact)

- **Pact — Consumer tests** — writing the consumer expectation against the mock provider:
  <https://docs.pact.io/getting_started/how_pact_works>
- **Pact — Provider verification** — replaying the pact file against the real provider, provider states:
  <https://docs.pact.io/getting_started/verifying_pacts>
- **Pact — provider states** — the `given(...)` precondition setup that makes verification deterministic:
  <https://docs.pact.io/getting_started/provider_states>
- **pact-python** — the Python consumer/provider library (for `order`/`search`):
  <https://github.com/pact-foundation/pact-python>
- **pact-go** — the Go library (for `inventory`/`payment`):
  <https://github.com/pact-foundation/pact-go>
- **Pact — gRPC/Protobuf plugin** — contract testing over gRPC, not just REST:
  <https://github.com/pactflow/pact-protobuf-plugin>
- **Pact — bi-directional contract testing** — verifying a provider's own contract against the consumer's pact (the stretch goal):
  <https://docs.pact.io/bi-directional_contract_testing>

## Property-based testing (four languages)

- **Hypothesis (Python)** — strategies, `@given`, `@example`, `RuleBasedStateMachine`:
  <https://hypothesis.readthedocs.io/>
- **fast-check (JS/TS)** — `fc.assert`, `fc.property`, arbitraries, model-based testing:
  <https://fast-check.dev/>
- **gopter (Go)** — generators, properties, the `gen` package, stateful testing:
  <https://github.com/leanovate/gopter>
- **proptest (Rust)** — strategies, `proptest!`, shrinking, the state-machine crate:
  <https://proptest-rs.github.io/proptest/intro.html>
- **"Property-Based Testing with PropEr, Erlang, and Elixir" (Hébert), concepts chapter** — the clearest free-to-read explanation of *what to test* (the hard part):
  <https://propertesting.com/> (the "Thinking in Properties" chapters are readable online)
- **John Hughes — "Testing the Hard Stuff and Staying Sane"** — the QuickCheck-finds-the-bug talk that started the discipline (free on YouTube/InfoQ).

## Capacity planning and queueing theory

- **Little's Law** — the relation L = λW and its derivation:
  <https://en.wikipedia.org/wiki/Little%27s_law> (then DDIA ch. 1 for the latency-percentile framing)
- **Designing Data-Intensive Applications (Kleppmann), Ch. 1** — percentiles, tail latency, and why the mean lies. (You own it from Week 1.)
- **The Google SRE Workbook — "Managing Load" / "Addressing Cascading Failures"** — the practitioner's queueing intuition, free online:
  <https://sre.google/workbook/managing-load/>
- **The M/M/c queue** — the multi-server queueing model behind a replica pool:
  <https://en.wikipedia.org/wiki/M/M/c_queue>
- **The Universal Scalability Law (Gunther)** — the model that explains why throughput bends back down:
  <https://www.vanguardsw.com/wp-content/uploads/2014/06/Universal-Scalability-Law.pdf>
- **Brendan Gregg — "The USE Method"** — Utilization, Saturation, Errors; how to *measure* the inputs to your capacity model:
  <https://www.brendangregg.com/usemethod.html>

## Tools you'll use this week

- **`pact` / `pact-broker`** — write consumer tests, run provider verification, publish to and query the broker. Run the broker locally via Docker (`pactfoundation/pact-broker`).
- **`pytest` + `hypothesis`** — the Python property tests (the CRDT-merge exercise) and the Python Pact consumer.
- **`cargo test` + `proptest`** — the Rust property tests against the real OR-set merge from Week 3/20.
- **`go test` + `gopter`** — the Go property tests and the `pact-go` provider verification.
- **`k6` / `fortio`** — generate the load that feeds real numbers into the USL fit (the capacity-model stretch).
- **Python (`numpy`/plain math)** — the capacity calculator: Little's Law, the M/M/c curve, the USL least-squares fit.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Consumer-driven contract** | A test where the *consumer* declares what it needs from a provider; the provider must satisfy it. |
| **Pact file** | The JSON artifact recording the agreed request/response interactions between a consumer and a provider. |
| **Provider verification** | Replaying the pact file against the *real* provider to confirm it still satisfies the consumer's expectations. |
| **Provider state** | A named precondition (`given("inventory has SKU-42 in stock")`) the provider sets up before verifying an interaction. |
| **Pact Broker** | The server that stores pacts and verification results and answers `can-i-deploy`. |
| **`can-i-deploy`** | The gate: "can I deploy this version without breaking a consumer that's already live in this environment?" |
| **Property-based test** | A test that generates many inputs and asserts an *invariant* holds for all of them, rather than checking one example. |
| **Generator (strategy/arbitrary)** | The thing that produces random inputs of the right shape for a property test. |
| **Invariant / property** | The law that must hold for *all* inputs (e.g., `merge(a,b) == merge(b,a)`). |
| **Shrinking** | The framework's automatic reduction of a failing input to the smallest input that still fails. |
| **Commutativity** | `f(a,b) == f(b,a)` — order doesn't matter. A required CRDT-merge law. |
| **Associativity** | `f(f(a,b),c) == f(a,f(b,c))` — grouping doesn't matter. A required CRDT-merge law. |
| **Idempotence** | `f(a,a) == a` — applying twice equals applying once. A required CRDT-merge law. |
| **Little's Law** | L = λW: average concurrency = arrival rate × average time in system. |
| **Utilization (ρ)** | The fraction of capacity in use, ρ = λ/(c·μ); latency explodes as ρ → 1. |
| **M/M/c queue** | A queueing model: Poisson arrivals, exponential service, `c` parallel servers (your replica pool). |
| **Universal Scalability Law (USL)** | Throughput as a function of concurrency with contention (α) and coherency (β) terms; predicts the ceiling. |

---

*If a link 404s, please open an issue so we can replace it.*
