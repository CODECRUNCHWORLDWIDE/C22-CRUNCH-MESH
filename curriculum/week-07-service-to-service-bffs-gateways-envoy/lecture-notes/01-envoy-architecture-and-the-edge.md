# Lecture 1 — Envoy Architecture and the Edge: Listeners, Clusters, and the Threading Model

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can distinguish a gateway from a mesh, read and write an Envoy static config at the listener/filter/cluster level, explain how the same shapes are delivered dynamically over xDS, and describe the threading model precisely enough to predict how a config update propagates.

If you remember one sentence from this lecture, remember this one:

> **Envoy has exactly four nouns — listeners, routes, clusters, endpoints — and everything else, including every service mesh you will ever run, is a control plane that generates those four nouns and ships them to a fleet of Envoys over xDS.**

Once you see Envoy as those four nouns, Istio stops being magic. Istio's `VirtualService` *becomes* a route. Its `DestinationRule` *becomes* a cluster's load-balancing and circuit-breaking config. Its `Gateway` *becomes* a listener. The mesh is a translator from human-friendly CRDs to Envoy config. This week you write the Envoy config by hand so that next week, when Istio writes it for you, you can read what it produced and tell whether it's right.

---

## 1. Gateway vs mesh: two different problems

Before any YAML, get the geography straight, because the single most expensive architecture mistake in this phase is reaching for a mesh when a gateway would have done.

### 1.1 North-south vs east-west

- **North-south traffic** is the edge: requests crossing the boundary between the outside world (browsers, mobile apps, partner APIs) and your services. It is *asymmetric* — untrusted client on one side, your services on the other — so it is where authentication, TLS termination, rate limiting, WAF, and request shaping live. The component that owns north-south is an **API gateway**.

- **East-west traffic** is internal: `cart` calling `inventory`, `order` calling `payment`. It is *symmetric* — both sides are your services, mutually authenticated, and you want uniform mTLS, retries, and observability on *every* hop. The component that owns east-west is a **service mesh**, which puts a proxy (a **sidecar**) next to every service instance.

```
            ┌──────────── north-south (the edge) ────────────┐
            │                                                 │
  browser ──┼──► [ API GATEWAY ] ──► cart                     │
  mobile  ──┘         (Envoy)         │                       │
                                      │  east-west (internal) │
                                      ▼                       │
                                   inventory ◄── payment      │
                                      ▲           ▲           │
            └─────────── these hops are the mesh's domain ────┘
                         (a sidecar proxy beside each pod)
```

### 1.2 The decision criterion

The honest rule a senior engineer gives in 2026:

> **You almost always need a gateway. You need a mesh when you have enough services that uniform east-west mTLS, retries, and telemetry — applied *without* asking every service team to implement them — is worth a sidecar's tax on every pod.**

The mesh's cost is real: a sidecar adds memory (tens to ~100 MB per pod), adds a small per-hop latency (a fraction of a millisecond to a couple of milliseconds, depending on the proxy and protocol), and adds operational surface (the control plane, sidecar injection, certificate rotation). For three services, that tax buys you little a gateway plus a shared library couldn't. For three hundred services across forty teams, the mesh is how you get mTLS and golden-signal telemetry everywhere without forty teams each doing it slightly wrong. This week: the gateway and the BFF. Weeks 8–9: the mesh, deliberately.

A note on **Gateway API**: the Kubernetes `Ingress` resource is being superseded by the **Gateway API** (`Gateway`, `HTTPRoute`, `GRPCRoute`), a richer, role-oriented standard. Envoy Gateway implements it, and so does Istio's ingress. You'll meet it in the resources; conceptually it is just a friendlier way to declare the same listeners and routes.

---

## 2. The four nouns

Here is the whole of Envoy, in four definitions. Everything else is detail.

