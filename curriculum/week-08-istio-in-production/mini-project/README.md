# Mini-Project — `cart-mesh`: The Cart Topology in Istio, mTLS-Strict and Canary-Ready

> Bring the cart system into Istio: `cart` and `inventory` meshed with STRICT mTLS, a deny-by-default authorization graph that allows only the intended call paths, a weighted canary that shifts cart v1→v2 with mesh-driven traffic management, and — the part that makes you dangerous — a measured comparison of the sidecar tax against ambient mode on your own workload.

This is the artifact that turns "I followed the Istio getting-started" into "I operate a mesh." After this week, the mesh is a *deployable posture* you can defend: every hop encrypted and authorized, a canary you can advance or roll back with a weight change, and a hard number for what the sidecar costs versus ambient — so when someone asks "should we mesh," you answer with evidence instead of enthusiasm.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-mesh` is the east-west layer of your **capstone Polyglot Marketplace Backbone**. The Week 7 `cart-edge` gateway stays the north-south edge; this mesh secures every internal hop behind it. Week 9 reinstalls this exact topology on Linkerd and Cilium so you can compare — so build it cleanly, with the latency baseline captured, because next week's numbers are measured against this week's. Week 21 deepens the security stack (SPIFFE/SPIRE + OPA) on top of the mTLS/authz foundation you lay here.

---

## What you will build

A repo `cart-mesh` with five deliverables:

1. **`mesh/install/`** — the Istio install (sidecar profile) plus the namespace labeling, captured as reproducible manifests/scripts so the mesh comes up the same way every time.
2. **`mesh/security/`** — the security posture: a namespace-wide STRICT `PeerAuthentication` and a deny-by-default `AuthorizationPolicy` graph that allows exactly the intended paths (BFF→cart, cart→inventory) and nothing else.
3. **`mesh/traffic/`** — the traffic management: a `DestinationRule` with v1/v2 subsets and an outlier-detection policy, plus a `VirtualService` that performs the 10/90 → 50/50 → 100/0 canary, with mesh-level retries and timeouts.
4. **`bench/`** — the **sidecar-tax measurement**: a repeatable benchmark (latency p50/p99 and per-pod memory) of the cart→inventory path under (a) sidecar mode and (b) ambient mode, with the numbers and a short analysis.
5. **`audit/verify_mesh.sh`** — a script that proves the posture is real: it asserts STRICT mTLS is effective, that the deny-by-default authz actually denies an unauthorized principal, and that the canary weights are present on the actual proxy. Exits non-zero if any claim is false.

By the end you have a public repo of Istio CRDs + a benchmark + an audit script that any future service can be onboarded into.

---

## Why this and not "just turn on Istio"

You could `istioctl install` and call your services "meshed." Don't stop there — that's the gap this whole week is about. A defensible mesh posture gives you:

- **mTLS you can prove is enforced**, not merely available. The default mesh is permissive; this project's audit asserts STRICT and *demonstrates plaintext is refused*. The difference is a compliance pass versus a compliance finding.
- **Least-privilege east-west**, not "anyone in the mesh can call anyone." Deny-by-default plus explicit allows is what makes a lateral-movement attack (a compromised pod calling services it shouldn't) fail at the data plane.
- **A canary you can actually run**, with instant rollback as a weight change — and a hook for automatic rollback on SLO breach.
- **A real answer to "what does the mesh cost,"** measured on *your* workload, so the adopt/don't-adopt decision (and the sidecar-vs-ambient choice) is evidence-based.

The Gateway API and progressive-delivery controllers will eventually drive much of this for you. Building it by hand first is what lets you read and trust what they generate — the senior-shop convention in 2026.

---

## Repo layout

```
cart-mesh/
├── README.md
├── mesh/
│   ├── install/
│   │   └── install.sh            # istioctl install + namespace labeling, reproducible
│   ├── security/
│   │   ├── peer-authentication.yaml   # namespace STRICT mTLS
│   │   └── authorization-policy.yaml  # deny-by-default + explicit allows
│   └── traffic/
│       ├── destinationrule.yaml       # v1/v2 subsets + outlier detection
│       └── virtualservice.yaml        # the weighted canary + retries/timeout
├── bench/
│   ├── run.sh                    # drives fortio, scrapes latency + memory
│   └── RESULTS.md                # sidecar vs ambient numbers + analysis
├── audit/
│   └── verify_mesh.sh            # asserts mTLS strict, authz denies, canary weights present
└── deploy/
    └── *.yaml                    # cart-v1, cart-v2, inventory deployments + services
