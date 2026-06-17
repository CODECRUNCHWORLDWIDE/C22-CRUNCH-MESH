# Challenge 1 — The Sidecar That Wouldn't Start

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. A teammate moved the `order` service into the mesh this morning — labeled the namespace, redeployed — and now `order` is in `CrashLoopBackOff`. The app team is adamant: "we changed nothing, the image is identical, it ran fine yesterday." Someone has already discovered that if you remove the sidecar (un-label, redeploy), `order` runs perfectly — and is now lobbying to "just not mesh order," which would punch a hole in the compliance team's "mTLS on every hop" mandate.

Your job: prove the crash-loop is a **sidecar startup-ordering race** (not an app bug, not a mesh-wide outage), name the exact mechanism, and fix it **without** removing the sidecar. "Remove the sidecar" is not an answer — it's a surrender.

This mirrors the most common real Istio on-call scenario there is. A service that does work at startup — connect to a database, register with a discovery service, fetch config — fires that work *before* the sidecar Envoy is ready to carry it. The early calls fail (the proxy that's supposed to mTLS them doesn't exist yet), the app retries, exhausts its startup budget, and crash-loops. The fault is real, the app code is innocent, and the fix is one mesh setting — but only if you diagnose it correctly.

## The harness

Reproduce it. Deploy this `order` service into your meshed `shop` namespace. It does a "connect to dependency at startup" that fails if the network isn't ready — exactly the pattern that races the sidecar:

```yaml
# order-deploy.yaml — an app that calls a dependency AT STARTUP, before serving.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order
  namespace: shop
spec:
  replicas: 1
  selector: { matchLabels: { app: order } }
  template:
    metadata:
      labels: { app: order }
    spec:
      containers:
      - name: app
        image: curlimages/curl:latest
        command: ["/bin/sh", "-c"]
        args:
        - |
          echo "startup: calling dependency BEFORE serving..."
          # This call races the sidecar. If the proxy isn't up, iptables has
          # already redirected this traffic to a proxy that doesn't exist -> it
          # hangs/fails, and the startup script exits non-zero -> CrashLoopBackOff.
          curl -sS --max-time 5 http://inventory.shop.svc.cluster.local:50051/ \
            || { echo "startup dependency call FAILED"; exit 1; }
          echo "dependency reachable; now serving forever"
          sleep 100000
        # Make the race reliable: no startup grace, fail fast.
      terminationGracePeriodSeconds: 1
```

```bash
kubectl apply -f order-deploy.yaml
kubectl get pods -n shop -w
# order-xxxxx   0/2   ...   CrashLoopBackOff   (the app container keeps exiting 1)
```

You now have the bug. Diagnose it from the outside before reading the fix section.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Symptom** — exactly what you observe: pod status, restart count, which container is failing (`app` or `istio-proxy`?), and the relevant lines from the app container's logs and the pod events.
2. **Proof it's the race, not an app bug** — the specific evidence that the *app* is fine and the *timing* is wrong. (Hint: the app's own log says the dependency call failed at startup. Now check: was the sidecar even ready when that call fired? Compare the app container's start time to the istio-proxy's ready time. And: does the same dependency call *succeed* once you exec into a healthy meshed pod and run it by hand? If yes, the network path is fine when the proxy is up — so it's timing.)
3. **The mechanism** — name it precisely: iptables redirection is programmed by the init phase, but the sidecar Envoy that traffic is redirected *to* isn't ready until after the app container can start; the app's startup network call hits a not-yet-listening proxy and fails.
4. **The fix** — set `holdApplicationUntilProxyStarts: true` so the app container does not start until the sidecar reports ready. Show it applied and the pod going `2/2 Running`.
5. **Prevention** — one process change so meshing a service never causes this again (e.g., "set `holdApplicationUntilProxyStarts` mesh-wide in the install" or "startup dependency calls must tolerate a not-ready proxy with a bounded retry").

