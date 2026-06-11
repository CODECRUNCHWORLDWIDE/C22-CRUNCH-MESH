# Lecture 2 — Resilience, BFFs, and the Browser

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can configure timeouts, retries with a budget, outlier detection, and circuit breakers at the proxy and state what each does *not* protect you from; design a per-client BFF and justify it as a separate deployable; choose between gRPC-Web and Connect for the browser; and place rate limiting where it belongs.

Lecture 1 gave you the machine. This lecture makes it a *shock absorber*. A proxy that only forwards is a router; a proxy that forwards *and* contains failure is the reason you put a proxy there at all. Three parts: (1) the resilience policies, (2) the BFF pattern, (3) the browser and rate limiting.

The sentence to carry through this lecture:

> **Every resilience primitive is a way of spending one resource to protect another — and a retry without a budget spends the thing it's trying to protect.**

---

## Part 1 — Resilience at the proxy

There are four primitives, and they compose. Configure them in this order of importance: timeouts first (always), then circuit breakers, then outlier detection, then retries (last, and never without a budget).

### 1.1 Timeouts — the one you must never omit

A request without a timeout is a request that can hang forever, and a hung request holds a connection, a goroutine, a slot in every pool between the client and the backend. One slow dependency with no timeout is how a single bad database query takes down a whole fleet: the slowness propagates upstream as exhausted connection pools. **Every route gets a timeout.**

```yaml
route:
  cluster: cart
  timeout: 2s                       # the overall route timeout: total time for the request
```

Two subtleties:

- The route `timeout` is the **overall** budget for the request *including retries*. If you set `timeout: 2s` and a retry policy of 2 retries, all attempts must finish within 2 s total — the second retry won't even start if 2 s have elapsed.
- For streaming gRPC, the overall timeout is wrong (a stream is long-lived). Use `max_stream_duration` or disable the route timeout for streaming routes and rely on per-message deadlines.

The cardinal sin: **a proxy timeout longer than the client's timeout.** If your mobile app gives up after 3 s but Envoy's route timeout is 10 s, then for 7 seconds Envoy is doing work for a client that's already gone — and may be *retrying* on behalf of a request nobody is waiting for. Timeouts should *tighten* as you go upstream, not loosen.

### 1.2 Circuit breakers — fail fast instead of piling on

A circuit breaker bounds how much in-flight work a cluster can have. When a backend is struggling, the worst thing you can do is send it more; the circuit breaker makes the proxy **fail fast** (return 503 immediately) once limits are hit, instead of queuing requests that will only make the backend slower.

```yaml
clusters:
- name: cart
  # ... type, endpoints ...
  circuit_breakers:
    thresholds:
    - priority: DEFAULT
      max_connections: 1024        # cap upstream connections
      max_pending_requests: 100    # cap requests waiting for a connection; overflow -> 503 fast
      max_requests: 1024           # cap concurrent requests (HTTP/2 multiplexes, so this matters)
      max_retries: 3               # cap concurrent retries across the cluster
```

The key counters: `upstream_rq_pending_overflow` (a request was rejected because the pending queue was full) and `circuit_breakers.default.rq_open` (the breaker is open). When you see these climb, the proxy is protecting the backend by shedding load — which is the system working, not failing. A backend that's overwhelmed recovers *faster* when you stop sending it work; the circuit breaker is how you stop.

> **What it does not protect you from:** a circuit breaker bounds *concurrency*, not *correctness*. It won't help if the backend returns wrong answers quickly. And it's per-cluster per-Envoy — in a fleet, each sidecar has its own breaker, so the *aggregate* limit is `N × max_requests`. Size accordingly.

### 1.3 Outlier detection — passive health checking

Outlier detection ejects an individual *endpoint* (one bad pod) from the load-balancing set when it misbehaves, without an active probe. It watches the responses the endpoint actually returns and ejects it after a threshold of consecutive failures.

```yaml
clusters:
- name: cart
  outlier_detection:
    consecutive_5xx: 5                 # 5 consecutive 5xx -> eject
    consecutive_gateway_failure: 5     # connection failures / resets
    interval: 10s                      # how often the ejection sweep runs
    base_ejection_time: 30s            # eject for 30s (grows with repeated ejections)
    max_ejection_percent: 50           # never eject more than half the cluster at once
```

