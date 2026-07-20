# Week 23 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 24. Answer key is at the bottom — don't peek.

---

**Q1.** In consumer-driven contract testing, who authors the contract, and why?

- A) The provider, because the provider owns the API.
- B) The consumer, because the consumer knows exactly what it depends on; the contract becomes an artifact the provider's CI must honor.
- C) A central platform team, to keep both sides honest.
- D) Nobody authors it; Pact infers it from traffic.

---

**Q2.** What is the artifact in the middle of the Pact flow, and what's notable about it?

- A) A shared library both services import.
- B) The pact file — a language-neutral JSON description of the agreed interactions, containing neither side's code, which is why it works across a polyglot system.
- C) A running mock server that stays up in production.
- D) The provider's OpenAPI spec.

---

**Q3.** What does `can-i-deploy` actually do?

- A) Runs the consumer's tests one more time.
- B) Asks the broker whether deploying a given service version would break any consumer already live in the target environment, and returns non-zero (blocking the deploy) if it would.
- C) Deploys the service if the tests pass.
- D) Checks whether the Kubernetes cluster has capacity.

---

**Q4.** What is a Pact "provider state" for?

- A) Storing the provider's deployment status.
- B) A named precondition the provider sets up (seeds data, sets a fixture) before verifying an interaction, so verification is deterministic and the consumer's assumptions about provider *state* are documented.
- C) The provider's health-check endpoint.
- D) A cache of verification results.

---

**Q5.** Which of these does a contract test NOT prove?

- A) That the agreed request/response shapes match.
- B) That the named interactions hold under their declared preconditions.
- C) That the provider's business logic is *correct* (e.g., that the stock count returned is the *right* number) and that idempotency holds under duplicate delivery.
- D) That the consumer parses the response correctly.

---

**Q6.** What are the three pieces of a property-based test?

- A) Setup, exercise, assert.
- B) A generator (produces random inputs), an invariant (the law that must hold for all of them), and a shrinker (reduces a failure to its minimal counterexample).
- C) A mock, a stub, and a spy.
- D) Given, when, then.

---

**Q7.** Why is the shrinker the part that makes property testing usable for correctness?

- A) It makes tests run faster.
- B) When a property fails, it automatically reduces the failing input to the smallest input that still fails — handing you a readable bug report instead of a giant random blob.
- C) It shrinks the test file.
- D) It reduces memory usage during the run.

---

**Q8.** Which three algebraic laws must a state-based CRDT's merge satisfy, and why do they matter?

- A) Reflexivity, symmetry, transitivity — they make it an equivalence.
- B) Commutativity, associativity, idempotence — together they *are* the convergence guarantee: replicas that see updates in any order, batching, or with re-delivery all converge to the same state.
- C) Linearity, continuity, monotonicity — they make it differentiable.
- D) Atomicity, consistency, durability — the ACID properties.

---

**Q9.** A buggy CRDT merge passes the idempotence property but fails commutativity. What does that tell you?

- A) The bug is harmless because two of three laws pass.
- B) The merge is order-dependent, so replicas that saw the same updates in different orders will diverge permanently — a split brain. It also shows why you test all three laws: any one can survive a bug the others catch.
- C) Idempotence is the only law that matters.
- D) The test framework is misconfigured.

---

**Q10.** State Little's Law and one of its readings.

- A) E = mc²; energy equals mass times the speed of light squared.
- B) L = λW: average concurrency = arrival rate × average time in system. Reading: at λ=500 rps and W=20ms, L = 10 requests in flight on average, so your pool must hold ≥10.
- C) ρ = λ/μ; utilization equals arrival over service rate.
- D) X = N / (1 + α(N−1)); throughput under contention.

---

**Q11.** Why does latency explode rather than degrade gracefully as utilization approaches 1?

- A) Because CPUs throttle at high temperature.
- B) Because in an M/M/c queue the response time carries a 1/(1−ρ) factor — at ρ=0.9 it's 10×, at ρ=0.99 it's 100× — so latency goes vertical near saturation. That's why you target 0.6–0.7, keeping headroom to absorb bursts.
- C) Because the network MTU is exceeded.
- D) It doesn't; latency grows linearly with load.

---

**Q12.** In the Universal Scalability Law, what do the α and β terms represent, and what does β cause?

- A) α is amplitude, β is bandwidth; both increase throughput.
- B) α is contention (serialization — caps the curve to a ceiling); β is coherency (coordination cost, growing as N(N−1)) — β makes the throughput curve *peak and then bend back down*, so past a point adding workers reduces total throughput.
- C) α and β are both error terms with no physical meaning.
- D) α is the alpha release, β is the beta release.

---

**Q13.** Your capacity model says order-service needs 7 replicas to hold ρ ≤ 0.65 at peak. A reviewer asks "why not run at 0.9 to save money?" What's the defensible answer?

- A) "0.65 is the industry standard."
- B) "At 0.9 the queueing factor is 10× and a single traffic burst or one replica loss pushes us over the latency cliff into an SLO breach; the headroom between 0.65 and 1.0 is what absorbs variance, and the extra replicas cost less than a latency incident."
- C) "Because the autoscaler defaults to 0.65."
- D) "We can't change it; it's hard-coded."

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Consumer-driven: the consumer knows its needs and makes them an artifact the provider's CI honors. (Lecture 1 §2.)
2. **B** — The pact file: language-neutral JSON, no code from either side, which is why it crosses the polyglot boundary as data. (Lecture 1 §2.2.)
3. **B** — `can-i-deploy` checks the cross-service verification matrix and blocks (non-zero) a deploy that would break a live consumer. (Lecture 1 §4.2.)
4. **B** — A named precondition the provider sets up so verification is deterministic and the consumer's state assumptions are documented. (Lecture 1 §3.)
5. **C** — Contract tests prove shape and named interactions; they do NOT prove business correctness or idempotency-under-duplication. (Lecture 1 §6; Challenge 1.)
6. **B** — Generator, invariant, shrinker. (Lecture 2 §1.1.)
7. **B** — It reduces a failure to the minimal counterexample, turning a random blob into a readable bug report. (Lecture 2 §1.1.)
8. **B** — Commutativity, associativity, idempotence: together they are the convergence guarantee. (Lecture 2 §1.4.)
9. **B** — Order-dependent merge → permanent divergence; and it's why you test all three laws (one can pass while another fails). (Lecture 2 §1.4; Exercise 2.)
10. **B** — L = λW; e.g., 500 rps × 20 ms = 10 in flight. (Lecture 2 §2.1.)
11. **B** — The 1/(1−ρ) blow-up; vertical near saturation; target 0.6–0.7 for burst headroom. (Lecture 2 §2.2.)
12. **B** — α contention (ceiling), β coherency (quadratic coordination cost that bends the curve down). (Lecture 2 §2.3.)
13. **B** — The queueing cliff + single-failure headroom + cost-of-incident-vs-replicas argument. (Lecture 2 §2.2, §2.4.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md) and the mock interview.
