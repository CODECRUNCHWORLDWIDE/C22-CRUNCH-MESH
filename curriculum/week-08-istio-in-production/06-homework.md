# Week 8 Homework

Six problems that revisit the week's topics and force the Istio operational literacy into your fingers. The full set should take about **5 hours**. Work in your Week 8 Git repository (the same workspace as the exercises and the `cart-mesh` mini-project) so every problem produces at least one commit you can point to at the Phase 2 architecture review in Week 12.

The headline deliverable is **Problem 4 — the sidecar-vs-ambient cost memo**, the artifact a platform lead reads before choosing a data-plane mode for a fleet. Treat it as a funding/architecture decision document, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Istio** installed on Kind and your **`cart`/`inventory`** services meshed (Exercise 1). Problems 1, 2, 3, 5, and 6 run against the live mesh.

---

## Problem 1 — The mesh posture audit table

**Problem statement.** Bring up your meshed `shop` namespace. For **every** workload in it, capture the actual security and routing posture from `istioctl` (not from your CRDs). Build a markdown table in `notes/week-08/mesh-audit.md` with one row per workload and these columns:

| Workload | Sidecar present (2/2)? | Effective mTLS | AuthorizationPolicies applied | Proxy SYNCED? | Correct? |
|---|---|---|---|---|---|

The **Correct?** column is your judgement against the week's posture (every workload should be `2/2`, STRICT, and have a deny-by-default-plus-allow authz), with a one-line reason where you wrote `no`.

**Acceptance criteria.**

- `notes/week-08/mesh-audit.md` exists with one row per workload (at least `cart`, `inventory`).
- Every row's mTLS and sync columns come from `istioctl x describe` / `istioctl proxy-status`, not from your CRD YAML.
- At least one workload is marked `no` with a reason, or you explicitly argue every workload is already correct and why.
- Committed.

**Hint.** `istioctl proxy-status` gives you the sync column for all proxies at once; `istioctl x describe pod <pod>` gives the effective mTLS and applied policies per workload. If a workload is `1/1`, that's your `no` — the sidecar didn't inject.

**Estimated time.** 40 minutes.

---

## Problem 2 — Prove mTLS is enforced, not just available

**Problem statement.** Demonstrate the difference between mTLS *available* and mTLS *enforced*. With the namespace PERMISSIVE, make a plaintext call to `inventory` from an un-meshed pod and capture that it *succeeds*. Then flip to STRICT and capture that the same call now *fails*. Quote the `connection_security_policy` telemetry label in both states.

**Acceptance criteria.**

- `notes/week-08/mtls-enforcement.md` shows the un-meshed plaintext call succeeding under PERMISSIVE and failing under STRICT.
- You quote the `istio_requests_total{...connection_security_policy="..."}` label for a meshed call (it should read `mutual_tls`).
- You state in one sentence why "we have a mesh" does not imply "our traffic is encrypted."
- Committed.

**Hint.** Run the un-meshed pod in `default` (no injection): `kubectl run plain --image=curlimages/curl -n default --rm -it --restart=Never -- curl -m5 http://inventory.shop.svc.cluster.local:50051/`. Under PERMISSIVE it connects; under STRICT the connection is reset. That toggle IS enforcement.

**Estimated time.** 45 minutes.

---

## Problem 3 — Least-privilege authorization

**Problem statement.** Build a deny-by-default `AuthorizationPolicy` graph for `shop`: allow only BFF→cart and cart→inventory; deny everything else. Then prove it with the Exercise-3 probe from (a) an allowed principal — passes — and (b) a different principal — `RBAC: access denied`. Finally, remove the allow-cart rule and show that *even cart* is now denied (deny-by-default is real).

**Acceptance criteria.**

- `notes/week-08/authz.md` records the policy YAML, the allowed-principal pass, the unauthorized-principal denial (with the `RBAC: access denied` line), and the "even cart is denied when the allow is removed" result.
- The allow rules are principal-scoped (`cluster.local/ns/shop/sa/<sa>`), not `principals: ["*"]`.
- You quote `inventory`'s `istio-proxy` log line showing the RBAC denial — proof the *mesh* denied it, not the app.
- Committed.

**Hint.** The deny-by-default base is an ALLOW policy with `rules: []` (matches nothing → denies all). Then each allow punches one hole. To get a "different principal," run a second workload under a different service account, or use the Istio `sleep` sample.

**Estimated time.** 50 minutes.

---

## Problem 4 — The sidecar-vs-ambient cost memo (headline deliverable)

**Problem statement.** This is the syllabus skill ("the cost of sidecars; ambient mesh and why it exists"). Write a one-to-two-page memo at `notes/week-08/sidecar-vs-ambient-memo.md` advising a platform team which data-plane mode to adopt, backed by numbers *you measured* on your cart topology. Pick **one** org and state which:

- **Org A:** wants mTLS + telemetry on every internal hop, but does very little L7 policy (a few routes, mostly L4 service-to-service).
- **Org B:** does rich L7 work everywhere — per-route authz on HTTP attributes, lots of header-based routing, fault injection in many namespaces.

Your memo must hit these headings:

