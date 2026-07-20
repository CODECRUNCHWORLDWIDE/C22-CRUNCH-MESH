# Exercise 1 — Envoy as Ingress in Front of cart and inventory

**Goal:** Stand up Envoy as a north-south ingress in front of your two gRPC services, route by gRPC service path to the right cluster, and *prove* with `grpcurl` and the admin `/stats` that the proxy is forwarding and that gRPC actually works through it. You will train the single most important Envoy habit of the week: reading the admin endpoint instead of guessing.

**Estimated time:** 60 minutes. Guided.

---

## Setup

You need `cart` and `inventory` reachable as gRPC servers. In-cluster they're Services; locally, run them on `localhost:50051` (cart) and `localhost:50052` (inventory).

**Fallback if your Phase 1 services aren't ready.** Use the gRPC reflection-enabled health server below as a stand-in for *each* service. Save as `stub_server.py`, run two copies on different ports. It serves the standard gRPC health and reflection services, which is enough to prove the proxy hop.

```python
#!/usr/bin/env python3
"""Minimal gRPC server with health + reflection — a stand-in for cart/inventory."""
import sys
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection


def serve(port: str, name: str) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    service_names = (health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
                     reflection.SERVICE_NAME)
    reflection.enable_server_reflection(service_names, server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    print(f"{name} gRPC stub serving on :{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve(sys.argv[1], sys.argv[2])   # e.g. python3 stub_server.py 50051 cart
```

```bash
pip install grpcio grpcio-health-checking grpcio-reflection grpcio-tools
python3 stub_server.py 50051 cart      # terminal 1
python3 stub_server.py 50052 inventory # terminal 2
```

---

## Step 1 — Write the Envoy config

Save this as `ingress.yaml`. One listener on `:10000`, routing by gRPC path prefix to two clusters. Note the `http2_protocol_options` on **both** clusters — gRPC requires HTTP/2 upstream.

```yaml
admin:
  address:
    socket_address: { address: 0.0.0.0, port_value: 9901 }

static_resources:
  listeners:
  - name: ingress
    address:
      socket_address: { address: 0.0.0.0, port_value: 10000 }
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress
          codec_type: AUTO
          route_config:
            name: edge
            virtual_hosts:
            - name: backend
              domains: ["*"]
              routes:
              - match: { prefix: "/cart.v1." }
                route: { cluster: cart, timeout: 2s }
              - match: { prefix: "/inventory.v1." }
                route: { cluster: inventory, timeout: 2s }
              # health + reflection paths can go to either; send them to cart.
              - match: { prefix: "/grpc.health." }
                route: { cluster: cart, timeout: 2s }
              - match: { prefix: "/grpc.reflection." }
                route: { cluster: cart, timeout: 2s }
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
  - name: cart
    type: STRICT_DNS
    connect_timeout: 1s
    lb_policy: ROUND_ROBIN
    typed_extension_protocol_options:
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
              socket_address: { address: 127.0.0.1, port_value: 50051 }
  - name: inventory
    type: STRICT_DNS
    connect_timeout: 1s
    lb_policy: ROUND_ROBIN
    typed_extension_protocol_options:
      envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
        "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
        explicit_http_config:
          http2_protocol_options: {}
    load_assignment:
      cluster_name: inventory
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address: { address: 127.0.0.1, port_value: 50052 }
```

> If your services run **in Kind**, change the two `address:` values to the Service DNS (`cart.default.svc.cluster.local` / `inventory.default.svc.cluster.local`) and run Envoy as a Deployment in the cluster. The config is otherwise identical — that portability is the point.

---

## Step 2 — Run Envoy and confirm it loaded

```bash
func-e run -c ingress.yaml
```

In another terminal, confirm the config actually loaded — don't trust that "no error printed" means "config applied":

```bash
curl -s localhost:9901/config_dump | jq '.configs[] | select(."@type" | test("ClustersConfigDump")) | .static_clusters | length'
# 2
```