The `max_ejection_percent` cap is the safety valve: if your *whole* cluster is throwing 5xx (a bad deploy, a dependency outage), you do **not** want outlier detection to eject every host and route traffic to nothing. Capping at 50% means even a total meltdown leaves half the hosts in rotation, so the symptom is degraded service, not zero service.

The counter to watch: `cluster.cart.outlier_detection.ejections_active`. Non-zero means the proxy found a bad host and is routing around it — usually exactly what you want, and a signal to go investigate *which* pod and *why*.

> **What it does not protect you from:** outlier detection is *passive* — it learns from failed requests, which means some requests *do* fail before a host is ejected. It also can't distinguish "this host is bad" from "this host got unlucky with three hard requests in a row." Tune `consecutive_5xx` so a transient blip doesn't eject a healthy host.

### 1.4 Retries — last, and never without a budget

Retries are the most dangerous resilience primitive because they *amplify* load exactly when the system can least afford it. A backend hiccups; every client retries; the retry traffic doubles the load; the backend, now under 2× load, hiccups harder; everyone retries again. This is a **retry storm**, and it has taken down more production systems than the original fault ever would have.

The naive retry:

```yaml
retry_policy:
  retry_on: "5xx,reset,connect-failure"
  num_retries: 2
```

This is a loaded gun. `num_retries: 2` means up to 3× the traffic to a struggling backend. The fix is a **retry budget**: cap retries as a *fraction* of active requests, so retries can never become more than a small percentage of total load no matter how many requests are failing.

```yaml
clusters:
- name: cart
  circuit_breakers:
    thresholds:
    - priority: DEFAULT
      retry_budget:
        budget_percent: { value: 20.0 }    # retries may be at most 20% of active requests
        min_retry_concurrency: 3           # but always allow at least 3 concurrent retries
```

Now even if *every* request fails, retries are capped at 20% of active load — the backend sees at most 1.2× traffic, not 3×. The budget is the difference between a retry policy that helps and one that turns a blip into an outage. The counter `upstream_rq_retry_limit_exceeded` *climbing under stress is the budget working* — it's refusing retries it would otherwise have made.

Two more retry disciplines:

- **Only retry idempotent operations.** A `GET` or a gRPC read is safe to retry. A `POST` that charges a card is not — a retry might double-charge. Envoy's `retry_on` plus per-route config lets you retry reads and not writes. (Week 11's idempotency keys are the deeper fix; the retry policy is the first line.)
- **Retry with backoff and jitter.** Envoy adds exponential backoff between retries by default (`retry_back_off`); keep it. Retrying *immediately* and in lockstep across all clients is how you synchronize a thundering herd.

**Hedging** is a cousin of retries: instead of waiting for a slow response then retrying, send a second request after a short delay and take whichever returns first. It trades extra load for tail-latency reduction. Use it sparingly, only on idempotent reads, only when p99 tail latency genuinely hurts — it spends load to buy latency, and under stress that's the wrong trade.

```yaml
route:
  cluster: cart
  timeout: 2s
  retry_policy:
    retry_on: "reset,connect-failure,unavailable"   # gRPC-aware conditions
    num_retries: 2
    retry_host_predicate:
    - name: envoy.retry_host_predicates.previous_hosts   # don't retry the same bad host
    host_selection_retry_max_attempts: 3
```

`previous_hosts` is the small detail that makes retries actually work: without it, a retry can land on the *same* failing endpoint. With it, Envoy avoids hosts it already tried — so a retry has a real chance of hitting a healthy pod.

---

## Part 2 — The BFF pattern

### 2.1 The problem BFFs solve

You have a gRPC backbone: `cart`, `inventory`, `payment`, `order`. A mobile app needs, for one screen, the cart contents *and* each item's current stock *and* a price. Three options:

1. **The mobile app makes three calls.** Now the app is chatty over a flaky cellular network, leaks your service topology to the client, and re-implements aggregation logic on every platform (iOS, Android, web).
2. **A shared "API layer" serves all clients.** It grows to satisfy web *and* mobile *and* partners, accumulating every client's needs into one bloated surface — the distributed monolith reborn as an API tier. Every client's change risks every other client.
3. **A BFF per client class.** A `bff-mobile` tailored to the mobile app, a `bff-web` tailored to the browser, each owned by the client team, each aggregating exactly what *its* client needs and nothing more.

