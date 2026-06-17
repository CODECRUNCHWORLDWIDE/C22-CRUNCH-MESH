# Week 6 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 7. Answer key is at the bottom — don't peek.

---

**Q1.** Twelve-factor says config that varies between deploys lives in the environment. What's the operational payoff?

- A) Smaller images.
- B) One image runs in every environment, configured differently — so "tested in staging" means something, because it's the *same artifact* as production.
- C) Faster startup.
- D) Logs are structured automatically.

---

**Q2.** Why does twelve-factor say a service should write logs to stdout and not manage log files?

- A) stdout is faster than files.
- B) The app shouldn't know or care where logs go; the platform captures stdout and routes it, so you can change the log backend without touching any service.
- C) Files are not allowed in containers.
- D) stdout encrypts logs.

---

**Q3.** What does a **liveness** probe answer, and what does Kubernetes do when it fails?

- A) "Can I serve traffic?"; Kubernetes removes the pod from the Service.
- B) "Is the process wedged?"; Kubernetes restarts the container.
- C) "Is a dependency up?"; Kubernetes scales the deployment.
- D) "Has the process started?"; Kubernetes delays traffic.

---

**Q4.** What does a **readiness** probe answer, and what does Kubernetes do when it fails?

- A) "Is the process wedged?"; Kubernetes restarts the container.
- B) "Can I serve traffic right now?"; Kubernetes removes the pod from the Service's endpoints (but does NOT restart it).
- C) "Is the node healthy?"; Kubernetes drains the node.
- D) "Is the image current?"; Kubernetes redeploys.

---

**Q5.** A team makes `cart`'s readiness probe check that it can reach `catalog`. `catalog` has a 10-second blip. What happens, and what's the rule?

- A) Nothing; this is good practice.
- B) Every `cart` replica goes unready simultaneously → total `cart` outage from a transient dependency blip. The rule: readiness checks *self only*; handle dependency failures in the request path.
- C) Only one `cart` replica restarts.
- D) `catalog` is automatically scaled up.

---

**Q6.** On `SIGTERM`, what is the correct ordering of a graceful shutdown for a service with in-flight requests and a DB?

- A) Close the DB, then drain requests, then exit.
- B) Flip health/readiness to not-ready, drain in-flight requests, close the DB, then exit — bounded under the grace period.
- C) `os.Exit(0)` immediately.
- D) Sleep 30 seconds, then exit.

---

**Q7.** Why does a `preStop` hook with a short sleep exist?

- A) To slow deploys deliberately.
- B) To dodge the readiness-removal race: endpoint removal is asynchronous and may not finish before `SIGTERM`, so the sleep gives Kubernetes time to stop routing new traffic before the process starts shutting down.
- C) To warm up the cache.
- D) To rotate logs.

---

**Q8.** What is the correct configuration precedence, lowest to highest priority?

- A) Flags → env → file → defaults.
- B) Defaults → config file → environment → command-line flags.
- C) Environment → defaults → flags → file.
- D) File → defaults → env → flags.

---

**Q9.** In OpenTelemetry, what makes `cart`'s span and `catalog`'s span part of *one* trace?

- A) They share a database.
- B) Context propagation: `cart` injects a W3C `traceparent` into the gRPC metadata; `catalog` extracts it and makes its spans children. You must set a global propagator or the spans won't stitch.
- C) They run on the same node.
- D) Nothing; cross-service traces are impossible.

---

**Q10.** What do RED metrics measure?

- A) Reads, Edits, Deletes.
- B) Rate (requests/sec), Errors (failures), Duration (latency distribution) — the default service dashboard.
- C) Replicas, Endpoints, Deployments.
- D) Requests, Egress, Disk.

---

**Q11.** Why must a Deployment set both resource *requests* and *limits*?

- A) They're the same thing.
- B) Requests tell the scheduler how much to reserve (so the pod lands somewhere with room); limits cap usage (CPU → throttle, memory → OOMKill) so a leak's blast radius is one pod, not the node.
- C) Only requests matter; limits are cosmetic.
- D) Limits are for billing only.

---

**Q12.** Where should a long-lived database password live in production, and where must it never live?

- A) In the source code; never in an env var.
- B) In a Kubernetes Secret (referenced by the Deployment); never baked into the image, committed in plaintext, or written to logs.
- C) In the container image; never in a Secret.
- D) In a public config file; never in source control.

---

**Q13.** What is the test of a good runbook playbook?

- A) It's long and thorough.
- B) It contains executable commands a person who didn't write the service can run — *symptom → diagnosis → mitigation → verify → escalate* — not vague instructions like "investigate the issue."
- C) It's written by the most senior engineer.
- D) It links to the source code.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — One image everywhere; "tested in staging" is meaningful because it's the same artifact. (Lecture 1 §1.1.)
2. **B** — Decouple production from routing; swap the backend without touching services. (Lecture 1 §1.2.)
3. **B** — Liveness = "wedged?"; fail → restart. (Lecture 1 §3.1.)
4. **B** — Readiness = "serve now?"; fail → removed from endpoints, NOT restarted. (Lecture 1 §3.1.)
5. **B** — The conflation outage: dependency-checking readiness takes down all replicas at once. Readiness = self only; handle deps in the request path. (Lecture 1 §3.2.)
6. **B** — Flip health → drain → close DB → exit, bounded. Closing the DB first would fail the requests you're draining. (Lecture 1 §4.3.)
7. **B** — Dodges the readiness-removal race (async endpoint removal vs SIGTERM). (Lecture 1 §4.2.)
8. **B** — Defaults → file → env → flags; general to specific. (Lecture 1 §5.)
9. **B** — Context propagation via the W3C `traceparent`; set the global propagator or spans don't stitch. (Lecture 2 §1.3.)
10. **B** — Rate, Errors, Duration. (Lecture 2 §1.4.)
11. **B** — Requests for scheduling, limits to cap blast radius (throttle/OOMKill). (Lecture 2 §2.2.)
12. **B** — A Kubernetes Secret; never baked/committed/logged. (Lecture 2 §3.)
13. **B** — Executable commands runnable by a non-author; symptom→diagnosis→mitigation→verify→escalate. (Lecture 2 §4.2.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./06-homework.md).
