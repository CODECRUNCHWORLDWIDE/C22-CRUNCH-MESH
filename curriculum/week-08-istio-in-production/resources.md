# Week 8 — Resources

Every resource here is **free** and **open**. Istio is a CNCF graduated project; its docs are published openly and versioned per release. Kiali, Flagger, and Argo Rollouts are open-source. No paywalled books are linked.

Istio versions its docs and CRD APIs per release. This week targets **Istio 1.24+** (the line where ambient mode is GA and the `networking.istio.io/v1` and `security.istio.io/v1` API versions are stable). When a link is to `latest`, pin it to your installed version if a CRD field differs; the *concepts* are stable, only occasional field names move.

## Required reading (work it into your week)

- **Istio — Architecture** — istiod, the data plane, how config flows. Read it Monday and again Friday:
  <https://istio.io/latest/docs/ops/deployment/architecture/>
- **Istio — Ambient mesh overview** — ztunnel, waypoint, and why sidecar-less exists:
  <https://istio.io/latest/docs/ambient/overview/>
- **Istio — Mutual TLS (PeerAuthentication)** — STRICT/PERMISSIVE, the migration, the SPIFFE identity:
  <https://istio.io/latest/docs/tasks/security/authentication/mtls-migration/>
- **Istio — Authorization (AuthorizationPolicy)** — deny-by-default, allow rules, principals:
  <https://istio.io/latest/docs/concepts/security/#authorization>
- **Istio — Traffic management concepts** — VirtualService, DestinationRule, subsets:
  <https://istio.io/latest/docs/concepts/traffic-management/>

## The architecture pieces (skim, then refer back)

- **Istio — Sidecar injection** — the webhook, automatic vs manual, the init container:
  <https://istio.io/latest/docs/setup/additional-setup/sidecar-injection/>
- **Istio — Ambient architecture** — the ztunnel/waypoint data-plane split in depth:
  <https://istio.io/latest/docs/ambient/architecture/>
- **Istio — Canary deployments / traffic shifting** — weighted subsets:
  <https://istio.io/latest/docs/tasks/traffic-management/traffic-shifting/>
- **Istio — Fault injection** — fixed-delay and abort at the route:
  <https://istio.io/latest/docs/tasks/traffic-management/fault-injection/>

## CRD references (the ones you'll have open all week)

- **`VirtualService`** — routing, weights, retries, timeouts, fault injection:
  <https://istio.io/latest/docs/reference/config/networking/virtual-service/>
- **`DestinationRule`** — subsets, traffic policy, connection pools, outlier detection:
  <https://istio.io/latest/docs/reference/config/networking/destination-rule/>
- **`PeerAuthentication`** — mTLS mode per namespace/workload:
  <https://istio.io/latest/docs/reference/config/security/peer_authentication/>
- **`AuthorizationPolicy`** — allow/deny rules, principals, conditions:
  <https://istio.io/latest/docs/reference/config/security/authorization-policy/>

## Operations and debugging

- **`istioctl` reference** — `proxy-config`, `proxy-status`, `analyze`, `x describe`:
  <https://istio.io/latest/docs/reference/commands/istioctl/>
- **Istio — Debugging Envoy and Pilot** — reading the sidecar's actual config:
  <https://istio.io/latest/docs/ops/diagnostic-tools/proxy-cmd/>
- **Istio — Common problems** — the sidecar startup, init-container, and injection gotchas:
  <https://istio.io/latest/docs/ops/common-problems/>
- **Istio — `holdApplicationUntilProxyStarts`** — the startup-ordering control for the sidecar race:
  <https://istio.io/latest/docs/reference/config/istio.mesh.v1alpha1/#ProxyConfig>

## Progressive delivery

- **Flagger** — automated canary analysis driving Istio weights, with rollback:
  <https://docs.flagger.app/>
- **Argo Rollouts** — the other progressive-delivery controller, Istio-aware:
  <https://argo-rollouts.readthedocs.io/en/stable/features/traffic-management/istio/>

## Observability

- **Kiali** — the Istio service-graph, traffic, and config-validation UI:
  <https://kiali.io/docs/>
- **Istio — Observability / Telemetry** — the metrics the mesh emits and how to wire Prometheus/Grafana/Jaeger:
  <https://istio.io/latest/docs/tasks/observability/>

## Talks worth your time (free, no signup)

- **IstioCon talks** — maintainers on ambient, security, and operations, posted free on the CNCF YouTube:
  <https://www.youtube.com/c/cloudnativefdn>
- **"Ambient mesh: a new dataplane mode"** — search the CNCF channel for the ambient deep-dives from the Istio team; the why behind sidecar-less.
- **KubeCon Istio operations sessions** — the "Istio in anger" war stories, rehearsed publicly each cycle:
  <https://www.youtube.com/c/cloudnativefdn>

## Tools you'll use this week

- **`istioctl`** — install (`istioctl install --set profile=demo`), introspect (`istioctl proxy-config`, `istioctl x describe`), validate (`istioctl analyze`).
- **`kubectl`** — label namespaces for injection (`istio-injection=enabled` for sidecar, `istio.io/dataplane-mode=ambient` for ambient), apply CRDs, read pod status.
- **Kiali + Prometheus + Grafana + Jaeger** — the Istio sample addons (`samples/addons/`) give you the full observability stack in one apply.
- **`fortio`** — Istio's bundled load generator; drives the canary and fault-injection exercises.
- **`grpcurl`** — call gRPC through the mesh to prove a hop works (or is correctly denied).

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **istiod** | The Istio control plane: config validation, the CA (certs), and xDS push to the data plane. |
| **Data plane** | The proxies that carry traffic: an Envoy sidecar per pod, or in ambient, ztunnel + waypoint. |
| **Sidecar** | A full Envoy injected next to each app container; intercepts all the pod's traffic via iptables. |
| **Ambient mode** | Sidecar-less mesh: a per-node ztunnel (L4 + mTLS) plus optional per-namespace waypoint (L7). |
| **ztunnel** | The ambient per-node proxy carrying mTLS and L4 for every pod on the node, cheaply. |
| **Waypoint** | An ambient per-namespace/per-service Envoy you add only where you need L7 policy. |
| **PeerAuthentication** | The CRD that sets mTLS mode (STRICT/PERMISSIVE/DISABLE) — authentication. |
| **AuthorizationPolicy** | The CRD that allows/denies traffic by principal/namespace/properties — authorization. |
| **VirtualService** | The routing CRD: matches, weighted splits, retries, timeouts, fault injection. Maps to Envoy routes. |
| **DestinationRule** | The destination-config CRD: subsets, load balancing, pools, outlier detection. Maps to Envoy clusters. |
| **Subset** | A named slice of a service's endpoints (e.g. `v1`, `v2`) selected by pod labels; the unit of a canary. |
| **SPIFFE identity** | The workload identity baked into each mTLS cert: `spiffe://<trust-domain>/ns/<ns>/sa/<sa>`. |
| **mTLS STRICT** | The workload accepts *only* mutually-authenticated TLS; plaintext is refused. |
| **Injection webhook** | The admission webhook that adds the sidecar (and init container) to pods at creation. |
| **istioctl proxy-config** | The command that dumps a sidecar's *actual* Envoy config — the ground truth for debugging. |
| **Sidecar tax** | The memory + per-hop latency + ops cost a per-pod Envoy adds; the reason ambient exists. |

---

*If a link 404s, please open an issue so we can replace it.*