| Noun | What it is | Delivered by |
|---|---|---|
| **Listener** | A bound socket (address + port) and the filter chain that processes connections on it | LDS |
| **Route** | The rules that map an incoming request (by host, path, headers) to a cluster, with per-route timeout/retry/split | RDS |
| **Cluster** | A named upstream service: a set of endpoints, a load-balancing policy, a connection pool, health checks, and circuit breakers | CDS |
| **Endpoint** | One concrete upstream host:port inside a cluster | EDS |

A request's life, in one line: it arrives on a **listener**, passes through that listener's **filter chain**, the router filter matches it against the **route** table to pick a **cluster**, and the cluster's load balancer selects an **endpoint** to forward to.

### 2.1 A complete static bootstrap, annotated

Here is a minimal but *complete* Envoy config that fronts the `cart` service. It is `static_resources` — everything inline, no control plane. Read every block; this is the shape you will see again as xDS.

```yaml
# envoy-static.yaml — Envoy as an ingress in front of the cart service.
# Run with: func-e run -c envoy-static.yaml
admin:
  address:
    socket_address: { address: 0.0.0.0, port_value: 9901 }   # /stats, /clusters, /config_dump

static_resources:
  listeners:
  - name: ingress_http
    address:
      socket_address: { address: 0.0.0.0, port_value: 10000 }
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          codec_type: AUTO                 # detect HTTP/1.1, HTTP/2, or h2c
          route_config:
            name: local_route
            virtual_hosts:
            - name: backend
              domains: ["*"]
              routes:
              - match: { prefix: "/cart.v1.CartService/" }   # gRPC: package-qualified path
                route:
                  cluster: cart
                  timeout: 2s                                 # per-route deadline
              - match: { prefix: "/" }
                route: { cluster: cart }
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
  - name: cart
    type: STRICT_DNS                       # resolve the endpoint by DNS (k8s Service name)
    connect_timeout: 1s
    lb_policy: ROUND_ROBIN
    typed_extension_protocol_options:      # speak HTTP/2 upstream (gRPC needs it)
      envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
        "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
        explicit_http_config:
          http2_protocol_options: {}
    load_assignment:
      cluster_name: cart
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address: { address: cart.default.svc.cluster.local, port_value: 50051 }
```

Walk it top to bottom:

- **`admin`** — the operational endpoint on `:9901`. `curl localhost:9901/config_dump` returns the *running* config (the source of truth, which may differ from your file once xDS is in play); `/stats` is every counter; `/clusters` shows each cluster's endpoints and their health. You will live in `/stats`.
- **`listeners[0]`** binds `0.0.0.0:10000`. Its single filter chain has one network filter: the **HttpConnectionManager (HCM)**. The HCM is the heart of an HTTP listener — it parses bytes into HTTP, runs the HTTP filter chain, and at the end runs the **router** filter that actually forwards.
- **`route_config`** — one virtual host matching all domains, with two routes. The first matches the gRPC service path prefix (`/cart.v1.CartService/`) and sets a 2-second timeout; the second is the catch-all. Order matters: Envoy takes the first matching route.
- **`http_filters`** — here just the router. In real configs this list grows: a gRPC-Web filter, a rate-limit filter, a CORS filter, all *before* the router (the router must be last; it terminates the chain).
- **`clusters[0]`** — the `cart` upstream. `STRICT_DNS` means Envoy resolves `cart.default.svc.cluster.local` and load-balances across every A record. `http2_protocol_options: {}` is **mandatory for gRPC** — without it Envoy speaks HTTP/1.1 upstream and your gRPC calls fail with a confusing error. This is the single most common first-day Envoy-and-gRPC mistake.

### 2.2 The same config, dynamically (xDS)

Now replace `static_resources` with `dynamic_resources`. The shapes are identical; the *delivery* changes — a control plane streams them over gRPC.

