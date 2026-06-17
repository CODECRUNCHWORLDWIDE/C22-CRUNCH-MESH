# Week 8 — Istio in Production

Welcome to the week the proxy goes inside the pod. Last week you hand-wrote Envoy config: listeners, clusters, retries, a budget. This week a control plane writes all of it for you, on every pod, and gives you mutual TLS on every hop as a side effect of installation. That control plane is **Istio**, and this is the week it stops being the thing that "magically does mesh stuff" and becomes a system you operate, debug, and — crucially — know when *not* to use.

We assume you finished Week 7. You have `cart` and `inventory` as gRPC services behind an Envoy gateway, and you can read an Envoy `/config_dump` and tell whether a cluster has a retry budget. That literacy is load-bearing this week, because **Istio's sidecar *is* Envoy**, and everything you configured by hand last week, Istio now configures via CRDs. When you write a `DestinationRule`, you are writing an Envoy cluster's circuit breaker. When you write a `VirtualService`, you are writing an Envoy route. The mesh is a translator; last week you learned the target language so this week you can read what the translator produces.

The one thing to internalize before you read another line: **a service mesh is not free, and the headline cost is the sidecar — a full Envoy on every pod, taxing memory and adding a hop to every request.** Istio's answer to that cost in 2026 is **ambient mode**: a mesh with *no* per-pod sidecar, using a per-node L4 proxy (ztunnel) and an optional per-namespace L7 proxy (the waypoint). You will run both the classic sidecar mode and ambient mode this week, measure the difference, and leave able to argue which one a given workload should use. The mesh you adopt by reflex is a liability; the mesh you adopt deliberately, knowing its cost, is the thing that gives a 15-team org uniform mTLS without 15 chances to get it wrong.

This week is where you stop being impressed by Istio and start being responsible for it.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** Istio's architecture — istiod as the unified control plane, the Envoy sidecar (or ambient ztunnel + waypoint) as the data plane — and trace how a Kubernetes Service and a CRD become Envoy config pushed over xDS.
- **Distinguish** sidecar mode from ambient mode precisely: what each costs (per-pod Envoy vs per-node ztunnel), what each can do (sidecar gets full L7 always; ambient gets L4 free and L7 only via a waypoint), and which workloads belong on each.
- **Enable** mTLS across the mesh with `PeerAuthentication` in `STRICT` mode, explain the permissive-to-strict migration path, and verify on the wire that traffic is actually encrypted.
- **Write** `AuthorizationPolicy` to enforce service-to-service access (deny-by-default, then allow specific principals), and reason about the difference between authentication (who you are) and authorization (what you may do).
- **Shape traffic** with `VirtualService` and `DestinationRule`: define subsets, shift weighted traffic for a canary (10/90 → 50/50 → 100/0), and pin the destination's load-balancing and outlier detection.
- **Perform** a mesh-driven progressive rollout and reason about automatic rollback on an SLO breach (the seam Flagger/Argo Rollouts plug into).
- **Inject** faults at the mesh layer (latency and aborts via `VirtualService`) to test resilience without touching application code, and observe the blast radius in Kiali.
- **Debug** the sidecar surprises that bite every Istio operator: the `holdApplicationUntilProxyStarts` race, the mesh-excludes-the-init-container trap, `istioctl proxy-config` as the ground truth, and why "it works without the sidecar" is a diagnosis, not a fix.

## Prerequisites

This week assumes you have completed **C22 weeks 1–7**, or have equivalent fluency. Specifically:

