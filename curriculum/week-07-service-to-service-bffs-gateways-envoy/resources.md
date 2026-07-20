# Week 7 — Resources

Every resource here is **free** and **open**. Envoy is a CNCF graduated project; its docs are published openly. The CNCF gateway and mesh projects (Kong, Tyk Community Edition, the Gateway API spec) all have public documentation. Connect and Buf docs are open. No paywalled books are linked.

Envoy versions its docs per release. The examples in this week target **Envoy 1.31+** (the `v3` xDS API, which is the only API surface in 2026 — `v2` was removed years ago). When a link is to `latest`, pin it to your installed version if you hit a config-field discrepancy; the *concepts* are stable, only field names occasionally move.

## Required reading (work it into your week)

- **Envoy — "Life of a Request"** — the canonical mental model. Read it Monday and again Thursday:
  <https://www.envoyproxy.io/docs/envoy/latest/intro/life_of_a_request>
- **Envoy — Listeners, Clusters, Routing overview** — the four nouns you configure all week:
  <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/intro/intro>
- **Envoy — xDS REST/gRPC protocol** — how LDS/RDS/CDS/EDS and ADS deliver dynamic config:
  <https://www.envoyproxy.io/docs/envoy/latest/api-docs/xds_protocol>
- **Envoy — Threading model** — why config is eventually consistent across workers and never blocks the data path:
  <https://blog.envoyproxy.io/envoy-threading-model-a8d44b922310>
- **Pattern: Backends for Frontends** — Sam Newman's canonical write-up of the BFF:
  <https://samnewman.io/patterns/architectural/bff/>

## The architecture pieces (skim, then refer back)

You won't read these cover to cover, but you want them open while you configure.

- **Envoy — Retry policy** — `retry_on`, `num_retries`, the retry budget, host predicates:
  <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/router_filter#retry-policy>
- **Envoy — Outlier detection** — passive health checking, consecutive-5xx and consecutive-gateway-failure ejection:
  <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/outlier>
- **Envoy — Circuit breaking** — `max_connections`, `max_requests`, `max_pending_requests`, `max_retries`:
  <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking>
- **Envoy — Global rate limiting** — the RLS gRPC API and the `ratelimit` reference service:
  <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/other_features/global_rate_limiting>

## API and config references (the ones you'll have open all week)

- **Envoy — `HttpConnectionManager`** — the HTTP filter you build every listener around:
  <https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto>
- **Envoy — `Cluster`** — connection pooling, load balancing, health checks, circuit breakers:
  <https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/cluster.proto>
- **Envoy — `RouteConfiguration` / `RouteAction`** — timeouts, retries, traffic splitting at the route:
  <https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/route/v3/route_components.proto>
- **Envoy — gRPC-Web filter** and **gRPC-JSON transcoder**:
  <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/grpc_web_filter>
  <https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/grpc_json_transcoder_filter>

## The control plane (for the stretch goals)

- **`go-control-plane`** — the reference Go xDS server every mesh control plane is built on:
  <https://github.com/envoyproxy/go-control-plane>
- **`envoyproxy/ratelimit`** — the reference global rate-limit service, Redis-backed:
  <https://github.com/envoyproxy/ratelimit>
- **Kubernetes Gateway API** — the standard that replaces Ingress; Envoy Gateway implements it:
  <https://gateway-api.sigs.k8s.io/>
- **Envoy Gateway** — Envoy as a managed Gateway API implementation; read its config to see xDS generated for you:
  <https://gateway.envoyproxy.io/>

## Browser-to-gRPC

- **Connect (Buf)** — the protocol that speaks gRPC, gRPC-Web, and HTTP/1.1 from one handler:
  <https://connectrpc.com/docs/introduction/>
- **`connect-go`** — the Go server/client library you'll reach for in the stretch:
  <https://github.com/connectrpc/connect-go>
- **gRPC-Web** — the older standard and its proxy requirement:
  <https://github.com/grpc/grpc-web>

## The honest vendor comparison (read the docs, not the marketing)

- **Kong Gateway** — the Lua/Nginx-heritage gateway, plus its newer Envoy-adjacent and Kubernetes-Gateway-API stories:
  <https://docs.konghq.com/gateway/latest/>
- **Tyk** — the Go-native, API-management-first gateway (open-source core):
  <https://tyk.io/docs/>
- **CNCF Landscape — API Gateway category** — survey the field before you commit:
  <https://landscape.cncf.io/>

## Talks worth your time (free, no signup)

- **EnvoyCon talks** — the maintainers on threading, xDS, and the data plane, posted free on the CNCF YouTube:
  <https://www.youtube.com/c/cloudnativefdn>
- **Matt Klein — "Envoy: an open-source edge and service proxy"** — the origin talk from the creator; the why behind the design:
  search the CNCF channel for the original Envoy introduction.
- **KubeCon service-mesh and gateway sessions** — the gateway-vs-mesh debate, rehearsed publicly every cycle:
  <https://www.youtube.com/c/cloudnativefdn>

## Tools you'll use this week

- **`envoy`** — run it locally with `func-e` (`func-e run -c envoy.yaml`) or the official `envoyproxy/envoy` container.
- **The Envoy admin endpoint** — `localhost:9901`: `/stats`, `/clusters`, `/config_dump`, `/server_info`. Your primary diagnostic.
- **`grpcurl`** — call gRPC methods through the proxy and direct, to prove the hop.
- **`func-e`** — the Envoy version manager from Tetrate; `func-e use 1.31.0 && func-e run -c envoy.yaml`.
- **`fortio`** or **`ghz`** — load generators; `fortio load` and `ghz` (gRPC-native) drive the resilience exercises.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Listener** | A socket Envoy binds; an address + port + the filter chain that processes its connections. |
| **Filter chain** | The ordered pipeline a connection passes through; network filters wrap HTTP filters. |
| **HCM** | `HttpConnectionManager` — the network filter that turns bytes into HTTP and runs the HTTP filter chain + router. |
| **Cluster** | A named group of upstream endpoints Envoy load-balances across, with its own pool, health checks, and circuit breakers. |
| **Endpoint** | One upstream host:port inside a cluster. |
| **xDS** | The family of discovery services Envoy pulls dynamic config from. |
| **LDS / RDS / CDS / EDS** | Listener / Route / Cluster / Endpoint Discovery Service — the four config streams. |
| **ADS** | Aggregated Discovery Service — all xDS over one ordered gRPC stream, so updates are consistent. |
| **North-south** | Traffic between the outside world and your services — the edge. A gateway's domain. |
| **East-west** | Traffic between your services internally. A service mesh's domain. |
| **BFF** | Backend-for-frontend — a thin per-client aggregation service that tailors the backend surface to one client class. |
| **Outlier detection** | Passive health checking: eject a host that returns errors, without an active probe. |
| **Retry budget** | A cap on retries as a fraction of active requests, so retries can't amplify an outage. |
| **Circuit breaker** | Per-cluster limits on connections/requests/retries that fail fast instead of piling on. |
| **RLS** | Rate Limit Service — the external gRPC service Envoy asks "is this request over quota?" for global limits. |
| **gRPC-Web** | A transcoding of gRPC that a browser can speak, requiring a proxy to translate. |
| **Connect** | A protocol (Buf) that speaks gRPC, gRPC-Web, and a browser-friendly HTTP/1.1 form from one handler. |

---

*If a link 404s, please open an issue so we can replace it.*
