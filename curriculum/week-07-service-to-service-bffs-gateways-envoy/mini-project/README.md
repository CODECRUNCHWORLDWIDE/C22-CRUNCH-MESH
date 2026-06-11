# Mini-Project — `cart-edge`: A Production-Shaped Gateway

> Build the north-south edge for the cart system: an Envoy gateway in front of `cart` and `inventory`, a Go BFF that aggregates them for the mobile client, a global rate limiter that enforces per-customer quota across replicas, and an audit script that proves — from the admin endpoint — that every resilience policy you claimed is actually loaded and firing.

This is the artifact that turns "I configured an Envoy once" into "I own an edge." After this week, the edge is a *deployable* with a config you can defend line by line, resilience policies you can prove are active, and a BFF that does real aggregation — not a hand-wavy "and then there's a gateway" box on an architecture diagram.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-edge` becomes the north-south layer of your **capstone Polyglot Marketplace Backbone**. In Week 8, Istio takes over the *east-west* hops (mTLS, internal retries) and the gateway you build here stays the edge — the two compose. The capstone's progressive-delivery story (weighted canary, automatic rollback) plugs into the weighted-route primitive you set up here. Build it well now; you'll deploy it for real in Phase 4.

---

## What you will build

A repo `cart-edge` with four deliverables:

1. **`envoy/edge.yaml`** — the gateway config: one listener, routes by gRPC service path to the `cart` and `inventory` clusters, the full resilience stack (timeouts, retries+budget, outlier detection, circuit breakers), a local rate-limit filter for coarse protection, and a global rate-limit filter wired to an RLS for per-customer quota.
2. **`bff/`** — a Go BFF (extend Exercise 3) that the mobile route fans into: parallel fan-out, batched stock lookup, graceful degradation, plus a `/healthz` and basic OpenTelemetry spans so the BFF shows up in a trace.
3. **`ratelimit/`** — the global rate-limit service (`envoyproxy/ratelimit` + Redis) with a config that enforces a per-`x-customer-id` quota, proving two Envoy replicas share one budget.
4. **`audit/check_edge.sh`** — a script that hits the Envoy admin endpoint and *verifies the policies are real*: it asserts the `cart` cluster has a retry budget, outlier detection, and circuit breakers loaded, and that the rate-limit filters are in the chain. It exits non-zero if any expected policy is missing — so it gates a deploy.

By the end you have a public repo of Envoy YAML + ~300–450 lines of Go (BFF + audit helpers) that any future service can sit behind.

---

## Why a real edge and not just "an Ingress"

You could drop a stock Kubernetes `Ingress` in front of the services and call it done. Don't — not for a system you'll operate. A hand-owned Envoy edge gives you:

- **Resilience you can prove.** An `Ingress` annotation might set a timeout; it won't give you a retry budget, outlier detection, and circuit breakers you can read in `/config_dump` and assert on in CI. The audit script is the difference between "we have retries" and "here is the loaded retry budget."
- **A BFF seam.** The mobile route fans into a BFF; the web route can fan into a different one. An `Ingress` has no opinion about per-client aggregation; the whole point of the edge is to host it.
- **Quota that survives scale-out.** Per-instance limits drift as you autoscale. The global RLS gives you a fleet-wide, per-customer quota — the thing a real product needs and an annotation can't give you.

The Gateway API (and Envoy Gateway) will eventually generate config like this *for* you. Building it by hand first is what lets you read and trust what they generate. That's the senior-shop convention in 2026.

---

## Repo layout

```
cart-edge/
├── README.md
├── envoy/
│   └── edge.yaml              # the gateway config (source of truth for routing + resilience)
├── bff/
│   ├── go.mod
│   ├── main.go                # the mobile BFF (extends exercise 3)
│   └── screen.go              # the aggregation + composition logic
├── ratelimit/
│   ├── docker-compose.yaml    # ratelimit service + redis
│   └── config/edge.yaml       # the per-customer quota descriptors
├── audit/
│   └── check_edge.sh          # admin-endpoint assertions; exits non-zero on missing policy
└── deploy/
    └── kind/                  # Deployments + Services for cart, inventory, edge, bff
