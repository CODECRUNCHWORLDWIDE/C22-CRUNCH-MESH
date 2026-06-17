# Lecture 2 — Traffic Management, the Weighted Canary, and the Sidecar Tax

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can shape traffic with `VirtualService` and `DestinationRule`, run a weighted canary and reason about automatic rollback, inject faults at the mesh to test resilience without touching code, read the result in Kiali, and debug the sidecar startup surprises that page every Istio operator.

Lecture 1 gave you the mesh and its security floor. This lecture is what you *do* with it day to day: move traffic safely, break things on purpose, and survive the sidecar. Three parts: (1) traffic management and the canary, (2) fault injection and observability, (3) the sidecar tax and the debugging it forces.

The sentence to carry through:

> **A canary is a weighted route plus a way to notice it's going wrong and undo it — and the mesh gives you the weighted route for free, but the "notice and undo" is the part you actually have to engineer.**

---

## Part 1 — Traffic management

### 1.1 The two CRDs and their division of labor

Traffic management is two CRDs that work as a pair:

- **`DestinationRule`** defines, for a service, its **subsets** (named slices of endpoints, selected by pod labels) and the per-destination **traffic policy** (load balancing, connection pools, outlier detection). It maps to an Envoy **cluster** and its sub-clusters.
- **`VirtualService`** defines the **routing**: which requests go to which subset, with what weights, retries, timeouts, and fault injection. It maps to Envoy **routes**.

The division: the `DestinationRule` says "here are the versions of cart and how to load-balance each"; the `VirtualService` says "send 90% of cart traffic to v1, 10% to v2." You need both — the `VirtualService` weights are meaningless without the subsets the `DestinationRule` defines.

```yaml
# DestinationRule: define the subsets (v1, v2) by pod label, plus a traffic policy.
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: cart
  namespace: shop
spec:
  host: cart.shop.svc.cluster.local
  trafficPolicy:
    loadBalancer:
      simple: LEAST_REQUEST          # the Envoy LB policy, set declaratively
    outlierDetection:                # the SAME outlier detection you wrote by hand in Week 7
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
  subsets:
  - name: v1
    labels: { version: v1 }          # selects pods labeled version=v1
  - name: v2
    labels: { version: v2 }
```

```yaml
# VirtualService: route by weight across the subsets — the canary.
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: cart
  namespace: shop
spec:
  hosts: [cart.shop.svc.cluster.local]
  http:
  - route:
    - destination: { host: cart.shop.svc.cluster.local, subset: v1 }
      weight: 90
    - destination: { host: cart.shop.svc.cluster.local, subset: v2 }
      weight: 10                      # 10% canary to v2
```

Notice the `outlierDetection` block — it is the *same* passive-health-checking you configured in raw Envoy last week, now declared in a CRD. That's the whole point of Lecture 1's mapping table made concrete: the mesh isn't doing something new; it's the Envoy you know, configured for you.

### 1.1.5 Beyond weights: header routing and mirroring

Weighted splits are the canary's backbone, but the `VirtualService` does more, and two patterns earn their keep:

**Header-based routing** sends specific requests to a subset regardless of weight — the basis of *dark launches* and *internal testing*. Route requests carrying a `x-canary: true` header to v2, and your team can exercise v2 in production while real users stay on v1:

```yaml
http:
- match:
  - headers:
      x-canary: { exact: "true" }      # internal testers opt into v2
  route:
  - destination: { host: cart.shop.svc.cluster.local, subset: v2 }
- route:                                # everyone else: stable v1
  - destination: { host: cart.shop.svc.cluster.local, subset: v1 }
```

**Traffic mirroring** (shadowing) sends a *copy* of live traffic to v2 while the real response still comes from v1. The mirrored requests hit v2 for real, so you see how v2 behaves under production load and shape — but v2's responses are discarded, so a broken v2 can't hurt a user:

```yaml
http:
- route:
  - destination: { host: cart.shop.svc.cluster.local, subset: v1 }
  mirror: { host: cart.shop.svc.cluster.local, subset: v2 }
  mirrorPercentage: { value: 100.0 }   # shadow 100% of traffic to v2, responses discarded
```

Mirroring is the safest pre-canary check there is: v2 sees real traffic before it serves a single real user. The catch — and a real foot-gun — is **side effects**: if v2's code writes to a database or calls a payment API, the mirrored requests do those writes *for real*, doubling them. Mirror only read-shaped traffic, or point the mirror at a v2 wired to a scratch datastore. Naming this constraint is the difference between a safe shadow test and a duplicated charge.