You should see `2` clusters. Now confirm the upstreams are reachable:

```bash
curl -s localhost:9901/clusters | grep -E "::(cx_active|health_flags|rq_total)" | grep -E "cart|inventory"
```

Look for `health_flags::healthy` (no failing flags) on the endpoints. A cluster whose endpoint shows `/failed_active_hc` or refuses connection means your service isn't up on that port — fix that before going on.

---

## Step 3 — Call through the proxy

`grpcurl` against the **proxy** (`:10000`), not the service. This is the whole point — the request goes browser → Envoy → service.

```bash
# List services via reflection, THROUGH Envoy:
grpcurl -plaintext localhost:10000 list

# Call the health check THROUGH Envoy:
grpcurl -plaintext localhost:10000 grpc.health.v1.Health/Check
```

Expected:

```
grpc.health.v1.Health
grpc.reflection.v1alpha.ServerReflection
```

```json
{
  "status": "SERVING"
}
```

If you instead get `Unavailable` or `upstream connect error`, the proxy reached but the upstream failed — go read `/clusters` again. If you get a codec error, you forgot `http2_protocol_options` on the cluster.

---

## Step 4 — Prove the hop in the stats

This is the diagnostic muscle. With your `grpcurl` calls done, read the per-cluster request counters:

```bash
curl -s localhost:9901/stats | grep -E "cluster.cart.upstream_rq(_2xx|_total)$"
```

Expected (counts depend on how many calls you made):

```
cluster.cart.upstream_rq_total: 2
cluster.cart.upstream_rq_2xx: 2
```

**The counter incrementing on the cluster you called is the proxy doing its job.** Make an `inventory.v1` call (against your real service or with a crafted reflection call) and watch `cluster.inventory.upstream_rq_total` climb instead. That routing-by-path is the listener and route table working.

---

## Step 5 — Make the routing fail on purpose, then fix it

Change the `/inventory.v1.` route's cluster to a name that doesn't exist (`inventory_typo`) and reload Envoy. Call an inventory method through the proxy. You'll get a `503` and:

```bash
curl -s localhost:9901/stats | grep -E "no_cluster|no_route"
# http.ingress.no_cluster: 1
```

`no_cluster` means the route matched but pointed at a cluster that doesn't exist — a config bug the proxy surfaces immediately. Fix the name, reload, confirm `no_cluster` stops climbing. This is the failure you'll see most often when hand-writing routes: a typo'd cluster name. The stat names it.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `curl -s localhost:9901/config_dump` shows **2** clusters (`cart`, `inventory`) loaded.
- [ ] `grpcurl -plaintext localhost:10000 grpc.health.v1.Health/Check` returns `SERVING` *through the proxy*.
- [ ] `cluster.cart.upstream_rq_2xx` increments when you call a `cart.v1` (or health) method through `:10000`.
- [ ] Routing by path works: a `cart.v1` call increments `cluster.cart.*` and an `inventory.v1` call increments `cluster.inventory.*`.
- [ ] You can explain, in one sentence, why both clusters need `http2_protocol_options` (gRPC rides on HTTP/2; without it Envoy speaks HTTP/1.1 upstream and gRPC fails).

---

## Stretch

- Add a **second endpoint** to the `cart` cluster (run a second stub on `:50053`) and confirm round-robin spreads requests across both — `curl /clusters` shows two healthy endpoints and `rq_total` splits roughly evenly.
- Add the `grpc_web` HTTP filter (before the router) and a CORS filter, and call the proxy from a browser `fetch()` with the gRPC-Web client. Now your browser talks to a gRPC backend.
- Switch the listener to require **TLS** (add a `transport_socket` with a self-signed cert) and call with `grpcurl -insecure`. You've terminated TLS at the edge — the north-south job.

---

When this feels comfortable, move to [Exercise 2 — The resilience policy](exercise-02-resilience-policy.yaml).