```

---

## Deliverable 1 — `envoy/edge.yaml` (the gateway)

This is the heart of the project. It must:

- Define **one listener** on `:10000` with an HCM and an HTTP filter chain in the correct order: CORS → gRPC-Web (so a browser can reach it) → local rate-limit → global rate-limit → router (last).
- **Route by gRPC service path**: `/cart.v1.` → `cart` cluster, `/inventory.v1.` → `inventory` cluster, and the mobile BFF's HTTP path (`/cart-screen`) → the `bff` cluster.
- Put the **full resilience stack** on the `cart` and `inventory` clusters: per-route `timeout`, a `retry_policy` with `previous_hosts` and `per_try_timeout`, a `retry_budget` (≤ 20%), `outlier_detection` (consecutive-5xx, `max_ejection_percent: 50`), and `circuit_breakers` (bounded connections/requests/pending/retries).
- Configure **both** rate-limit filters: a local token bucket for coarse per-instance protection AND a global RLS call keyed on `x-customer-id` for per-customer quota.
- Speak **HTTP/2 upstream** to the gRPC clusters (`http2_protocol_options`).

Use the configs from Exercises 1 and 2 as your starting point; the new work is wiring the BFF cluster, the two rate-limit filters, and the gRPC-Web/CORS pair for the browser.

> **The rule the audit enforces:** every cluster that fronts a real service MUST have a retry budget, outlier detection, and circuit breakers. A cluster with `num_retries` and no budget fails the audit. That's the project's reason to exist — resilience you can prove is loaded, not resilience you *think* you configured.

The routing table your edge should implement, for reference:

| Incoming path | Destination cluster | Notes |
|---|---|---|
| `/cart.v1.` | `cart` | gRPC; full resilience stack |
| `/inventory.v1.` | `inventory` | gRPC; full resilience stack |
| `/cart-screen` | `bff` | the mobile BFF's HTTP/JSON surface |
| `/grpc.health.` | `cart` or `inventory` | health checks through the proxy |

Document this table in your repo README so a reviewer can see, at a glance, what the edge routes where — and so the homework's edge-audit table has a target to compare the loaded config against.

---

## Deliverable 2 — `bff/` (the mobile BFF)

Extend Exercise 3 into a deployable:

- Same fan-out / batch / degrade discipline, now as a containerized service with a `Dockerfile` and a `/healthz`.
- Add **OpenTelemetry** spans (you instrumented services this way in Week 6): a parent span for `GetCartScreen`, child spans for the `cart` and `inventory` calls. When you trace a request through the edge in Phase 3, the BFF's fan-out must be visible.
- The BFF dials `cart` and `inventory` through their **cluster DNS** (in-cluster) — and you'll point it at the Istio mesh in Week 8 without changing a line, because the address is the same Service name.

---

## Deliverable 3 — `ratelimit/` (global quota)

Stand up the reference rate-limit service with Redis and a descriptor config that enforces a per-customer limit:

```yaml
# ratelimit/config/edge.yaml — the RLS descriptors for domain "edge".
domain: edge
descriptors:
  - key: customer_id
    rate_limit:
      unit: second
      requests_per_unit: 50      # each customer gets 50 req/s across the WHOLE fleet
```

Then prove the point that local limiting can't make: run **two** Envoy replicas, both pointing at the one RLS, and show that a single customer's 50 req/s budget is shared across both replicas — not 50 per replica. That fleet-wide correctness is the entire reason the global limiter earns its network hop.

---

## Deliverable 4 — `audit/check_edge.sh`

A script that makes the edge's claims *verifiable*. Against a running Envoy admin endpoint it must:

1. Fetch `/config_dump` and assert the `cart` and `inventory` clusters each have: a `retry_budget`, `outlier_detection`, and `circuit_breakers` with non-default thresholds.
2. Assert the HTTP filter chain contains the rate-limit filters and that the router is **last**.
3. Drive a short load (`ghz`/`fortio`) and assert from `/stats` that `upstream_rq_retry` and (under induced failure) `upstream_rq_retry_limit_exceeded` are non-zero — i.e., the budget is actually firing, not just present in config.
4. Exit **0** when every assertion passes; exit **non-zero** naming the first failed assertion.

Sketch of the assertion core:

```bash
#!/usr/bin/env bash
set -euo pipefail
ADMIN=${ADMIN:-localhost:9901}
fail() { echo "AUDIT FAIL: $1" >&2; exit 1; }

dump=$(curl -s "$ADMIN/config_dump")

echo "$dump" | grep -q '"retry_budget"' || fail "cart cluster has no retry_budget (storm risk)"
echo "$dump" | grep -q '"outlier_detection"' || fail "no outlier_detection configured"
echo "$dump" | grep -q '"circuit_breakers"' || fail "no circuit_breakers configured"
echo "$dump" | grep -q 'local_ratelimit' || fail "local rate-limit filter missing"

# The router must be the LAST http filter — anything after it never runs.
last_filter=$(echo "$dump" | grep -oE 'envoy\.filters\.http\.[a-z_]+' | tail -1)
[[ "$last_filter" == "envoy.filters.http.router" ]] || fail "router is not the last http filter (got: $last_filter)"

