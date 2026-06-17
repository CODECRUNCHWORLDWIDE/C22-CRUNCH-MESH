# Week 7 — Service-to-Service: BFFs, Gateways, and Envoy

Welcome to the week the network stops being free. For six weeks you had one hardened service. Now there are two, and the moment a second service exists, every assumption you made about a function call — that it returns, that it returns quickly, that it returns *correctly* — becomes a negotiation across a wire that drops packets, reorders them, and occasionally just stops. This week you learn the substrate that makes that negotiation survivable: **Envoy**, the proxy that sits in front of, between, and eventually inside every service you will run for the rest of this course.

We assume you finished Phase 1. You have a `cart` service in Go and an `inventory` service that talk gRPC over a typed `cart.v1` / `inventory.v1` contract. They have probes, structured logs, and OpenTelemetry baseline traces. If that is not true — if your services still log to stdout as unstructured text and crash on SIGTERM — go back to Week 6 first. Everything this week assumes a service that is *already* production-shaped; we are adding the network tier, not fixing the service.

The one thing to internalize before you read another line: **a gateway is not a mesh, and most teams reach for a mesh when a gateway would have done.** An API gateway is a single front door — north-south traffic, the edge between the internet and your services. A service mesh is the *entire* internal network — east-west traffic, every service-to-service hop, mTLS everywhere, with a sidecar per pod. They share a data plane (both are usually Envoy) but they solve different problems, and the cost of a mesh — a sidecar's memory and latency tax on every single pod — is one you should pay deliberately, not by reflex. This week you build the gateway and the BFF. Weeks 8 and 9 build the mesh. By the end of the three you will know, in your gut, when each is the right tool.

This week is where you stop treating the network as a detail.

## Learning objectives

By the end of this week, you will be able to:

- **Distinguish** an API gateway (north-south, edge) from a service mesh ingress (east-west, internal) and state precisely which problem each solves — and when a gateway alone is enough.
- **Read and write** an Envoy static bootstrap config at the level of listeners, filter chains, routes, and clusters, and explain how the same shapes appear as xDS-delivered dynamic config (LDS/RDS/CDS/EDS).
- **Explain** the Envoy threading model — the main thread, the worker threads, the thread-local cluster manager — and why it means config updates are eventually consistent across workers and never block the data path.
- **Configure** the production resilience primitives at the proxy: retries with a retry budget and hedging, per-route timeouts, outlier detection (passive health checking), and a circuit breaker — and state what each one does *not* protect you from.
- **Design** a BFF (backend-for-frontend) for a specific client — a mobile app — that aggregates several gRPC backends behind one tailored surface, and justify why it is a *separate* deployable from the web BFF.
- **Choose** between gRPC-Web and Connect for browser clients, and configure the proxy-side transcoding that lets a browser talk to a gRPC backend at all.
- **Apply** rate limiting and quota at the edge — local (per-instance) token buckets and a global rate-limit service — and reason about where each belongs.
- **Compare** Envoy against Kong and Tyk honestly, and articulate why Envoy is the data plane underneath most of the others in 2026.

## Prerequisites

This week assumes you have completed **C22 weeks 1–6**, or have equivalent fluency. Specifically:

- A working **Kubernetes** cluster locally — **Kind** is what the examples target (`kind create cluster` works; `kubectl get nodes` is Ready). k3d or minikube are fine if you adapt the manifests.
- The **`cart`** and **`inventory`** services from Phase 1, containerized and deployable to your cluster, exposing gRPC over the `cart.v1` / `inventory.v1` contracts.
- **`grpcurl`** installed, and you can call a gRPC method against a running service from the command line.
- Comfort with **Go** at the level of writing an HTTP/gRPC server with middleware — the BFF exercise is Go.
- The **rcl of containers**: you can read a `Dockerfile`, build an image, load it into Kind (`kind load docker-image`), and write a `Deployment` + `Service` manifest from a template.
- You understand **HTTP/2** at the conceptual level from Week 5: streams, multiplexing, why gRPC rides on it.

You do **not** need prior Envoy experience. We start at the static bootstrap and build up to xDS, resilience, and the BFF. If you have only ever seen Envoy as "the thing Istio installs," this is the week it becomes a tool you configure on purpose.

## Topics covered

