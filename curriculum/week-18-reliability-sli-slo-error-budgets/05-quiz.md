# Week 18 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 19. Answer key is at the bottom — don't peek.

---

**Q1.** What is the shape of an SLI?

- A) The average latency of a service.
- B) A ratio of good events to valid events (e.g. non-5xx responses / all responses) over a window.
- C) The total number of requests.
- D) The uptime percentage promised in a contract.

---

**Q2.** Why can a badly-chosen SLI be worse than no SLI?

- A) It costs more to compute.
- B) It can be green while users suffer — e.g. a mesh-level availability SLI sees HTTP 200 as success, so a service returning 200 with a wrong/empty body scores 100% while every user is failing. You also need an app-level correctness SLI.
- C) It uses too many labels.
- D) It can't be queried in PromQL.

---

**Q3.** What is an error budget, and what's the key mental shift about it?

- A) The money you spend on reliability.
- B) (1 − SLO): the allowed unreliability — and the shift is to treat it as a *resource you spend deliberately* on velocity, risk, and chaos drills, not a line you must never cross.
- C) The number of alerts you're allowed.
- D) The time before the next deploy.

---

**Q4.** Your availability SLO is 99.9% over 28 days. Roughly how much downtime-equivalent budget is that, and what does "burn rate 14.4" mean?

- A) ~4 hours; burn rate is irrelevant.
- B) ~40 minutes of budget; burn rate 14.4 means you're spending the budget 14.4× faster than the rate that would exhaust it evenly over the window — at that rate you'd burn a 28-day budget in ~2 days.
- C) ~1 minute; burn rate means CPU usage.
- D) Zero; 99.9% means no failures allowed.

---

**Q5.** Why does multi-window multi-burn-rate alerting beat a static "error rate > 1%" threshold?

- A) It's simpler.
- B) A static threshold is both too noisy (a brief blip pages you) and too blind (a steady sub-threshold leak quietly drains the whole budget, never paging). Multi-window pages fast on a catastrophe (high burn over a short window) and tickets on a simmer (low burn over a long window), off the same budget.
- C) It uses fewer metrics.
- D) Static thresholds don't work in Prometheus.

---

**Q6.** Why does each burn-rate alert use BOTH a long window and a short window?

- A) Redundancy in case one fails.
- B) The long window gives precision (a real budget threat, not a blip); the short window gives responsiveness — it fires fast AND *clears fast* once the problem is fixed, so you're not paged for an hour after you've already resolved it. Requiring both gives a page that's neither a false alarm nor stuck.
- C) The short window is for CPU, the long for memory.
- D) Only the long window matters; the short is decorative.

---

**Q7.** Why is 100% the wrong reliability target?

- A) It's achievable but slow.
- B) Each additional nine costs exponentially more for a benefit users can't perceive, AND your reliability is capped by your weakest dependency anyway (a service on 99.9% dependencies can't be 99.99%). The error budget exists *because* some failure is acceptable and 100% is neither attainable nor worth it.
- C) 100% requires a paid license.
- D) It isn't wrong; always target 100%.

---

**Q8.** Why must retries use jitter, and what's a retry budget for?

- A) Jitter makes retries faster; a budget limits cost.
- B) Without jitter, all callers retry in lockstep — a synchronized thundering herd that re-kills a recovering dependency. Full jitter de-synchronizes them. A retry budget caps retries at a small fraction of traffic so retries recover isolated transients but can't amplify a widespread failure into a retry storm.
- C) Jitter encrypts the retry; the budget is for billing.
- D) Neither is necessary if you have a circuit breaker.

---

**Q9.** What does a circuit breaker prevent, and what are its three states?

- A) It prevents slow queries; states are fast/slow/medium.
- B) It prevents a failing dependency from cascading into the caller: closed (calls pass), open (fail fast — return immediately without calling the dead dependency, so it can recover and the caller doesn't pile up on timeouts), half-open (trickle probes to test recovery).
- C) It prevents all errors; states are on/off/standby.
- D) It's a load balancer with three backends.

---

**Q10.** What failure does a bulkhead prevent?

- A) Disk corruption.
- B) One dependency's problem exhausting ALL your resources: with a shared pool, a hung payment consumes every thread, so cart can't reach the *healthy* inventory/shipping either. Separate bounded pools per dependency compartmentalize the failure.
- C) A network partition.
- D) A bad deploy.

---

**Q11.** Why does an event-driven Kafka consumer scale better on lag (KEDA) than on CPU (HPA)?

- A) KEDA is newer.
- B) A consumer can be far behind (lag exploding) while its CPU is low (I/O-waiting or under-replicated) — CPU-based HPA wouldn't scale it up and the backlog would grow until retention drops messages. Lag directly measures "are we keeping up," which is what should drive scaling.
- C) CPU can't be measured for consumers.
- D) Lag is cheaper to compute than CPU.

---

**Q12.** What does Little's Law (L = λW) tell you, and how does it explain the overload spiral?

- A) It computes error rate.
- B) Average concurrency L = arrival rate λ × latency W. If latency W rises (a slow dependency) at fixed throughput, L rises — more requests pile up in flight, consuming memory/connections, which slows things further, raising W again: the unbounded-queue death spiral.
- C) It's a formula for SLO targets.
- D) It only applies to single-threaded systems.

---

**Q13.** What is coordinated omission, and why does it make a load test lie about the tail?

- A) It's when two services agree to drop requests.
- B) A naive loop-and-wait load tester, when the server stalls, *doesn't send* the requests it would have during the stall — so the stall is recorded as one slow sample instead of the thousands that would have queued. This systematically under-reports the tail; open-loop (fixed-rate) testing represents the queue that actually forms.
- C) It's a Prometheus bug.
- D) It only affects the mean, not the tail.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — good events / valid events over a window. The fundamental shape. (Lecture 1 §1.1.)
2. **B** — green-while-users-suffer; the mesh sees network success, not semantic correctness — you need an app-level correctness SLI too. (Lecture 1 §1.2.)
3. **B** — (1 − SLO), and the shift is to spend it deliberately as a resource. (Lecture 1 §2.1–2.2.)
4. **B** — ~40 min of budget over 28 days; burn rate 14.4 ≈ exhaust in ~2 days. (Lecture 1 §2.1, §3.1.)
5. **B** — static is both too noisy and too blind; multi-window pages on catastrophe, tickets on simmer. (Lecture 1 §3.2.)
6. **B** — long window = precision, short window = fast fire AND fast clear; both required. (Lecture 1 §3.3.)
7. **B** — exponential cost per nine + weakest-dependency cap; the budget exists because some failure is acceptable. (Lecture 1 §4.1.)
8. **B** — jitter de-synchronizes the herd; the budget caps retries so they can't amplify a widespread failure. (Lecture 2 §1.2.)
9. **B** — prevents cascade; closed/open(fail-fast)/half-open(probe). (Lecture 2 §1.3.)
10. **B** — prevents one dependency starving the others; separate bounded pools compartmentalize. (Lecture 2 §1.4.)
11. **B** — lag (not CPU) is the "are we keeping up" signal; a behind consumer can have low CPU. (Lecture 2 §2.2.)
12. **B** — L = λW; rising W at fixed λ raises in-flight L, the overload spiral. (Lecture 2 §3.1.)
13. **B** — loop-and-wait omits the requests that would queue during a stall, under-reporting the tail; open-loop fixes it. (Lecture 2 §3.4.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md).