```

---

## Deliverable 1 — `mesh/install/` (reproducible install)

A script that installs Istio (sidecar profile), creates the `shop` namespace, labels it for injection, applies the observability addons, and waits for everything healthy. It must be idempotent — running it twice doesn't break a working mesh. Capture the exact `istioctl` version; mesh behavior is version-sensitive and "works on my cluster" is not a deliverable.

---

## Deliverable 2 — `mesh/security/` (the posture)

The security CRDs:

- **`peer-authentication.yaml`** — namespace-wide STRICT. Document in a comment why you'd stage PERMISSIVE→STRICT in production even though the lab goes straight to STRICT.
- **`authorization-policy.yaml`** — a deny-by-default base plus explicit allows keyed on SPIFFE principals. The intended graph is: the BFF/gateway may call `cart`; `cart` may call `inventory`; nothing else. Every allow names the source principal (`cluster.local/ns/shop/sa/<sa>`) and the target methods. The rule the audit enforces: an unauthorized principal calling `inventory` gets `RBAC: access denied`.

> **The rule the audit enforces:** the mesh must *deny* a call from a principal you didn't allow. A posture that "has an AuthorizationPolicy" but allows everything (an over-broad rule, a `principals: ["*"]`) fails the audit. Least privilege is the point.

---

## Deliverable 3 — `mesh/traffic/` (the canary)

The traffic CRDs, building on Exercise 2:

- **`destinationrule.yaml`** — `cart` with v1/v2 subsets and an `outlierDetection` block (the same passive health checking you wrote in raw Envoy in Week 7, now declared).
- **`virtualservice.yaml`** — the weighted canary with mesh-level `retries` (gRPC-aware `retryOn`, `perTryTimeout`) and an overall `timeout`. The canary must be advanceable (edit weights, re-apply) and instantly rollback-able (v2 weight → 0).

Document the three stages and the rollback in the repo README, with the `istioctl proxy-config routes` output proving the weights landed on the actual proxy at each stage.

---

## Deliverable 4 — `bench/` (the sidecar-tax measurement)

This is the deliverable that separates this project from a tutorial. Measure, on *your* cart→inventory path:

1. **Sidecar mode:** p50/p99 latency under a fixed load (`fortio -c N -qps Q -t 60s`) and the per-pod memory of the `istio-proxy` containers (`kubectl top pod`).
2. **Ambient mode:** reinstall ambient (`istioctl install --set profile=ambient`), relabel the namespace `istio.io/dataplane-mode=ambient`, and re-run the identical benchmark. Note pods are now `1/1` (no sidecar).
3. **Ambient + waypoint:** add a waypoint to the namespace (so L7 policy works in ambient) and re-measure — this shows what L7 costs *on top of* ambient's cheap L4 floor.

Write `RESULTS.md`: a table of latency and memory across the three configurations, and a paragraph of analysis. The honest shape you'll find: ambient's L4-only path is much lighter than the sidecar; the waypoint brings back some cost, but only where you need L7. Put real numbers on it. "The sidecar costs ~X MB/pod and ~Y ms p99 on our workload; ambient cuts that to Z" is the sentence that wins a mesh-architecture argument.

---

## Deliverable 5 — `audit/verify_mesh.sh`

A script that makes the posture *verifiable*, not claimed. Against the running mesh it must:

1. Assert STRICT mTLS is **effective** on `inventory` (`istioctl x describe` reports STRICT) AND demonstrate plaintext from an un-meshed pod is **refused**.
2. Assert the deny-by-default authz actually **denies**: run the Exercise-3 probe from an unauthorized principal and confirm `RBAC: access denied`.
3. Assert the canary weights are present on the **actual proxy** (`istioctl proxy-config routes` shows the configured split), not just in the CRD.
4. Exit **0** when every assertion passes; exit **non-zero** naming the first failure.

Sketch:

```bash
#!/usr/bin/env bash
set -euo pipefail
NS=${NS:-shop}
fail() { echo "MESH AUDIT FAIL: $1" >&2; exit 1; }

# 1. mTLS strict effective?
istioctl x describe pod -n "$NS" "$(kubectl get pod -n "$NS" -l app=inventory -o jsonpath='{.items[0].metadata.name}')" \
  | grep -q "STRICT" || fail "inventory PeerAuthentication is not STRICT"

# 1b. plaintext from outside the mesh refused?
if kubectl run audit-plain --image=curlimages/curl -n default --rm -i --restart=Never -- \
     curl -sS -m 5 "http://inventory.$NS.svc.cluster.local:50051/" >/dev/null 2>&1; then
  fail "plaintext call from un-meshed pod SUCCEEDED — STRICT is not enforced"
fi

# 2. unauthorized principal denied? (drive the probe; expect RBAC denial)
# ... exec the exercise-03 probe from a non-cart SA and assert DENIED ...

# 3. canary weights on the actual proxy?
istioctl proxy-config routes deploy/cart -n "$NS" -o json \
  | grep -q '"weight"' || fail "no weighted canary route on the cart proxy"