You must reach the diagnosis with **at least two** independent signals — e.g., the app log's "dependency call failed" *and* the proxy-not-ready timing, or the events showing the app container restarting while the proxy is still starting *and* the by-hand call succeeding once the proxy is up. One signal is a guess; two is a diagnosis.

## The fix, applied

Per-pod, via an annotation:

```yaml
# Add to the pod template metadata:
metadata:
  labels: { app: order }
  annotations:
    proxy.istio.io/config: |
      holdApplicationUntilProxyStarts: true
```

Or mesh-wide, in the IstioOperator/mesh config:

```yaml
# values.global.proxy or meshConfig.defaultConfig:
meshConfig:
  defaultConfig:
    holdApplicationUntilProxyStarts: true
```

Re-apply, and the app container now waits for the sidecar before its startup script runs:

```bash
kubectl rollout restart deploy/order -n shop
kubectl get pods -n shop
# order-xxxxx   2/2   Running   0   30s     <-- the race is gone
```

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You quote the app container's startup log (the failed dependency call) AND demonstrate the sidecar was not ready when it fired (timing from `kubectl describe pod` events or container start timestamps).
- [ ] You demonstrate the SAME dependency call SUCCEEDS from a healthy meshed pod (`kubectl exec ... curl ...`) — proving the network path is correct once the proxy is up, so the cause is timing, not connectivity.
- [ ] Your fix is `holdApplicationUntilProxyStarts: true` (or the native sidecar-container ordering), NOT removing the sidecar. The pod reaches `2/2 Running`.
- [ ] A `order-fixed.yaml` — the corrected manifest — checked in.
- [ ] Committed to your Week 8 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong "fixes" you must NOT write:

- **"Un-mesh the service."** This makes the crash-loop disappear by removing the very thing — the sidecar — that you adopted the mesh to get. The service now has no mTLS, violating the mandate. Worse, it teaches the org that "meshing breaks things," which poisons the rollout. Removing the sidecar to make a sidecar problem go away is not a fix; it's confirming the diagnosis and then quitting.
- **"Add a long `sleep` before the app's startup call."** This *masks* the race by guessing a duration. It's flaky (the sidecar's ready time varies with node load), it slows every startup, and it breaks the day the sidecar takes a half-second longer. The correct fix waits on the actual readiness signal (`holdApplicationUntilProxyStarts`), not a hard-coded delay.

A related real-world cousin worth naming in your writeup: the **job-that-won't-terminate** problem (a `Job` finishes but the sidecar keeps running, so the pod never completes). It's the same family — sidecar lifecycle vs app lifecycle — with the opposite timing, and the native sidecar-container support (proxy as a proper init-sidecar) fixes both ends.

## Stretch

- Reproduce the **init-container trap**: add an init container to `order` that does a network call (e.g., waits for a database). With the default iptables interception it hangs (traffic redirected to a not-yet-existent proxy). Fix it with the Istio CNI plugin and explain the difference.
- Reproduce the **port-naming bug**: name the order Service port `tcp-order` instead of `grpc-order` and show that your `VirtualService` route silently doesn't apply (L4-only treatment). `istioctl analyze` flags it; quote the warning.
- Try the same `order` service in **ambient mode** (no sidecar at all). Does the startup race exist there? Explain why ambient's per-node ztunnel changes the startup-ordering picture — and what it costs you (no per-pod L7 without a waypoint).

## Why this matters

Every mesh adoption hits this wall: a service that worked breaks when meshed, and the team's instinct is to blame the mesh and back out. The difference between a mesh rollout that succeeds and one that gets reverted is whether *someone* can stand in front of the room and say "this is a known startup-ordering race, here's the one-line fix, the app is fine and the mesh stays." This challenge is that moment, rehearsed. When you defend your `cart-mesh` at the Phase 2 review, "I know exactly why meshing a service can crash-loop it and how to fix it without un-meshing" is the line that says you've operated a mesh, not just installed one.