Option 3 is the BFF pattern. The insight from Sam Newman: **the friction you're trying to remove is the friction between a backend optimized for many consumers and a frontend optimized for one experience.** A BFF resolves it by giving each frontend its own backend-shaped-for-it.

### 2.2 What a BFF is and is not

A BFF **is**:

- A thin aggregation and translation layer. It fans out to the gRPC backbone, composes the results, and returns one response shaped for its client.
- Owned by the **client team**, not a central platform team. The mobile team owns `bff-mobile`; they change it when the mobile app changes, without a cross-team ticket.
- Per **client class**, not per client. Web and mobile each get one; you don't make a BFF per app version.

A BFF is **not**:

- A place for business logic. The cart's pricing rules live in the `cart` service, not the BFF. If the BFF starts making business decisions, it's becoming a service, and you've smeared a bounded context across two deployables.
- A shared layer. The moment `bff-mobile` and `bff-web` share code that encodes *both* clients' needs, you've recreated option 2. Some shared *libraries* are fine (a generated gRPC client); shared *surface* is the smell.
- A security boundary on its own. It runs behind the gateway; auth happens at the edge. The BFF trusts the identity the gateway established.

### 2.3 The aggregation, concretely

A mobile BFF endpoint that builds a cart screen fans out to `cart` and `inventory` in parallel, then composes:

```go
// Sketch — the full runnable version is exercise-03-mobile-bff.go.
func (s *MobileBFF) GetCartScreen(ctx context.Context, userID string) (*CartScreen, error) {
    // Fan out in parallel with a shared deadline derived from the inbound context.
    ctx, cancel := context.WithTimeout(ctx, 800*time.Millisecond)
    defer cancel()

    cart, err := s.cartClient.GetCart(ctx, &cartv1.GetCartRequest{UserId: userID})
    if err != nil {
        return nil, err
    }

    // For each cart line, fetch live stock — but in one batched call, not N calls.
    skus := skusOf(cart)
    stock, err := s.inventoryClient.GetStockBatch(ctx, &inventoryv1.GetStockBatchRequest{Skus: skus})
    if err != nil {
        // Degrade: show the cart without live stock rather than failing the whole screen.
        return cartScreenWithoutStock(cart), nil
    }
    return composeCartScreen(cart, stock), nil   // one response, shaped for the phone
}
```

Three BFF disciplines visible here:

- **A deadline tighter than the inbound one.** The BFF gives its fan-out 800 ms even if the client allowed 1 s, leaving slack to compose and respond.
- **Batch, don't loop.** `GetStockBatch` over the SKUs, not `GetStock` in a loop — the BFF's job is to turn a chatty client into a small number of efficient backend calls.
- **Graceful degradation.** If `inventory` is down, the BFF returns the cart *without* live stock rather than failing the whole screen. The client team decides what's degradable; that's *why* they own the BFF.

---

## Part 3 — The browser and rate limiting

### 3.1 gRPC-Web vs Connect

A browser cannot speak raw gRPC. gRPC requires control over HTTP/2 framing (trailers, in particular) that the browser `fetch` API does not expose. Two solutions:

**gRPC-Web** is a modified gRPC wire format the browser *can* produce, with a proxy in the middle translating gRPC-Web ⇄ gRPC. Envoy's `grpc_web` filter does exactly this: the browser sends gRPC-Web, Envoy transcodes it to real gRPC for the backend, and transcodes the response back. It works, it's mature, and it requires the proxy in the path — which, since you have Envoy at the edge anyway, is free.

