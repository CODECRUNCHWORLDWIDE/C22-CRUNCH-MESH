# Week 7 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 8. Answer key is at the bottom — don't peek.

---

**Q1.** What is the difference between north-south and east-west traffic, and which component owns each?

- A) North-south is internal service-to-service; a mesh owns it. East-west is the edge; a gateway owns it.
- B) North-south is the edge (outside world ↔ services); a gateway owns it. East-west is internal service-to-service; a mesh owns it.
- C) They're the same thing; the names are interchangeable.
- D) North-south is HTTP; east-west is gRPC.

---

**Q2.** You configure an Envoy cluster for a gRPC backend but omit `http2_protocol_options`. What happens?

- A) Nothing — Envoy detects gRPC automatically and uses HTTP/2.
- B) Envoy speaks HTTP/1.1 upstream and the gRPC calls fail, because gRPC requires HTTP/2 framing the cluster isn't offering.
- C) The cluster won't load; Envoy refuses to start.
- D) gRPC works but at half throughput.

---

**Q3.** What are Envoy's four "nouns," and which discovery service delivers the high-churn one (pods coming and going)?

- A) Listeners, routes, clusters, endpoints; EDS delivers endpoints (the high-churn one).
- B) Filters, chains, hosts, ports; LDS delivers ports.
- C) Gateways, meshes, sidecars, proxies; CDS delivers sidecars.
- D) Listeners, filters, clusters, services; RDS delivers services.

---

**Q4.** Why does Envoy use ADS (one aggregated stream) instead of four separate xDS streams in production?

- A) ADS is faster on the wire.
- B) ADS lets the control plane order updates (send a cluster before the route that references it), so the data plane is never inconsistent — make-before-break.
- C) Four streams aren't supported anymore.
- D) ADS encrypts the config and separate streams don't.

---

**Q5.** In Envoy's threading model, where does request processing happen, and what is the consequence for config updates?

- A) On the main thread; config updates block all requests until applied.
- B) On worker threads, each owning its connections; config is posted to each worker's thread-local state and applied per-worker — so updates are eventually consistent and never block live requests.
- C) On a thread pool shared with the control plane; updates require a restart.
- D) On the main thread, which is why Envoy is single-threaded and slow.

---

**Q6.** A backend hiccups and returns 5xx briefly. Your Envoy retry policy is `num_retries: 3` with no retry budget. What is the danger?

- A) None — retries always help.
- B) A retry storm: up to 4× traffic to a struggling backend, which can turn a brief hiccup into a sustained self-amplifying outage.
- C) The retries will be too slow to matter.
- D) Envoy will crash from too many retries.

---

**Q7.** What does a retry budget do, and what does a *climbing* `upstream_rq_retry_limit_exceeded` counter mean under stress?

- A) It caps retries as a fraction of active requests; a climbing `limit_exceeded` means the budget is *refusing* retries it would otherwise make — the storm-prevention working.
- B) It increases the number of retries; a climbing counter means more retries succeeded.
- C) It disables retries entirely; the counter should always be zero.
- D) It's a billing meter; the counter tracks cost.

---

**Q8.** What does outlier detection do, and why is `max_ejection_percent: 50` important?

- A) It actively probes hosts; 50% caps the probe rate.
- B) It passively ejects an endpoint that returns consecutive errors; `max_ejection_percent: 50` ensures that even in a total meltdown, no more than half the cluster is ejected — so you degrade rather than route to nothing.
- C) It load-balances; 50% sets the split.
- D) It's a circuit breaker; 50% is the trip threshold.

---

**Q9.** Why is a BFF a *separate* deployable per client class (mobile, web) rather than one shared API layer?

- A) Shared layers are faster.
- B) A shared layer accumulates every client's needs into one bloated surface — the distributed monolith reborn — and every client's change risks every other. A per-client BFF is owned by that client's team and tailored to its screens.
- C) Mobile and web can't share gRPC stubs.
- D) Separate deployables are required by Kubernetes.

---

**Q10.** A mobile BFF needs cart contents plus per-item stock. Which approach follows the BFF disciplines?