### 1.2 The weighted canary, stage by stage

A canary deploy is a sequence of weight changes, each held long enough to observe:

1. **10/90** — deploy v2, send it 10% of traffic. Watch v2's error rate and latency. If it's healthy, proceed; if not, set v2 to 0 (instant rollback — no redeploy, just a weight change).
2. **50/50** — half the traffic. Higher confidence, larger blast radius if wrong.
3. **100/0** — v2 takes everything; v1 is now idle and can be scaled down.

The thing the mesh makes cheap is the *weight change*: editing a `VirtualService` shifts traffic in seconds with no pod restarts and no dropped connections (istiod pushes the new route; Envoy applies it per-worker, eventually-consistent, exactly as in Week 7 §4). The thing the mesh does *not* give you for free is the decision to advance or roll back — that's the next section.

### 1.3 Progressive delivery and automatic rollback

Doing canary stages by hand (edit YAML, watch a dashboard, edit again) works but doesn't scale and doesn't run at 3 a.m. The production answer is a **progressive-delivery controller** — **Flagger** or **Argo Rollouts** — that:

1. Watches a metric (error rate, p99 latency, a custom SLI) for the canary subset.
2. Automatically steps the weight up (10 → 25 → 50 → 100) while the metric stays healthy.
3. **Automatically rolls back** — sets the canary weight to 0 — the moment the metric breaches a threshold.

The controller drives the *same* `VirtualService` weights you'd edit by hand; it just does it on a schedule with a kill switch wired to your SLO. The capstone's "automatic rollback on SLO breach" is precisely this: Flagger watching `istio_requests_total{response_code=~"5.."}` and yanking the canary weight to 0 if the canary's error rate exceeds, say, 1%.

```yaml
# A Flagger Canary sketch — the controller manages the VirtualService weights for you.
apiVersion: flagger.app/v1beta1
kind: Canary
metadata: { name: cart, namespace: shop }
spec:
  targetRef: { apiVersion: apps/v1, kind: Deployment, name: cart }
  service: { port: 50051 }
  analysis:
    interval: 1m
    threshold: 5              # 5 failed checks -> roll back
    maxWeight: 50
    stepWeight: 10
    metrics:
    - name: request-success-rate
      thresholdRange: { min: 99 }   # if success rate < 99%, fail the check
    - name: request-duration
      thresholdRange: { max: 500 }  # if p99 > 500ms, fail the check
```

> **The engineering is in the metric, not the mesh.** Anyone can write a weighted route. The skill is choosing an SLI that actually reflects user pain and a threshold that catches a bad canary without false-positive-ing on noise. A canary that rolls back on every transient blip is as useless as one that never rolls back. That judgment — the same SLO discipline as Week 18 — is what the controller automates, and it's only as good as the metric you give it.

### 1.4 Mesh-level retries and timeouts on the route

The `VirtualService` also carries the resilience knobs you configured by hand in Envoy last week — retries and timeouts — now declared at the route. This is where the Week 7 discipline becomes mesh config:

```yaml
http:
- route:
  - destination: { host: inventory.shop.svc.cluster.local }
  timeout: 2s                            # overall request budget, including retries
  retries:
    attempts: 2
    perTryTimeout: 800ms                 # each attempt bounded independently
    retryOn: "connect-failure,refused-stream,unavailable"   # gRPC-aware conditions
```

Two subtleties carry straight over from Week 7. First, `timeout` is the **overall** budget *including* retries — so `timeout: 2s` with two retries means all attempts must finish within 2 s total, and `perTryTimeout` bounds each individual attempt. Get the arithmetic wrong (a `perTryTimeout` larger than the overall `timeout`) and the retries can't actually fire. Second, the same retry-storm caution applies: mesh retries amplify load on a struggling backend just like proxy retries do, so the discipline of "only retry idempotent operations, and watch the aggregate" is unchanged. Istio doesn't expose a `retry_budget` as directly as raw Envoy, so the mitigation here leans more on conservative `attempts` and on outlier detection ejecting bad hosts — which is one of the cases where dropping to the underlying Envoy config (via an `EnvoyFilter`) is justified if you need the budget. The point: the resilience *primitives* are the same Envoy ones; the mesh just gives you a friendlier (and slightly less complete) CRD surface over them.

