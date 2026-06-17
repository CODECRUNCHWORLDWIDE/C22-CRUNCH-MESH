# Challenge 1 — Pass the Production-Readiness Review

**Time estimate:** ~90 minutes.

## Problem statement

You are the on-call lead, and a teammate wants to ship a new service — `wishlist`, which lets customers save products for later — to production this Friday. It "works on their laptop." Your job is to run it through a **production-readiness review** before it goes anywhere near production: find every gap against the checklist, fix the blockers, and *prove* the service is now safe to deploy — culminating in the zero-dropped-requests-on-deploy demonstration that is this week's promise.

This mirrors the real skill: the author thinks "it works, ship it." The reviewer's job is to find the eight unglamorous things that will page someone at 3 a.m. — and to insist they're fixed before, not after, the incident.

## The un-hardened service

Here is `wishlist` as the author wrote it. Read it and find the gaps. It's a deliberate worst-case: it *runs*, and almost nothing about it is production-ready.

```go
// wishlist.go — the author's "it works" version. Find the gaps.
package main

import (
	"fmt"
	"net/http"
	"os"
)

var items = map[string][]string{} // in-memory state (!)

func main() {
	http.HandleFunc("/add", func(w http.ResponseWriter, r *http.Request) {
		user := r.URL.Query().Get("user")
		sku := r.URL.Query().Get("sku")
		items[user] = append(items[user], sku) // unsynchronized map write (!)
		fmt.Printf("added %s to %s's wishlist\n", sku, user) // string log to... where?
		w.Write([]byte("ok"))
	})

	http.HandleFunc("/list", func(w http.ResponseWriter, r *http.Request) {
		user := r.URL.Query().Get("user")
		fmt.Fprintf(w, "%v", items[user])
	})

	// Hard-coded port; hard-coded everything. No health checks. No shutdown.
	// Connects to a database with a password baked in the source:
	dbURL := "postgres://wishlist:hunter2@db:5432/wishlist" // secret in source (!)
	_ = dbURL
	fmt.Println("listening on :3000")
	http.ListenAndServe(":3000", nil) // ignores the error; no graceful shutdown
}
```

And the author's "deployment" (such as it is):

```yaml
# wishlist-deploy.yaml — the author's version. Find the gaps.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wishlist
spec:
  replicas: 1                       # single replica
  selector: { matchLabels: { app: wishlist } }
  template:
    metadata: { labels: { app: wishlist } }
    spec:
      containers:
        - name: wishlist
          image: wishlist:latest    # :latest tag
          # no resources, no probes, no securityContext, no preStop
```

## Part A — The review (find the gaps)

Produce a `challenge-01-review.md` that audits `wishlist` against the 15-item checklist from Exercise 1 Part B *and* the twelve factors. For each gap, state the *consequence* — what outage or incident it causes — not just "it's missing." Order the gaps by blast radius (BLOCKER → HIGH → MED).

You should find at least these (and ideally more):

- **State in memory** (the `items` map) — violates Factor VI; the service can't scale or survive a restart; data lost on every deploy. **BLOCKER.**
- **A data race** (unsynchronized map writes) — will crash under concurrency (`fatal error: concurrent map writes`). **BLOCKER.**
- **No graceful shutdown** — every deploy drops in-flight requests. **BLOCKER.**
- **No readiness/liveness probes** — Kubernetes can't tell if it's healthy; routes traffic to a dead pod. **BLOCKER.**
- **No resource limits** — a leak OOMs the node. **BLOCKER.**
- **A secret baked into source** (`hunter2`) — leaked the moment the repo is read; in image-layer history forever. **BLOCKER.**
- **String logs to stdout via `fmt.Println`** — not structured, not queryable, no trace correlation. **HIGH.**
- **`:latest` image tag** — non-reproducible deploys; you can't roll back to a known version. **HIGH.**
- **Single replica + no PDB** — any disruption is a total outage. **HIGH.**
- **No tracing/metrics** — blind in an incident. **HIGH.**
- **No `SecurityContext`** — runs as root. **MED.**
- **No runbook.** **MED.**

## Part B — Harden it (fix the blockers)

Fix every BLOCKER and every HIGH. Produce:

1. **`wishlist-hardened.go`** — the rewritten service with: structured `slog` JSON logs; state moved to a backing store (a real Postgres, or for the challenge a thread-safe in-memory store *with a clear comment that production uses Postgres*); a fixed data race (mutex or the store's own locking); separate `/healthz` and `/readyz`; correct `SIGTERM` graceful shutdown (flip readiness → drain → close); config from the environment; the DB URL from an env var, never logged.
2. **`wishlist-hardened.yaml`** — the rewritten Deployment with: a pinned image tag (not `:latest`); resource requests *and* limits; all three probes (readiness/liveness check self only!); a non-root `SecurityContext`; `terminationGracePeriodSeconds` + a `preStop` sleep; 3 replicas; a `PodDisruptionBudget`; the DB credential from a `Secret`.

Use Exercise 2 (the Go service) and Exercise 3 (the Deployment) as your templates — this challenge is applying them to a new service under review pressure.

## Part C — Prove it (the zero-drop deploy)

This is the deliverable that proves you didn't just check boxes. Deploy the hardened `wishlist` to Kind, drive steady traffic at it with `k6` or `hey`, trigger a **rolling restart mid-flight**, and **show zero failed requests.**

```bash
# Terminal 1: steady load (e.g. hey, 60s, 20 concurrent)
hey -z 60s -c 20 http://wishlist.local/list
# Terminal 2, ~20s in: roll the deployment
kubectl rollout restart deployment/wishlist
# Result: hey's summary shows 0 non-2xx responses. Zero drops.
```

Capture the load generator's summary (showing 0 errors) and the `kubectl get pods` output during the roll (showing old pods Terminating while new pods are Ready first). That's the proof.

## Acceptance criteria

- [ ] `challenge-01-review.md` audits `wishlist` against the checklist and twelve factors, with the *consequence* of each gap, ordered by blast radius; all six BLOCKERs identified.
- [ ] `wishlist-hardened.go` fixes every BLOCKER: structured logs, no in-memory state (or a clearly-marked thread-safe store), no data race, health endpoints, graceful shutdown, config from env, secret from env.
- [ ] `wishlist-hardened.yaml` fixes every deployment gap: pinned tag, requests+limits, three probes (self-only), non-root SecurityContext, grace period + preStop, 3 replicas, PDB, Secret.
- [ ] **Part C:** a load-generator summary showing **0 failed requests** across a rolling restart under load, plus the `kubectl get pods` evidence of the safe roll.
- [ ] You can state, in one sentence each, why the in-memory state and the dependency-checking readiness probe (if the author had added one) are the two most dangerous patterns.
- [ ] Committed to your Week 6 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The seductive over-correction in Part B is to make the **readiness probe check the database** — "don't serve if the DB is down." This is the conflation outage from Lecture 1 §3.2, and it's *worse* than no probe: a brief DB blip makes *all* `wishlist` replicas unready *simultaneously*, turning a transient dependency hiccup into a total `wishlist` outage, and then a thundering herd when the DB recovers. Readiness checks **self only**. A DB outage is handled in the *request path* (return a typed error, degrade) — never by yanking yourself out of rotation. If your hardened readiness probe pings Postgres, you fell in the trap; fix it to check only "is my server up and initialized."

A second, subtler trap: "fixing" graceful shutdown by adding a long `sleep` before `os.Exit`. That doesn't *drain* anything — it just delays the drop. Real graceful shutdown flips readiness first, then *waits for in-flight requests to actually finish* (a WaitGroup or `http.Server.Shutdown`), then exits. A sleep is not a drain.

## Stretch

- Add **OpenTelemetry tracing** to the hardened service and show a trace of an `/add` request. If you wire it through a middleware/interceptor, it's the exact pattern that scales to the whole capstone.
- Run a **chaos micro-drill**: under load, `kubectl delete pod` one `wishlist` replica and confirm zero errors (traffic reroutes to the other two). This is a five-minute preview of the Week 22 gameday, and it proves your replica count + PDB + readiness are all correct together.
- Write the **`wishlist` runbook** (the mini-project deliverable, applied here): five named failure modes with executable playbooks. Then have a teammate try to execute one *without your help* — if they can't, the playbook isn't executable yet.

## Why this matters

In Week 12 you defend that your `cart` system is production-ready at the Phase 1 architecture review. The reviewer will not ask you to recite the twelve factors — they'll point at your running service and ask "what happens to in-flight requests when you deploy this, and prove it." This challenge *is* that conversation, rehearsed on a service you didn't write. Every team eventually has a Friday where someone wants to ship something that "works on their laptop," and the engineer who can run the five-minute readiness review — and insist on the zero-drop proof — is the one who keeps the team's weekends free.