- A) The phone makes one call per item to inventory.
- B) The BFF loops and calls `GetStock` once per cart line.
- C) The BFF fans out to cart and inventory in parallel, fetches stock in one batched call, and degrades to showing the cart without live stock if inventory is down.
- D) The BFF embeds the pricing rules so it doesn't need to call cart.

---

**Q11.** Why can a browser not speak raw gRPC, and what are the two standard fixes?

- A) Browsers don't support TLS; the fixes are HTTP and HTTPS.
- B) The browser `fetch` API can't control HTTP/2 framing (trailers) that gRPC needs. Fixes: gRPC-Web (a proxy like Envoy transcodes) or Connect (a multi-protocol backend the browser can call directly).
- C) Browsers are too slow for gRPC; the fixes are caching and a CDN.
- D) gRPC is server-only; there is no browser fix.

---

**Q12.** When should you use a global rate-limit service (RLS) instead of a local (per-instance) rate limiter?

- A) Always — local limiting is deprecated.
- B) When you need a fleet-wide, contractual quota (e.g., "this customer gets 50 req/s across all replicas"), which a per-instance counter gets wrong the moment you scale out — at the cost of one network hop per decision.
- C) Never — global limiting is too slow for production.
- D) Only for north-south traffic.

---

**Q13.** Why is Envoy the answer to "why not Kong or Tyk?" in 2026, beyond feature comparison?

- A) Envoy is the only free option.
- B) Envoy is the data plane that most of the field — Istio, Envoy Gateway, and other meshes/gateways — is built on; learning Envoy teaches the substrate the others configure on your behalf.
- C) Kong and Tyk don't support TLS.
- D) Envoy is written in Go, which makes it faster.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — North-south is the edge (gateway's domain, asymmetric/untrusted client); east-west is internal (mesh's domain, symmetric/mutually-authenticated). (Lecture 1 §1.)
2. **B** — gRPC rides on HTTP/2; without `http2_protocol_options` Envoy speaks HTTP/1.1 upstream and gRPC fails. The most common first-day mistake. (Lecture 1 §2.1.)
3. **A** — Listeners (LDS), routes (RDS), clusters (CDS), endpoints (EDS). EDS is high-churn because pods come and go. (Lecture 1 §2.)
4. **B** — ADS is one ordered stream so the control plane can sequence updates (cluster before route), guaranteeing the data plane is never inconsistent — make-before-break. (Lecture 1 §2.2.)
5. **B** — Workers own their connections and run event loops; config is posted to per-worker thread-local state, applied per-worker on the next loop turn — eventually consistent, never blocking. (Lecture 1 §4.)
6. **B** — Uncapped retries amplify: `num_retries: 3` is up to 4× load to a struggling backend, the classic retry storm. (Lecture 2 §1.4; Challenge 1.)
7. **A** — The budget caps retries as a fraction of active load; a climbing `retry_limit_exceeded` under stress is the budget refusing retries — storm prevention working. (Lecture 2 §1.4.)
8. **B** — Passive ejection of a bad endpoint; `max_ejection_percent: 50` ensures a full meltdown leaves half the hosts in rotation, so you degrade instead of routing to nothing. (Lecture 2 §1.3.)
9. **B** — A shared layer becomes the distributed monolith; a per-client BFF is owned by the client team and tailored, so changes are isolated. (Lecture 2 §2.2.)
10. **C** — Parallel fan-out + batched stock lookup + graceful degradation is the BFF discipline. (Lecture 2 §2.3.)
11. **B** — `fetch` can't control HTTP/2 trailers gRPC needs; gRPC-Web (proxy transcodes) or Connect (multi-protocol backend, browser-direct) are the fixes. (Lecture 2 §3.1.)
12. **B** — Global RLS gives a fleet-wide quota correct under scale-out, at one network hop; local limiting drifts as you autoscale. (Lecture 2 §3.3.)
13. **B** — Envoy is the data plane the gateways and meshes are built on; learning it teaches the substrate. (Lecture 2 §4.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