---

## Part 2 — Fault injection and observability

### 2.1 Breaking things on purpose, at the mesh

One of the mesh's quietest superpowers: you can inject faults into a route *without touching application code*. The `VirtualService` `fault` stanza makes Istio delay or abort a fraction of requests, so you can test whether callers handle a slow or failing dependency — the resilience you configured in Week 7 — under controlled conditions.

```yaml
# Inject 200ms of latency into 50% of inventory requests, and abort 10% with a 503.
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata: { name: inventory, namespace: shop }
spec:
  hosts: [inventory.shop.svc.cluster.local]
  http:
  - fault:
      delay:
        percentage: { value: 50 }
        fixedDelay: 200ms          # half of requests are delayed 200ms
      abort:
        percentage: { value: 10 }
        httpStatus: 503            # 10% are aborted with a 503 (gRPC maps to UNAVAILABLE)
    route:
    - destination: { host: inventory.shop.svc.cluster.local }
```

Apply this and watch what your *cart* service and *BFF* do. Does the BFF degrade gracefully (the Week 7 discipline) when inventory is slow or failing? Does cart's retry policy recover the 503s? This is the syllabus's "inject a 200 ms latency fault and observe in Kiali" — a controlled rehearsal of the failures Week 22's gameday will throw at you for real, with the safety of a percentage you control and a single `kubectl delete` to stop.

> **Fault injection is a resilience *test*, not a resilience feature.** You inject the fault to discover whether your timeouts, retries, and degradation actually work — and you delete it when you're done. Leaving fault injection in a non-test namespace is a self-inflicted outage. (It's also a fun, and real, on-call story: "the latency was coming from inside the mesh.")

A discipline that makes mesh fault injection safe and useful: **scope it tightly and make it loud.** Scope the fault to a specific test client where you can (via a header match, so only requests carrying `x-fault-test: true` get the delay/abort), so production users never see it even while the experiment runs. And make it loud — announce it, time-box it, and have the `kubectl delete` ready — so nobody on the team mistakes the injected failure for a real incident and starts a wild-goose-chase. The most embarrassing version of this is an engineer paging the team about "elevated inventory latency" that turns out to be a fault-injection `VirtualService` a colleague forgot to delete on Friday. Treat fault injection like any other controlled experiment: hypothesis, scope, time box, cleanup. Done that way, it's the safest possible rehearsal for Week 22's gameday; done carelessly, it's the gameday's first incident.

### 2.2 Kiali and the trace continuity story

**Kiali** is the mesh's eyes: a live service graph showing every service, the traffic flowing between them (rate, latency, error percentage), and a padlock on each mTLS edge. When you shift a canary, Kiali shows the traffic split visually; when you inject a fault, you watch the error percentage climb on exactly the edge you targeted. It also validates your CRDs (the same checks as `istioctl analyze`) and shows you which routes are actually in effect.

The deeper observability win the mesh hands you: **the sidecars emit spans automatically**, so a request that crosses cart → inventory shows up as a distributed trace *without you instrumenting the network hop yourself*. You still instrument your application logic (the OpenTelemetry from Week 6), but the mesh fills in the inter-service spans and propagates the trace context. The thing to verify — and the thing that breaks subtly — is **trace continuity**: the mesh propagates the standard tracing headers (`traceparent`, the B3 headers), but *your app must forward them* from inbound to outbound requests. If cart doesn't propagate the headers it received to its call to inventory, the trace breaks at cart and Kiali shows two disconnected traces instead of one. The mesh gives you the network spans; header propagation across your app logic is still your job.

### 2.3 The mesh's golden-signal metrics

Beyond traces, the sidecars emit a consistent set of metrics for *every* meshed service, with no application code — the RED signals (Rate, Errors, Duration) per service and per edge. The canonical metric is `istio_requests_total`, labeled with source, destination, response code, and — the security label from Lecture 1 — `connection_security_policy`. From these you build the dashboards and, crucially, the **SLI for progressive delivery**:

```promql
# success rate for the cart v2 subset (the canary's SLI):
sum(rate(istio_requests_total{destination_workload="cart-v2",response_code!~"5.."}[1m]))
/ sum(rate(istio_requests_total{destination_workload="cart-v2"}[1m]))
```