- **Gateway vs mesh ingress**: north-south versus east-west, the edge proxy versus the per-pod sidecar, and the decision criteria. Where Gateway API (the Kubernetes-native successor to Ingress) fits.
- **Envoy architecture**: listeners, filter chains, network filters vs HTTP filters, the router filter, route configuration, clusters, and endpoints. The four xDS APIs — **LDS** (listeners), **RDS** (routes), **CDS** (clusters), **EDS** (endpoints) — and ADS (aggregated) as the way you actually run them.
- **The Envoy threading model**: a single non-blocking main thread for config and stats, N worker threads each running an event loop and owning their connections, the thread-local cluster manager, and the consequence — config is applied per-worker, so updates are eventually consistent and never stall live connections.
- **Resilience at the proxy**: per-route timeouts, retries with `retry_on` conditions, the **retry budget** (so retries can't amplify an outage), request hedging, **outlier detection** (eject a host that returns 5xx or trips consecutive gateway failures), and **circuit breakers** (bound concurrent connections, requests, retries, and pending requests per cluster).
- **The BFF pattern**: one backend-for-frontend per client class (web, mobile), each a thin aggregation layer over the gRPC backbone, owned by the client team, tailoring the payload to the device's screen and network. Why a shared "API layer" for all clients re-creates the distributed monolith.
- **Browser access to gRPC**: **gRPC-Web** (the older transcoding standard, needs a proxy) versus **Connect** (the newer protocol from Buf that speaks gRPC, gRPC-Web, and its own HTTP/1.1-friendly protocol from one handler). Envoy's `grpc_web` filter and the `grpc_json_transcoder` for REST-to-gRPC.
- **Rate limiting and quota**: the local rate-limit filter (per-instance token bucket, cheap, no network hop) versus the global rate-limit service (a shared RLS over gRPC, correct under horizontal scale, one network hop per decision). Quota, 429s, and `Retry-After`.
- **The honest vendor comparison**: Kong (Lua/Nginx heritage, now also Envoy-adjacent), Tyk (Go, API-management-first), and why Envoy is the data plane that the cloud-native gateways and every major mesh build on in 2026.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Gateway vs mesh; Envoy architecture; listeners/clusters |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | The threading model; static config; first proxy hop    |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Resilience: timeouts, retries, outlier detection, CB   |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | The BFF pattern; gRPC-Web vs Connect; the aggregation  |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Rate limiting; the gateway-vs-mesh decision memo       |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                 |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, memo polish                              |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The Envoy docs, the CNCF gateway landscape, the talks worth your time |
| [lecture-notes/01-envoy-architecture-and-the-edge.md](./02-lecture-notes/01-envoy-architecture-and-the-edge.md) | Gateway vs mesh, Envoy listeners/filters/clusters, xDS, the threading model |
| [lecture-notes/02-resilience-bffs-and-the-browser.md](./02-lecture-notes/02-resilience-bffs-and-the-browser.md) | Timeouts, retries, outlier detection, circuit breakers, the BFF pattern, gRPC-Web vs Connect, rate limiting |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-envoy-ingress.md](./03-exercises/exercise-01-envoy-ingress.md) | Stand up Envoy as an ingress in front of `cart` and `inventory`; verify the proxy hop end-to-end |
| [exercises/exercise-02-resilience-policy.yaml](./03-exercises/exercise-02-resilience-policy.yaml) | A complete Envoy config with per-route retries+budget, timeouts, outlier detection, and a circuit breaker — runnable |
| [exercises/exercise-03-mobile-bff.go](./03-exercises/exercise-03-mobile-bff.go) | A Go mobile BFF that fans out to `cart` and `inventory` over gRPC and returns one tailored response |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-tame-the-retry-storm.md](./04-challenges/challenge-01-tame-the-retry-storm.md) | Diagnose and stop a retry-amplified outage on a live proxy chain |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the gateway-vs-mesh decision memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | The `cart-edge` gateway: Envoy + a Go BFF + a global rate limiter, fully audited |

## The "the proxy is doing its job" promise

C22 uses a recurring marker for every exercise that ends in the proxy actually shaping traffic the way you told it to. The canonical one this week is the Envoy admin stats endpoint:

```
$ curl -s localhost:9901/stats | grep -E "cart.*(upstream_rq_retry|upstream_rq_timeout|outlier)"
cluster.cart.upstream_rq_retry: 4
cluster.cart.upstream_rq_retry_limit_exceeded: 0
cluster.cart.upstream_rq_timeout: 0
cluster.cart.outlier_detection.ejections_active: 0
```

If `upstream_rq_retry_limit_exceeded` is climbing, your retry budget is doing its job — it is *refusing* to retry past the budget, which is exactly what stops a retry storm. If `outlier_detection.ejections_active` is non-zero, the proxy has ejected a bad host and is routing around it. The point of this week is to make these numbers something you read on purpose, the way a backend engineer reads an HTTP status code — and to make a *silently* misconfigured proxy (retries with no budget, a timeout longer than the client's) something you catch before it pages you.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Envoy "Life of a Request"** document end to end until you can narrate a request's path through listener → filter chain → router → cluster → endpoint from memory: <https://www.envoyproxy.io/docs/envoy/latest/intro/life_of_a_request>.
- Stand up a tiny **xDS control plane** with `go-control-plane` that serves your listener and cluster config over ADS, and watch Envoy hot-reload a route change with zero dropped connections. This is the seam every mesh control plane plugs into.
- Replace the gRPC-Web filter with a **Connect** backend (`connectrpc.com/connect-go`) and prove a browser `fetch()` can call it directly with no Envoy transcoding at all — then articulate the trade-off you just made.
- Run the global rate-limit service (`envoyproxy/ratelimit` backed by Redis) and prove that two Envoy replicas share one quota — the thing a per-instance limiter gets wrong the moment you scale out.

## Up next

Week 8 takes the Envoy literacy you built here and pushes it *inside* the pod. **Istio** is Envoy-as-sidecar with a control plane (istiod) that turns the static and xDS config you hand-wrote this week into CRDs — `VirtualService`, `DestinationRule`, `AuthorizationPolicy` — and gives you mTLS on every hop for free. Everything you configured by hand this week, Istio will configure for you; this week is what makes Istio legible instead of magic. Push your `cart-edge` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