```yaml
# envoy-dynamic.yaml — listeners and clusters come from a control plane over ADS.
node:
  id: cart-edge-1
  cluster: cart-edge

dynamic_resources:
  ads_config:
    api_type: GRPC
    transport_api_version: V3
    grpc_services:
    - envoy_grpc: { cluster_name: xds_cluster }
  cds_config: { ads: {}, resource_api_version: V3 }     # clusters via ADS
  lds_config: { ads: {}, resource_api_version: V3 }     # listeners via ADS

static_resources:
  clusters:
  - name: xds_cluster                                    # the ONE static cluster: the control plane
    type: STRICT_DNS
    connect_timeout: 1s
    typed_extension_protocol_options:
      envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
        "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
        explicit_http_config:
          http2_protocol_options: {}
    load_assignment:
      cluster_name: xds_cluster
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address: { address: xds-control-plane, port_value: 18000 }
```

The four discovery services:

- **LDS** (Listener Discovery Service) streams listeners.
- **RDS** (Route Discovery Service) streams route configs (referenced by listeners).
- **CDS** (Cluster Discovery Service) streams clusters.
- **EDS** (Endpoint Discovery Service) streams the endpoints inside a cluster — this is the high-churn one, because pods come and go.

In production you almost always use **ADS (Aggregated Discovery Service)**: all four over *one* ordered gRPC stream. Why one stream? Because ordering matters. If a new route references a cluster that hasn't arrived yet, Envoy would briefly have a route pointing at nothing. ADS guarantees the control plane can sequence updates — send the cluster, then the route that references it — so the data plane is never inconsistent. This is the **make-before-break** discipline, and every mesh control plane (istiod included) relies on it.

> **The seam.** A service mesh is, precisely, a control plane that watches Kubernetes (Services, Endpoints, and CRDs like `VirtualService`) and translates them into LDS/RDS/CDS/EDS streamed to the per-pod Envoys over ADS. When you understand xDS, you understand what istiod *is*.

---

## 3. The filter chain in depth

The filter chain is where Envoy's power lives. There are two levels.

### 3.1 Network filters vs HTTP filters

- **Network filters** operate on raw L4 bytes of a connection. The HCM is itself a network filter — it sits in the chain, consumes the byte stream, and produces HTTP semantics. A TCP proxy is a different network filter. You rarely write your own.
- **HTTP filters** live *inside* the HCM and operate on HTTP requests and responses. This is where almost all your work happens: routing, CORS, JWT auth, rate limiting, gRPC-Web transcoding, header manipulation, fault injection.

The ordering rule for HTTP filters is strict: **the `router` filter must be last.** It terminates the chain by forwarding upstream; anything after it never runs. Filters before it form a request pipeline (run top-to-bottom on the request) and a response pipeline (run bottom-to-top on the response). A typical edge listener's HTTP filter order:

```yaml
http_filters:
- name: envoy.filters.http.cors                      # handle preflight, set CORS headers
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors
- name: envoy.filters.http.grpc_web                   # transcode gRPC-Web <-> gRPC for browsers
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.grpc_web.v3.GrpcWeb
- name: envoy.filters.http.local_ratelimit            # per-instance token bucket (Lecture 2)
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit
    stat_prefix: edge_local_rl
    token_bucket: { max_tokens: 100, tokens_per_fill: 100, fill_interval: 1s }
- name: envoy.filters.http.router                     # MUST be last
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

Read that as a pipeline: a browser preflight is answered by CORS without ever touching the backend; a gRPC-Web request is transcoded to real gRPC before routing; the local rate limiter sheds load before the router forwards. Each filter is a small, composable, well-tested unit. This composability is the whole reason Envoy ate the proxy world.

### 3.2 Per-route configuration

Routes carry behavior, not just destinations. The `route` action can specify a timeout, a retry policy, a weighted split across clusters (this is how canary works — Week 8 uses it), header mutations, and more:

```yaml
routes:
- match: { prefix: "/cart.v1.CartService/" }
  route:
    cluster: cart
    timeout: 2s
    retry_policy:                          # detail in Lecture 2
      retry_on: "5xx,reset,connect-failure"
      num_retries: 2
    request_headers_to_add:
    - header: { key: "x-edge", value: "cart-edge" }