echo "AUDIT PASS: resilience + rate-limit policies loaded; router is terminal."
```

(Harden it: parse JSON with `jq` per-cluster rather than a flat `grep`, so an `inventory` cluster missing a budget doesn't pass because `cart` has one.)

---

## Rules

- **You may** read the Envoy docs, the lecture notes, the `envoyproxy/ratelimit` README, and any Gateway API examples.
- **You must not** ship a cluster fronting a real service without a retry budget, outlier detection, and circuit breakers. The audit enforces this; if `check_edge.sh` passes a budget-less cluster, you've broken the project's reason to exist.
- **You must not** put business logic in the BFF. It aggregates and degrades; it does not decide prices or stock. If the BFF makes a business decision, it's becoming a service.
- **You must not** rely on the local rate limiter alone for per-customer quota — that's the bug the global RLS exists to fix; demonstrate the two-replica shared-budget case.
- Go 1.22+, Envoy 1.31+, Redis 7+. Everything runs in Kind or docker-compose locally.
- The audit must exit non-zero on any missing policy so it can gate a deploy or a CI job.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-07-cart-edge-<yourhandle>`.
- [ ] `func-e run -c envoy/edge.yaml` (or the Kind deploy) brings up a gateway that routes `cart.v1`, `inventory.v1`, and `/cart-screen` correctly — proven with `grpcurl` and `curl`.
- [ ] The `cart` and `inventory` clusters each have a retry budget, outlier detection, and circuit breakers, verifiable in `/config_dump`.
- [ ] The mobile BFF returns one composed screen on the happy path and a degraded screen (no `available`, `stock_live:false`) when inventory is down; it returns 502/504 when cart is down.
- [ ] The global RLS enforces a per-customer quota that is **shared across two Envoy replicas** (demonstrated, with the before/after request counts).
- [ ] `audit/check_edge.sh` exits **0** against the correct edge and **non-zero** when you remove a cluster's retry budget — demonstrated in the README with the actual output.
- [ ] A `README.md` with the routing table, the run commands, and a paragraph on when this gateway is enough and a mesh would be overkill (the homework Problem 4 thesis, in miniature).
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Routing correctness** | 15 | Paths route to the right cluster; gRPC works through the proxy (`http2_protocol_options` present); BFF path wired. |
| **Resilience completeness** | 25 | Timeouts, retries+budget, outlier detection, circuit breakers on every real-service cluster; `previous_hosts` and `per_try_timeout` set; values defensible against the taste from Lecture 2. |
| **BFF quality** | 20 | Parallel fan-out, batched stock lookup, graceful degradation, no business logic, OTel spans present. |
| **Global rate limiting** | 15 | RLS enforces per-customer quota; the two-replica shared-budget case is demonstrated, not just claimed. |
| **Auditability** | 15 | `check_edge.sh` asserts policies are loaded AND firing; non-zero exit on a missing budget; router-is-last check. |
| **Docs & hygiene** | 10 | Clear README, defensible config comments, gateway-vs-mesh paragraph, sensible commits, no secrets/build artifacts checked in. |

**90+** is portfolio-grade and ready to be the capstone's north-south layer. **70–89** works but has a soft audit or a BFF that does too much. **Below 70** means a real-service cluster shipped without a retry budget — fix that first; it's the one thing this week exists to prevent.

---

## Stretch goals

- **xDS the edge.** Replace the static `edge.yaml` with a tiny `go-control-plane` server that streams the listener and clusters over ADS, and hot-reload a route change with zero dropped connections. This is the exact seam istiod plugs into next week.
- **Weighted canary.** Add a `cart_v2` cluster and a weighted route (90/10), then flip it to 50/50 and 0/100 with a config push. You've built progressive delivery by hand — Week 8 does it with an Istio `VirtualService`, and now you know what it generates.
- **Connect instead of gRPC-Web.** Swap the gRPC-Web filter for a Connect backend and prove a browser `fetch()` reaches it directly, no transcoding. Document the trade.
- **CI gate.** A GitHub Actions workflow that boots the edge in a headless container, runs `check_edge.sh`, and fails the build if any resilience policy is missing. Green check on every push.

---

## How this connects to the rest of C22

- **Week 8 (Istio)** takes over east-west: the `cart`→`inventory` hop gets mTLS and mesh-level retries. Your gateway stays the north-south edge; the two layers compose, and the BFF's Service-DNS dials don't change.
- **Week 9 (Linkerd/Cilium)** compares mesh data planes — all of which sit *behind* an edge like this one. The gateway-vs-mesh memo you write this week is the decision that determines whether Weeks 8–9 are even worth it for a given org.
- **Phase 4 (capstone)** deploys `cart-edge` as the real edge of the Polyglot Marketplace Backbone, with the weighted-canary route driving progressive delivery and automatic rollback on SLO breach.

When you've finished, push the repo and take the [quiz](../quiz.md).