```yaml
http_filters:
- name: envoy.filters.http.grpc_web
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.grpc_web.v3.GrpcWeb
- name: envoy.filters.http.cors            # browsers need CORS for cross-origin gRPC-Web
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors
- name: envoy.filters.http.router
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

**Connect** (from Buf) is the newer answer. A Connect server handler speaks *three* protocols from one endpoint: gRPC, gRPC-Web, and Connect's own protocol — which is plain HTTP/1.1-friendly POST with JSON or binary bodies that a browser `fetch` can produce *directly, with no proxy transcoding*. The trade you make:

- **gRPC-Web** keeps your backend a pure gRPC server; the browser support is the proxy's job. Best when you already run Envoy and want one protocol server-side.
- **Connect** makes the *backend* multi-protocol, so the browser can call it directly (even without Envoy) and you get human-debuggable HTTP requests. Best for new services where browser-friendliness and `curl`-ability are worth a different server library.

In 2026 the honest guidance: if you have Envoy at the edge (you do, this week), gRPC-Web is the path of least resistance. If you're standing up a browser-first service and value being able to `curl` it, Connect is worth the look — and `connect-go` interoperates with gRPC clients, so it's not an all-or-nothing bet.

### 3.2 The gRPC-JSON transcoder

A related Envoy filter, `grpc_json_transcoder`, lets a REST/JSON client call a gRPC backend by mapping HTTP paths to gRPC methods using the `google.api.http` annotations in your proto. It's how you offer a REST surface over a gRPC service without writing a second server. Useful for partner APIs that can't adopt gRPC; not something you reach for internally.

### 3.3 Rate limiting: local vs global

Rate limiting protects a backend (and enforces quota) by rejecting requests over a threshold with a `429 Too Many Requests` (or gRPC `RESOURCE_EXHAUSTED`). There are two flavors, and the difference is *where the counter lives*.

**Local rate limiting** runs entirely inside one Envoy instance: a token bucket per instance, no network hop, microsecond-cheap. It's perfect for coarse, per-instance protection ("no single edge proxy forwards more than 1000 req/s to `cart`").

```yaml
http_filters:
- name: envoy.filters.http.local_ratelimit
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit
    stat_prefix: edge_local_rl
    token_bucket:
      max_tokens: 1000
      tokens_per_fill: 1000
      fill_interval: 1s
    filter_enabled: { default_value: { numerator: 100, denominator: HUNDRED } }
    filter_enforced: { default_value: { numerator: 100, denominator: HUNDRED } }
```

Its limitation is exactly its strength: the counter is *per instance*. If you run three edge Envoys, your effective limit is 3× what you wrote, and it drifts as you autoscale. For coarse protection that's fine; for a *contractual* quota ("this customer gets 100 req/s across our whole fleet"), it's wrong.

**Global rate limiting** puts the counter in a shared external service — the **Rate Limit Service (RLS)**, a gRPC service (the reference implementation is `envoyproxy/ratelimit`, backed by Redis). Every Envoy asks the RLS "is this descriptor over budget?" per request. Now the limit is fleet-wide and correct under horizontal scale — at the cost of one network hop per rate-limited request and a shared dependency you must keep healthy.

```yaml
# In the HCM HTTP filters: ask the RLS per request.
- name: envoy.filters.http.ratelimit
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.ratelimit.v3.RateLimit
    domain: edge
    rate_limit_service:
      grpc_service: { envoy_grpc: { cluster_name: ratelimit_service } }
      transport_api_version: V3
```

The decision: **local for coarse per-instance protection (cheap, eventually-slightly-wrong); global for fleet-wide contractual quota (correct, one hop, a shared dependency).** Many production edges run *both*: a local limiter as a cheap first line of defense and a global limiter for per-customer quota. When you return a 429, include a `Retry-After` header so well-behaved clients back off instead of hammering.

---

## Part 4 — The honest vendor comparison

You'll be asked, in interviews and in real architecture reviews, "why Envoy and not Kong or Tyk?" The grown-up answer:

| | Envoy | Kong | Tyk |
|---|---|---|---|
| Heritage | C++, purpose-built proxy (Lyft) | Lua on Nginx (newer Envoy-adjacent paths exist) | Go, API-management-first |
| Primary strength | Data plane: the proxy everything else builds on | API management, plugin ecosystem, dev portal | API management, Go-native, simpler ops for some teams |
| xDS / mesh data plane | *Is* the standard data plane (Istio, Linkerd's edge, App Mesh, Gateway API) | Not a mesh data plane | Not a mesh data plane |
| When it wins | You want the most powerful, programmable proxy and/or a mesh | You want batteries-included API management with a portal | You want Go-native API management with a gentle ops story |

The load-bearing fact: **Envoy is the data plane underneath most of the field.** Istio runs Envoy. Envoy Gateway runs Envoy. AWS App Mesh ran Envoy. When you learn Envoy, you learn the substrate that the gateways and meshes are configuring on your behalf — which is exactly why this week teaches Envoy by hand before Weeks 8–9 let a control plane drive it.

---

## Part 5 — The full resilience stack, composed

Pull the four primitives together into one cluster's config — the shape you'll defend in the mini-project's audit. Read it as a single, coherent posture rather than four separate features:

```yaml
clusters:
- name: cart
  type: STRICT_DNS
  connect_timeout: 1s
  typed_extension_protocol_options:
    envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
      "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
      explicit_http_config: { http2_protocol_options: {} }
  # (1) CIRCUIT BREAKERS — bound concurrency; fail fast over piling on.
  circuit_breakers:
    thresholds:
    - priority: DEFAULT
      max_connections: 1024
      max_pending_requests: 100
      max_requests: 1024
      max_retries: 3
      # (2) RETRY BUDGET — the single most important line; caps retries at 20% of load.
      retry_budget:
        budget_percent: { value: 20.0 }
        min_retry_concurrency: 3
  # (3) OUTLIER DETECTION — eject a bad host; never more than half the cluster.
  outlier_detection:
    consecutive_5xx: 5
    interval: 10s
    base_ejection_time: 30s
    max_ejection_percent: 50