```

Weighted routing — the primitive under every canary — looks like this and will reappear in Week 8 as an Istio `VirtualService`:

```yaml
- match: { prefix: "/" }
  route:
    weighted_clusters:
      clusters:
      - { name: cart_v1, weight: 90 }
      - { name: cart_v2, weight: 10 }      # 10% canary
```

---

## 4. The threading model — why config is eventually consistent

This is the part that separates engineers who *use* Envoy from engineers who can *reason* about it under load. Envoy's performance and its update semantics both fall out of one design choice.

### 4.1 The architecture

Envoy runs:

- **One main thread.** It handles xDS, the admin endpoint, stats flushing, and timers. It does **no** request processing. It is never on the data path.
- **N worker threads** (by default, one per logical CPU). Each worker runs its own **event loop** (libevent), accepts connections, and owns the connections it accepts for their entire lifetime. A connection is pinned to one worker; it never migrates. This is a **share-nothing** design — workers don't coordinate per-request, so there are no locks on the hot path.
- **Thread-local storage (TLS).** Shared state that workers read on the hot path — the cluster manager's view of clusters and endpoints, route tables — is held in per-worker thread-local slots.

```
            ┌───────────────┐
   xDS ───► │  MAIN THREAD  │  (config, stats, admin — never serves requests)
            └───────┬───────┘
                    │ posts updates to each worker's TLS
        ┌───────────┼───────────┬───────────┐
        ▼           ▼           ▼           ▼
   ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
   │worker 0│  │worker 1│  │worker 2│  │worker 3│   each: event loop + owned connections
   └────────┘  └────────┘  └────────┘  └────────┘
```

### 4.2 The consequence: eventual consistency, never a stall

When a new config arrives (say CDS adds an endpoint), the main thread computes the new cluster state and **posts** an update to each worker's thread-local slot. Each worker applies it the next time its event loop turns. This has two crucial consequences:

1. **Config updates never block live requests.** A worker mid-request finishes that request on the old config, then picks up the new config on its next loop iteration. There is no stop-the-world. This is why you can push thousands of EDS updates a second through a busy Envoy without latency spikes.

2. **Config is eventually consistent across workers.** For a brief window, worker 0 may have the new endpoint while worker 3 still has the old one. For load balancing this is harmless — both endpoint sets are valid. It matters only in subtle cases (e.g., a stats counter that looks momentarily inconsistent), and you should *expect* it, not be alarmed by it.

> **The practical takeaway:** "Envoy applied my config" is not an instant, global event. It's a propagation that completes in milliseconds, per worker, without ever blocking traffic. When you push a route change and the first request still hits the old route, wait one loop tick — don't conclude the push failed. `curl localhost:9901/config_dump` shows you the *main thread's* committed view; the workers converge to it.

### 4.3 Hot restart and drain

Envoy can **hot restart**: a new Envoy process starts, inherits the listening sockets from the old one (via a domain socket), and the old process **drains** — it stops accepting new connections and lets in-flight requests finish before exiting. This is how you upgrade Envoy itself with zero dropped connections, and it's the same drain machinery a mesh uses when it rolls a sidecar. You won't drive a hot restart by hand this week, but know it exists: it's why "restart the proxy" doesn't mean "drop every connection."

---

## 5. Reading a running Envoy

The diagnostic muscle for this week is the admin endpoint. Four commands you will run constantly:

```bash
# What config is actually running? (The source of truth — may differ from your file under xDS.)
curl -s localhost:9901/config_dump | jq '.configs[].dynamic_listeners // empty'

# Are my clusters healthy, and what endpoints do they have?
curl -s localhost:9901/clusters | grep -E "cart::|health_flags"

# Every counter. Grep for the cluster you care about.
curl -s localhost:9901/stats | grep -E "cluster.cart.upstream_rq(_|$)"

