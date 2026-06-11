# Week 8 — Exercises

Three focused drills on a running Istio mesh. Each takes 45–90 minutes. Do them in order — exercise 2 (the canary) routes the traffic that exercise 1 put behind mTLS, and exercise 3 (authz) gates the calls exercise 2 routes. Run everything against your **`cart` and `inventory`** services from Phase 1, deployed into a meshed namespace on Kind (or, if your services aren't ready, the Istio sample apps each exercise names as a fallback).

## Index

1. **[Exercise 1 — Install Istio and turn on mTLS STRICT](exercise-01-install-and-mtls.md)** — install the mesh on Kind, inject `cart` and `inventory`, flip the namespace to `STRICT`, and prove encryption on the wire three ways. (~75 min, guided)
2. **[Exercise 2 — The weighted canary](exercise-02-weighted-canary.yaml)** — a complete `DestinationRule` + `VirtualService` that shifts cart traffic 10/90 → 50/50 → 100/0 across v1/v2 subsets, with a fault-injection stanza to test caller resilience. (~60 min, runnable)
3. **[Exercise 3 — The authorization probe](exercise-03-authz-probe.py)** — apply a deny-by-default `AuthorizationPolicy` plus an explicit allow, then probe it: prove the allowed principal passes and a different principal gets `RBAC: access denied`. (~60 min, runnable)

## How to work the exercises

- Have **`istioctl`** installed and a **Kind** cluster with headroom (the demo profile wants ~4 GB free; ambient is lighter). `istioctl version` and `kubectl get nodes` both work.
- Have your **`cart` and `inventory`** services deployable into a namespace. If they're not ready, the Istio `samples/bookinfo` or `samples/httpbin` apps stand in — each exercise notes the substitution.
- **Read `istioctl` before and after every change.** `istioctl proxy-status`, `istioctl x describe pod`, and `istioctl proxy-config` are your ground truth — the mesh equivalent of last week's `/config_dump`. Train the habit of confirming the proxy actually got the config, not just that you applied the CRD.
- When the mesh "isn't working," run `istioctl analyze` first (it catches the typo'd port name, the wrong-namespace policy), then `proxy-status` (did the push land?), then the sidecar logs. In that order.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match, you're not done.

## Running the exercises

The `.yaml` exercise is applied with `kubectl`:

```bash
kubectl apply -f exercise-02-weighted-canary.yaml
istioctl proxy-config routes deploy/cart -o json | jq '.[].virtualHosts[].routes[].route.weightedClusters'
```

The `.py` exercise is a standard Python script that runs probes against the mesh:

```bash
pip install grpcio
python3 exercise-03-authz-probe.py
```

The header of each file lists the exact prerequisites. If your Phase 1 protos aren't generated, the file's header points you at the minimal stand-in.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-08` to compare.