echo "MESH AUDIT PASS: STRICT mTLS enforced, unauthorized denied, canary weights live."
```

---

## Rules

- **You may** read the Istio docs, the lecture notes, and the Flagger/Argo Rollouts docs for the stretch.
- **You must not** declare the mesh "secure" with a permissive `PeerAuthentication` or an over-broad `AuthorizationPolicy`. The audit enforces STRICT + real denial; if `verify_mesh.sh` passes a permissive mesh or an allow-everything policy, you've broken the project's reason to exist.
- **You must not** report a sidecar-tax number you didn't measure. The benchmark must be reproducible from `bench/run.sh`.
- **You must not** "fix" a sidecar startup problem by un-meshing (see the challenge).
- Istio 1.24+, Kind, `istioctl`/`kubectl`/`fortio`. Everything runs locally.
- The audit must exit non-zero on any failed assertion so it can gate a deploy or CI.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-08-cart-mesh-<yourhandle>`.
- [ ] `mesh/install/install.sh` brings up Istio and a meshed `shop` namespace idempotently; `cart`/`inventory` pods are `2/2`.
- [ ] STRICT mTLS is enforced (proven by an un-meshed plaintext call being refused) and verifiable via `istioctl x describe`.
- [ ] The deny-by-default authz graph allows the intended paths and denies an unauthorized principal with `RBAC: access denied` (demonstrated).
- [ ] The canary advances 10/90 → 50/50 → 100/0 via weight changes and rolls back instantly (v2→0), with `istioctl proxy-config routes` output at each stage.
- [ ] `bench/RESULTS.md` has measured latency + memory numbers for sidecar, ambient, and ambient+waypoint, with analysis.
- [ ] `audit/verify_mesh.sh` exits **0** against the correct mesh and **non-zero** when you weaken the posture (e.g., flip to PERMISSIVE) — demonstrated in the README.
- [ ] A `README.md` with the security graph diagram, the canary stages, the benchmark table, and a paragraph on when this mesh is worth its cost.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **mTLS enforcement** | 20 | STRICT effective AND demonstrated (plaintext refused), not merely a STRICT CRD applied. |
| **Authorization (least privilege)** | 20 | Deny-by-default; allows are principal-scoped and minimal; an unauthorized principal is actually denied. |
| **Canary correctness** | 20 | Subsets + weights work; proven on the actual proxy; instant rollback demonstrated; mesh-level retries/timeout present. |
| **Sidecar-tax measurement** | 20 | Real, reproducible latency + memory numbers across sidecar/ambient/ambient+waypoint; honest analysis. |
| **Auditability** | 15 | `verify_mesh.sh` asserts enforcement (not config presence); non-zero exit when the posture is weakened. |
| **Docs & hygiene** | 5 | Clear README, security-graph diagram, sensible commits, no secrets/build artifacts checked in. |

**90+** is portfolio-grade and ready to be the capstone's east-west layer. **70–89** works but likely claims security it doesn't prove, or reports an unmeasured tax. **Below 70** usually means the mesh is permissive or the authz allows everything — fix that first; it's the one thing this week exists to prevent.

---

## Stretch goals

- **Automatic rollback.** Wire Flagger (or Argo Rollouts) to drive the canary `VirtualService` and roll back automatically when the canary's error rate breaches an SLO you define. Induce a bad v2, watch it roll back. This is the capstone's progressive-delivery story.
- **Ambient end-to-end.** Run the *entire* posture (mTLS, authz, canary) in ambient mode, adding waypoints only where L7 policy is needed, and prove `verify_mesh.sh` still passes. Document what moved from the sidecar to the ztunnel/waypoint.
- **Scope the sidecars.** Add `Sidecar` resources that limit what each workload discovers, and show istiod's config-push size shrinks — the technique that keeps a large mesh's control plane affordable.
- **CI gate.** A GitHub Actions workflow that boots the mesh in a Kind-in-a-container, applies the posture, and runs `verify_mesh.sh`. Green check on every push.

---

## How this connects to the rest of C22

- **Week 7 (`cart-edge`)** is the north-south edge; this mesh secures the east-west hops behind it. The two compose: the gateway terminates client TLS, the mesh mTLS-es every internal hop.
- **Week 9 (Linkerd/Cilium)** reinstalls this exact topology on the other two meshes and measures against the latency baseline you capture here. Your `bench/` numbers are next week's control group.
- **Week 21 (zero-trust)** replaces istiod's built-in CA with SPIFFE/SPIRE and adds OPA admission policy on top of the mTLS/authz foundation you build here.
- **Phase 4 (capstone)** deploys `cart-mesh` as the real east-west security layer, with Flagger-driven progressive delivery and automatic rollback on SLO breach.

When you've finished, push the repo and take the [quiz](../quiz.md).