```

And the route that consumes it, carrying the **timeout** (4) and the retry conditions:

```yaml
route:
  cluster: cart
  timeout: 2s                         # overall budget, including retries
  retry_policy:
    retry_on: "5xx,reset,connect-failure,unavailable"
    num_retries: 2
    per_try_timeout: 0.8s             # each attempt bounded independently
    retry_host_predicate:
    - name: envoy.retry_host_predicates.previous_hosts   # don't retry a host that just failed
    host_selection_retry_max_attempts: 3
```

The ordering of importance, restated as a checklist you can apply to *any* cluster fronting a real dependency:

1. **Timeout present?** If not, stop — a call with no timeout can hang forever and exhaust pools upstream.
2. **Circuit breakers bound concurrency?** A struggling backend recovers faster when you stop piling on.
3. **Outlier detection with `max_ejection_percent`?** Route around one bad host, but never to nothing.
4. **Retries — and do they have a budget?** Retries without a budget are a loaded gun; the budget is non-negotiable.

If a cluster is missing any of the four, it's a resilience gap — and the mini-project's audit script exists precisely to fail a deploy that ships one. "We have retries" is not the bar; "every cluster has a timeout, a breaker, outlier detection, and a budgeted retry policy, verifiable in `/config_dump`" is.

> **The composition is the point.** Each primitive protects against a different failure: timeouts against hangs, breakers against overload, outlier detection against one bad host, budgeted retries against transient drops. Configured together they turn a proxy into a shock absorber that contains the failure modes your services will actually hit in production. Configured *partially* — say, retries with no budget and no breaker — they can make an outage worse than no resilience at all, which is the lesson the retry-storm challenge drives home.

---

## 5. Recap

You should now be able to:

- Configure timeouts (always), circuit breakers, outlier detection, and retries *with a budget* — in that order — and state what each does not protect you from.
- Explain why a retry without a budget amplifies an outage, and why `previous_hosts` and backoff make retries actually safe.
- Design a per-client BFF, justify it as a separate deployable owned by the client team, and apply the deadline / batch / degrade disciplines.
- Choose between gRPC-Web (proxy transcodes, backend stays pure gRPC) and Connect (multi-protocol backend, browser-direct) for the browser.
- Place rate limiting correctly: local for cheap per-instance protection, global RLS for fleet-wide contractual quota.
- Defend "why Envoy" against Kong and Tyk by naming Envoy's role as the data plane the rest build on.

Next: the exercises put all of this on your `cart`/`inventory` topology. Continue to [the exercises](../exercises/README.md).

---

## References

- *Envoy — Retry policy*: <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/router_filter#retry-policy>
- *Envoy — Outlier detection*: <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/outlier>
- *Envoy — Circuit breaking*: <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking>
- *Envoy — Global rate limiting*: <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/other_features/global_rate_limiting>
- *Pattern: Backends for Frontends (Sam Newman)*: <https://samnewman.io/patterns/architectural/bff/>
- *Connect protocol (Buf)*: <https://connectrpc.com/docs/introduction/>
- *Envoy — gRPC-Web filter*: <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/grpc_web_filter>