1. **Recommendation** — one sentence: sidecar, ambient, or ambient-plus-targeted-waypoints, for the chosen org.
2. **The measured tax** — your benchmark numbers: p50/p99 latency and per-pod memory for sidecar vs ambient (vs ambient+waypoint) on the cart→inventory path.
3. **What each mode can do** — sidecar's always-on L7 vs ambient's cheap L4 floor + opt-in L7, mapped to the org's actual needs.
4. **The cost at the org's scale** — extrapolate your per-pod numbers to the org's pod count. "X MB/pod × N pods = Y GB of pure proxy memory" is the sentence that lands.
5. **The decision** — tie the measured cost to the org's L7 needs. For Org A (little L7), ambient is usually the clear win. For Org B (L7 everywhere), the sidecar's "it's already there" may beat sprinkling waypoints into every namespace.
6. **The migration path** — how you'd move an existing sidecar mesh to ambient (or vice versa) incrementally, namespace by namespace.

**Acceptance criteria.**

- `notes/week-08/sidecar-vs-ambient-memo.md` exists, fits on roughly one-to-two pages (600–1000 words), and hits all six headings.
- The **measured tax** section uses real numbers from your own benchmark, not figures quoted from a blog.
- The cost is extrapolated to the org's scale, not left as a per-pod abstraction.
- The recommendation commits to a position and ties it to the org's L7 needs.
- Committed.

**Hint.** The strongest memos quantify and then extrapolate: measure ~Z MB/pod sidecar overhead, then multiply by the org's pod count to show the fleet-wide memory bill. For Org B, the honest counter to "ambient is cheaper" is "but if you need L7 in every namespace, you're adding a waypoint everywhere, which claws back much of the saving and adds its own ops" — address it. This memo is the conversation you'll have at the Phase 2 review; rehearse it with numbers.

**Estimated time.** 1 hour.

---

## Problem 5 — Run the canary and force a rollback

**Problem statement.** Using your `DestinationRule` + `VirtualService` from the mini-project, run the canary 10/90 → 50/50, capturing the proxy-level weights at each stage. Then deploy a deliberately broken `cart` v2 (returns 5xx), shift 10% to it, observe the error rate rise on the v2 subset, and roll back (v2 weight → 0). Capture the before/after.

**Acceptance criteria.**

- `notes/week-08/canary.md` shows `istioctl proxy-config routes` output proving the weights landed at 10/90 and 50/50.
- You capture the v2 error rate rising (from the metric or Kiali) when the broken v2 takes traffic.
- You demonstrate instant rollback: setting v2 weight to 0 stops traffic to it with no pod restart, and the error rate recovers.
- You note in one sentence what a progressive-delivery controller (Flagger/Argo Rollouts) would have automated here.
- Committed.

**Hint.** The proxy weights are the proof the CRD became real config: `istioctl proxy-config routes deploy/cart -o json | jq '.[].virtualHosts[].routes[].route.weightedClusters'`. The instant-rollback point is the whole value of mesh canary — no redeploy, just a weight push.

**Estimated time.** 40 minutes.

---

## Problem 6 — Diagnose a planted mesh fault

**Problem statement.** Have a partner (or your future self) introduce ONE of these faults into your mesh, then diagnose it from the outside using `istioctl` before looking at what was changed: (a) a `VirtualService` whose `host` doesn't match the Service, (b) a Service port mis-named `tcp-cart` instead of `grpc-cart`, or (c) a `PeerAuthentication` applied to the wrong namespace. For whichever fault, produce a diagnosis: symptom, the `istioctl analyze` / `proxy-config` evidence, root cause, and fix.

**Acceptance criteria.**

- `notes/week-08/planted-fault.md` records which fault, the diagnostic commands you ran, the evidence (quote `istioctl analyze` and/or `proxy-config`), the root cause, and the fix.
- You reach the diagnosis with at least two signals (e.g., `istioctl analyze` warning *and* the missing route in `proxy-config`).
- Committed.

**Hint.** `istioctl analyze -n shop` catches all three of these classes — a host that doesn't resolve, a port that won't get L7 treatment, a policy that won't apply. It's the mesh's equivalent of a linter; run it first. The port-naming one is the sneakiest: the route is *applied* but silently L4-only, so the symptom is "my VirtualService doesn't take effect" with no error.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Mesh posture audit table | 40 min |
| 2 — Prove mTLS enforced | 45 min |
| 3 — Least-privilege authorization | 50 min |
| 4 — Sidecar-vs-ambient memo (headline) | 1 h 0 min |
| 5 — Canary and rollback | 40 min |
| 6 — Diagnose a planted fault | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `cart-mesh` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — Week 9 reinstalls this topology on Linkerd and Cilium and measures against your baseline. Then take the [quiz](./05-quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Posture audit (P1)** | 15 | Real `istioctl` evidence per workload; the un-injected or non-STRICT workload correctly flagged. |
| **mTLS enforcement (P2)** | 15 | PERMISSIVE-succeeds / STRICT-fails demonstrated; `connection_security_policy` quoted. |
| **Authorization (P3)** | 20 | Deny-by-default real; principal-scoped allows; unauthorized denial proven from the sidecar log. |
| **Sidecar-vs-ambient memo (P4)** | 25 | Measured numbers; extrapolated to org scale; committed recommendation tied to L7 needs; counter-argument addressed. |
| **Canary + rollback (P5)** | 15 | Proxy-level weights captured; broken-v2 error rise observed; instant rollback demonstrated. |
| **Planted fault (P6)** | 10 | Two-signal diagnosis; `istioctl analyze` evidence; correct root cause and fix. |

**90+** is portfolio-grade. **70–89** is solid but the memo likely lacks measured numbers or hedges on the recommendation. **Below 70** usually means Problem 2 or 4 was treated as a formality — they're the two that prove you understand the mesh's *cost* and its *enforcement*, which is the whole difference between installing Istio and operating it.