This is the exact query a Flagger `Canary` watches to decide advance-or-rollback. The value of the mesh emitting it *uniformly* is that you don't depend on each service team instrumenting its own success-rate metric correctly — the mesh measures the same thing the same way for everyone, which is what makes a fleet-wide automated rollback policy *trustworthy*. A per-team, hand-rolled metric would mean the rollback logic is only as reliable as the least-careful team's instrumentation; the mesh's uniform metric removes that variance. This is the same "uniformity is the real value" argument as mTLS, applied to observability: the mesh's worth is less any single feature and more that it does each feature *identically across every team*.

The honest caveat: the mesh's metrics see *network* success/failure, not *semantic* success. A service that returns HTTP 200 with a body saying "sorry, out of stock" is a success to `istio_requests_total` and a failure to the user. So mesh RED metrics are necessary but not sufficient for an SLO — you still need application-level SLIs for correctness. The mesh gives you "is it responding and fast"; "is it responding *correctly*" remains your app's job to measure. A canary that only watches mesh metrics can promote a v2 that returns fast, wrong answers — which is why mature progressive-delivery setups combine mesh RED metrics with at least one app-level correctness check.

---

## Part 3 — The sidecar tax and the debugging it forces

### 3.1 The cost, measured

"The sidecar costs something" is true but useless until you put numbers on it. The costs, concretely:

- **Memory:** each sidecar Envoy is tens to ~100+ MB resident, *per pod*. A 500-pod cluster pays that 500 times. (This is the single biggest driver of ambient adoption.)
- **Latency:** each meshed hop adds two proxy traversals (local sidecar out, remote sidecar in). On a fast path this is a fraction of a millisecond to a couple of milliseconds at p50, more at p99 under load. For a chatty call chain (BFF → cart → inventory → ...), the per-hop tax compounds.
- **Startup time:** a meshed pod is "ready" only once its sidecar is ready, which adds seconds to pod startup — and creates the race in §3.2.
- **Operational surface:** the control plane, the injection webhook, certificate rotation, and the config-push cost (which grows with mesh size unless you scope it with `Sidecar` resources).

The homework has you measure the latency and memory delta on your own cart topology — sidecar vs ambient — because "measure it on your workload" beats any number a lecture can quote. The shape you'll find: ambient's L4-only path is much cheaper than the sidecar; adding a waypoint for L7 brings back *some* of the cost, but only on the namespaces that need L7.

### 3.1.5 Choosing sidecar vs ambient, concretely

Now that you can quantify the cost, here is the decision, made operational. For a *given workload*, prefer **ambient** when:

- Its needs are mostly L4 — service connectivity, mTLS, and golden-signal telemetry — with little or no L7 policy. This is the majority of workloads in most clusters.
- Per-pod memory at your pod count is a real cost line (hundreds-to-thousands of pods).
- You want to enroll namespaces without restarting pods (the relabel-not-reinject property).

Prefer the **sidecar** when:

- The workload needs rich L7 on most of its hops (complex routing, fault injection, per-request policy), so it would need a waypoint anyway — and at that point the sidecar's "L7 is already right here" can be simpler than routing through a waypoint.
- You want the strongest per-pod isolation (the proxy shares the pod's exact lifecycle and traffic), or you're on an Istio version/feature combination where a specific capability is sidecar-only.

The 2026-current default for a *new* adoption is "ambient as the floor, waypoints where L7 is needed" — you get cheap mTLS everywhere and pay for L7 only where you use it. But the two modes *coexist* in one mesh: you can run most namespaces ambient and a few L7-heavy ones with sidecars. The skill is per-workload judgment, not a religious commitment to one mode. The homework's measurement is what lets you make that judgment with numbers instead of vibes — which is the whole reason this week makes you measure rather than just read the docs' claims.

### 3.2 The sidecar surprises that page you

These are the failures every Istio operator hits, and the reason "it works without the sidecar" is a diagnosis, not a fix.

**The startup race.** A pod's app container may start and try to make network calls *before* the sidecar Envoy is ready to proxy them. Those early calls fail (no proxy to carry the mTLS), and the app may crash-loop or, worse, silently mis-behave. The fix is `holdApplicationUntilProxyStarts: true` (sidecar waits-for-ready before the app starts) — set it mesh-wide or per-pod. This is the most common "my app worked un-meshed and crash-loops meshed" cause, and it's the challenge this week.

**The job that exits before the sidecar.** A Kubernetes `Job` or `CronJob` runs to completion and exits — but the sidecar Envoy doesn't know the job is done and keeps running, so the pod never completes. The fix: the app signals the sidecar to exit (`/quitquitquit` on the Envoy admin, or the newer native sidecar-container support that makes the proxy a proper init-sidecar that terminates with the pod). If your batch jobs hang at "completed but not terminating" after meshing, this is why.

**The init-container-can't-reach-the-network trap.** istiod programs iptables to redirect traffic through the sidecar — but the sidecar isn't up during the *init* container phase. An init container that needs the network (waiting for a database, fetching config) finds its traffic redirected to a proxy that doesn't exist yet, and hangs. The fix is the Istio CNI plugin (which programs iptables differently) or excluding the init container's traffic. "My init container worked, then I meshed the namespace and it hangs" = this.

**Port naming.** Istio infers protocol from the Service port *name*. A port named `grpc-cart` or `http2` gets L7 treatment; a port named `tcp-cart` or unnamed gets L4 only — so your retries, routing, and HTTP-level authz silently don't apply. "My VirtualService route isn't taking effect" is, more often than anything else, a mis-named port. `istioctl analyze` flags it.

### 3.3 The debugging method

When a meshed pod misbehaves, the method is:

1. **`istioctl proxy-status`** — is the proxy SYNCED with istiod? STALE means the push didn't land.
2. **`istioctl x describe pod <pod>`** — effective mTLS, applied policies, route — the human-readable summary.
3. **`istioctl proxy-config {clusters,routes,listeners,endpoints} <pod>`** — the *actual* Envoy config (the Week 7 `/config_dump`, fetched via istioctl). Does the route you wrote actually exist on the proxy?
4. **`istioctl analyze`** — config mistakes (mis-named ports, hosts that don't resolve, policies in the wrong namespace).
5. **The sidecar logs** (`kubectl logs <pod> -c istio-proxy`) — `RBAC: access denied` (an authz policy), TLS errors (an mTLS mismatch), or upstream errors (the app, not the mesh).

The single discipline that ties all five steps together: **isolate mesh-from-app before you touch either.** Each step is really asking "is this the mesh's fault or the application's?" A STALE proxy, a missing route in `proxy-config`, an `analyze` warning, or an `RBAC: access denied` in the sidecar log all point at the *mesh*; an upstream 500 in the sidecar log with everything else green points at the *app*. The trap is starting to debug the application before you've ruled out the mesh — you'll add log lines to a service that's working fine while the real problem is a mis-named port the mesh silently treated as L4. Run the five steps in order, let them tell you which side owns the bug, and only then dig in. That ordering is what turns an afternoon of confusion into a five-minute diagnosis, and it's the same outside-in discipline every diagnostic chapter of this course teaches.

This is the same outside-in discipline as the C24 QoS decision tree or the Week 7 retry-storm hunt: read the proxy's ground truth, isolate mesh-vs-app, and resist the urge to "fix" it by removing the sidecar (which only confirms the problem is in the mesh config — it doesn't solve anything).

### 3.4 A worked debugging walk: "my AuthorizationPolicy isn't denying"

Make the method concrete with a common case. You applied an `AuthorizationPolicy` to deny everything but `cart`→`inventory`, but a test from `frontend` *still succeeds* — the deny isn't taking. Walk the tree:

```bash
# 1. Is the proxy in sync? A stale push means your policy didn't land yet.
istioctl proxy-status | grep inventory
# inventory-xxxxx.shop   SYNCED ...   -> good, the config reached it

# 2. Did the policy actually apply to this workload?
istioctl x describe pod -n shop inventory-xxxxx | grep -A3 "AuthorizationPolicy"
# (empty) -> the policy's selector doesn't match inventory's labels! Found it.
```

The bug: your `AuthorizationPolicy`'s `selector.matchLabels` was `app: inventory-svc` but the pods are labeled `app: inventory`. The policy is valid YAML, applied to the namespace, and selecting *nothing* — so it enforces nothing. `istioctl analyze` would have flagged it ("policy matches no workloads"), which is why it's step 1 of the method. The fix is one label, and the lesson is the recurring one: the CRD is intent, the proxy is truth, and the gap between them is almost always a selector, a namespace, or a port name. You confirm the fix the same way:

```bash
istioctl analyze -n shop                        # no warnings now
istioctl x describe pod -n shop inventory-xxxxx | grep AuthorizationPolicy
# inventory-allow-cart.shop   -> applied; now frontend gets RBAC: access denied
```

This exact shape — "the policy is there but it's selecting nothing / in the wrong namespace / on a mis-named port" — accounts for the large majority of "my Istio config isn't doing what I wrote" tickets. Internalize the three suspects (selector, namespace, port name) and the two tools (`analyze` then `x describe`) and you'll resolve them in minutes instead of an afternoon.

### 3.5 The honest operational ledger

To close the loop on "what does operating Istio actually cost," here is the ledger a platform team carries, beyond the per-request sidecar tax:

- **The control plane** — istiod must be HA and monitored; its availability gates cert rotation (Lecture 1 §5.2) and config pushes.
- **Upgrades** — Istio releases regularly; sidecar upgrades mean rolling every meshed pod (or, for ambient, the ztunnel DaemonSet), which is a recurring, careful operation.
- **Config sprawl** — `VirtualService`/`DestinationRule`/`AuthorizationPolicy`/`PeerAuthentication` across many namespaces is a lot of YAML to keep correct; `istioctl analyze` in CI is how you keep it honest.
- **The push cost at scale** — without `Sidecar` resources scoping what each proxy discovers, istiod pushes every service's config to every sidecar, and that cost grows super-linearly with mesh size. Scoping is a real scale technique, not a nicety.

None of this is a reason *not* to run Istio — it's the reason to run it *deliberately*, with the operational budget to do it well. An org that adopts Istio's power without staffing its operation gets a control plane nobody can upgrade and a config nobody can audit, which is worse than a simpler mesh or no mesh. That trade-off — power versus the cost of operating it — is exactly what next week's comparison against Linkerd and Cilium quantifies.

A compact way to remember the full cost of a sidecar mesh, for the homework's cost memo:

- **Per-request:** two extra proxy hops (latency, especially at the tail).
- **Per-pod:** the sidecar's resident memory, times your pod count.
- **Per-startup:** the sidecar-ready wait (and the startup-race risk).
- **Per-cluster:** istiod (HA, monitored), the injection webhook, the CA.
- **Per-release:** rolling every meshed pod to upgrade the proxy.
- **Per-change:** keeping a growing CRD set correct (`analyze` in CI).
- **Per-scale-up:** the config-push cost, unless scoped with `Sidecar` resources.

Ambient removes or shrinks the first three (no per-pod proxy for L4); the rest are the price of running a control plane at all, and they're the same shape for any mesh. Putting numbers on the first two — which the homework's measurement does — is what turns this ledger from a list of worries into a defensible cost line in an architecture decision.

---

## 4. Recap

You should now be able to:

- Pair `DestinationRule` (subsets + traffic policy) with `VirtualService` (routing + weights + faults) and explain which Envoy config each generates.
- Run a weighted canary (10/90 → 50/50 → 100/0) as cheap weight changes, and reason about automatic rollback via a progressive-delivery controller wired to an SLI.
- Inject latency and abort faults at the mesh to test caller resilience without touching app code — and remember to delete them.
- Read a canary, a fault, and an mTLS edge in Kiali, and explain why trace continuity still requires your app to propagate tracing headers.
- Quantify the sidecar tax (memory, latency, startup, ops) and articulate the ambient trade-off.
- Debug the four sidecar surprises (startup race, job-won't-exit, init-container trap, port naming) with `istioctl proxy-status`/`proxy-config`/`analyze`, treating the proxy's config as ground truth.

Next: the exercises put all of this on your cart/inventory topology. Continue to [the exercises](../03-exercises/00-overview.md).

---

## References

- *Istio — Traffic shifting (canary)*: <https://istio.io/latest/docs/tasks/traffic-management/traffic-shifting/>
- *Istio — Fault injection*: <https://istio.io/latest/docs/tasks/traffic-management/fault-injection/>
- *Istio — VirtualService reference*: <https://istio.io/latest/docs/reference/config/networking/virtual-service/>
- *Istio — DestinationRule reference*: <https://istio.io/latest/docs/reference/config/networking/destination-rule/>
- *Flagger — progressive delivery*: <https://docs.flagger.app/>
- *Istio — Common problems (sidecar)*: <https://istio.io/latest/docs/ops/common-problems/>
- *Kiali docs*: <https://kiali.io/docs/>