- A working **Kind** cluster with enough headroom for Istio (the demo profile wants ~4 GB free; ambient is lighter). `kubectl get nodes` is Ready.
- The **`cart`** and **`inventory`** services from Phase 1, deployable to the cluster as gRPC servers with readiness/liveness probes (Week 6).
- **`istioctl`** installed (`istioctl version` works) — the CLI you'll use to install the mesh and to introspect sidecars.
- The **Envoy literacy from Week 7**: you can read a `/config_dump`, and you know what a cluster, route, retry budget, and outlier-detection block are. Istio CRDs map onto exactly these.
- Comfort with **Kubernetes CRDs and namespaces**: you can `kubectl apply` a custom resource, label a namespace, and read `kubectl describe` output.
- `grpcurl` and a load generator (`fortio` ships with Istio's samples; `ghz` works too).

You do **not** need prior Istio experience. We start at the install and build up to mTLS, authorization, canary, and the sidecar debugging that separates an operator from a tutorial-follower.

## Topics covered

- **Istio architecture**: istiod (the merged Pilot/Citadel/Galley control plane) — config validation, certificate issuance (the CA), and xDS push to the data plane. The sidecar injection webhook. The CNI plugin and the init-container that sets up iptables redirection.
- **Sidecar vs ambient mode**: the per-pod Envoy sidecar (full L7 on every hop, at a memory and latency cost) versus ambient's split data plane — **ztunnel** (a per-node L4 proxy carrying mTLS for everyone, cheaply) plus the **waypoint** proxy (a per-namespace/per-service L7 Envoy you add only where you need L7 policy). Why ambient exists and what it trades away.
- **mTLS by default**: `PeerAuthentication` (`STRICT`, `PERMISSIVE`, `DISABLE`), the SPIFFE identity baked into each workload's certificate, automatic certificate rotation, and the permissive-to-strict migration that lets you turn on mTLS without an outage.
- **Authorization**: `AuthorizationPolicy` — deny-by-default semantics, allow rules keyed on source principal (the SPIFFE identity), namespace, and request properties; the layering of `PeerAuthentication` (authn) under `AuthorizationPolicy` (authz).
- **Traffic management**: `VirtualService` (routing, weighted splits, header/URI matching, retries, timeouts, fault injection) and `DestinationRule` (subsets, load-balancing policy, connection pools, outlier detection) — and how they correspond to the Envoy routes and clusters you wrote by hand in Week 7.
- **Progressive delivery**: weighted canary by subset, the 10/90 → 50/50 → 100/0 rollout, and automatic rollback on an SLO breach via Flagger or Argo Rollouts driving the `VirtualService` weights.
- **Fault injection at the mesh**: injecting fixed-delay latency and HTTP/gRPC aborts into a route to test caller resilience, and watching the effect propagate in **Kiali** (the mesh's service-graph and traffic visualizer) and the distributed traces.
- **The sidecar surprises**: startup ordering (`holdApplicationUntilProxyStarts`, jobs that exit before the sidecar, the init-container-can't-reach-the-network trap), `istioctl proxy-config`/`proxy-status` as ground truth, the cost of sidecars at scale, and the "ambient because the sidecar tax is real" decision.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Istio architecture; istiod; sidecar vs ambient         |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Install on Kind; inject the mesh; mTLS STRICT          |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | VirtualService + DestinationRule; the weighted canary  |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | AuthorizationPolicy; fault injection; Kiali            |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Sidecar debugging; the cost-of-sidecars measurement    |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                 |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, postmortem polish                        |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Istio docs, the ambient-mesh material, the talks worth your time |
| [lecture-notes/01-istio-architecture-and-mtls.md](./02-lecture-notes/01-istio-architecture-and-mtls.md) | istiod, sidecar vs ambient, mTLS with PeerAuthentication, and AuthorizationPolicy |
| [lecture-notes/02-traffic-management-canary-and-the-sidecar-tax.md](./02-lecture-notes/02-traffic-management-canary-and-the-sidecar-tax.md) | VirtualService/DestinationRule, weighted canary, fault injection, Kiali, and debugging the sidecar |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-install-and-mtls.md](./03-exercises/exercise-01-install-and-mtls.md) | Install Istio on Kind, inject cart+inventory, turn on mTLS STRICT, and prove encryption on the wire |
| [exercises/exercise-02-weighted-canary.yaml](./03-exercises/exercise-02-weighted-canary.yaml) | A complete VirtualService + DestinationRule canary: subsets, 10/90 → 50/50 → 100/0, plus fault injection |
| [exercises/exercise-03-authz-probe.py](./03-exercises/exercise-03-authz-probe.py) | Apply a deny-by-default AuthorizationPolicy and probe it — prove allowed calls pass and denied calls get RBAC: access denied |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-sidecar-that-wouldnt-start.md](./04-challenges/challenge-01-the-sidecar-that-wouldnt-start.md) | Diagnose a pod stuck because of a sidecar startup-ordering race, from the outside |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the sidecar-vs-ambient cost memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | `cart-mesh`: the cart topology in the mesh with mTLS, authz, a canary, and a measured ambient comparison |

## The "the mesh is actually enforcing it" promise

C22 uses a recurring marker for every exercise that ends in the mesh actually doing what you declared. This week's canonical one is `istioctl` proving mTLS is real, not assumed:

```
$ istioctl proxy-config secret deploy/cart -o json | jq '.dynamicActiveSecrets[].name'
"default"
"ROOTCA"

$ istioctl x describe pod $(kubectl get pod -l app=cart -o name | head -1 | cut -d/ -f2)
...
Effective PeerAuthentication: STRICT
Applied PeerAuthentication:
   default.istio-system
Skipping Gateway information (no ingress gateway found)
```

If `Effective PeerAuthentication` says `STRICT`, the mesh is encrypting and refusing plaintext on that workload — verifiable, not vibes. The point of this week is to make these `istioctl` checks ordinary, the way you made `ros2 topic info -v` ordinary if you came through C24 — and to make a *silently* permissive mesh (a `PeerAuthentication` that didn't apply because of a namespace-label typo) something you catch before an auditor does.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Istio ambient mesh architecture** page until you can draw the ztunnel/waypoint split from memory and state exactly when a request needs a waypoint: <https://istio.io/latest/docs/ambient/architecture/>.
- Stand up **Flagger** (or Argo Rollouts) and let it drive the canary `VirtualService` weights automatically, rolling forward on healthy metrics and **rolling back on an induced error-rate breach**. This is the capstone's progressive-delivery story.
- Measure the **sidecar tax** rigorously: p50/p99 latency and per-pod memory with sidecars, then the same workload in ambient mode. Put numbers on "the sidecar costs something."
- Write a `Sidecar` resource to **scope** what each workload's sidecar discovers (a real scale technique — without it, every sidecar gets config for every service in the mesh, which is how istiod's push cost explodes at hundreds of services).

## Up next

Week 9 takes the mesh literacy you built here and asks the honest comparative question: **Istio is not the only mesh.** Linkerd (a Rust micro-proxy, sidecar-per-pod, ruthlessly simple) and Cilium (mesh on eBPF, no per-pod proxy at all) make different bets. You'll reinstall the same cart topology on each, measure the latency overhead against your Istio numbers, and write the ADR that recommends one of the three to a real org. Everything you learned this week about what a mesh *does* is what lets you compare *how* each one does it. Push your `cart-mesh` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