# Quick server health and uptime.
curl -s localhost:9901/server_info | jq '{state, uptime_current_epoch_s}'
```

The stats you'll read this week, by name:

| Stat | Meaning |
|---|---|
| `cluster.<name>.upstream_rq_total` | total requests sent to the cluster |
| `cluster.<name>.upstream_rq_2xx` / `_5xx` | response code buckets |
| `cluster.<name>.upstream_rq_retry` | retries attempted |
| `cluster.<name>.upstream_rq_retry_limit_exceeded` | retries refused by the budget (a *good* number under stress) |
| `cluster.<name>.upstream_rq_timeout` | requests that hit the route timeout |
| `cluster.<name>.upstream_rq_pending_overflow` | requests rejected by the pending-request circuit breaker |
| `cluster.<name>.outlier_detection.ejections_active` | hosts currently ejected by passive health checking |
| `cluster.<name>.circuit_breakers.default.rq_open` | 1 if the request circuit breaker is open |

When a request fails through Envoy, you diagnose it from these counters *before* you touch the application. Did it time out (`upstream_rq_timeout`)? Get circuit-broken (`pending_overflow`)? Hit a host the outlier detector ejected? The proxy tells you, if you read it.

---

## 6. Putting it together: the request, narrated

A browser hits your edge. Here is the path, using the nouns:

1. The connection lands on **`listeners[ingress_http]`**, bound on `:10000`, and is accepted by **worker 2** (say), which owns it now.
2. Worker 2 runs the **filter chain**: the HCM parses HTTP/2, the **CORS** filter passes a real request through, the **gRPC-Web** filter transcodes if needed, the **local rate-limit** filter checks the token bucket.
3. The **router** filter matches the request path against the **route table**, picks the route for `/cart.v1.CartService/`, and reads its 2 s timeout and retry policy.
4. The route names the **`cart` cluster**. The cluster's load balancer (round-robin) picks a healthy **endpoint** from its current (thread-local) endpoint set.
5. Envoy forwards over a pooled HTTP/2 connection to that endpoint, enforcing the timeout and, on a qualifying failure, the retry policy and budget.
6. The response flows back up the filter chain (bottom-to-top), stats are incremented on worker 2's local counters, and the main thread aggregates them for `/stats`.

That is the whole machine. Six steps, four nouns, one threading model.

---

## 7. Recap

You should now be able to:

- Distinguish north-south (gateway) from east-west (mesh) traffic and state when a gateway alone suffices.
- Name Envoy's four nouns and write a static bootstrap with a listener, a route, and a gRPC-capable cluster — including the `http2_protocol_options` that gRPC requires.
- Explain how the same config is delivered dynamically over LDS/RDS/CDS/EDS, and why ADS exists (ordered, consistent updates).
- Order an HTTP filter chain correctly (router last) and read it as a request/response pipeline.
- Describe the main-thread / worker-thread / thread-local design and predict that config updates are eventually consistent and never block the data path.
- Read a running Envoy from the admin endpoint and name the stats that diagnose timeouts, retries, circuit breaking, and outlier ejection.

Next up: the resilience policies that turn a proxy into a shock absorber, the BFF that tailors the backend to a client, and how a browser talks to a gRPC backend at all. Continue to [Lecture 2 — Resilience, BFFs, and the Browser](./02-resilience-bffs-and-the-browser.md).

---

## References

- *Envoy — Life of a Request*: <https://www.envoyproxy.io/docs/envoy/latest/intro/life_of_a_request>
- *Envoy — Listeners / Clusters / Routing*: <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/intro/intro>
- *Envoy — xDS protocol*: <https://www.envoyproxy.io/docs/envoy/latest/api-docs/xds_protocol>
- *Envoy — Threading model*: <https://blog.envoyproxy.io/envoy-threading-model-a8d44b922310>
- *Envoy — HttpConnectionManager*: <https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto>
- *Kubernetes Gateway API*: <https://gateway-api.sigs.k8s.io/>
