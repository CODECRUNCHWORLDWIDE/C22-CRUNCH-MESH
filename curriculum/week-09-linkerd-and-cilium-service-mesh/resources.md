# Week 9 — Resources

Every resource here is **free** and **open**. Linkerd and Cilium are both CNCF graduated projects with public, versioned documentation. The eBPF material is open. The comparison reading is vendor docs and conference talks, not paywalled analyst reports. No paywalled books are linked.

Both projects version their docs per release. This week targets **Linkerd 2.16+** (the stable line in 2026) and **Cilium 1.16+** (where service mesh and mTLS are mature). When a link is to `latest` or `stable`, pin it to your installed version if a flag differs; the *concepts* are stable, only occasional CLI flags move.

## Required reading (work it into your week)

- **Linkerd — Architecture** — control plane, the proxy, the data path. Read it Monday:
  <https://linkerd.io/2/reference/architecture/>
- **Linkerd — Why a Rust micro-proxy** — the design argument for a purpose-built proxy over Envoy:
  <https://linkerd.io/2020/12/03/why-linkerd-doesnt-use-envoy/>
- **Cilium — Service Mesh overview** — eBPF datapath, sidecar-less, the embedded Envoy for L7:
  <https://docs.cilium.io/en/stable/network/servicemesh/>
- **Cilium — Mutual Authentication (mTLS)** — how mTLS works without a per-pod proxy:
  <https://docs.cilium.io/en/stable/network/servicemesh/mutual-authentication/mutual-authentication/>
- **The service mesh landscape (CNCF)** — the field, so your comparison isn't just three points:
  <https://landscape.cncf.io/>

## Linkerd (Monday/Tuesday)

- **Linkerd — Getting started** — install + mesh a workload on Kind:
  <https://linkerd.io/2/getting-started/>
- **Linkerd — Automatic mTLS** — the identity system and how mTLS is on by default:
  <https://linkerd.io/2/features/automatic-mtls/>
- **Linkerd — Authorization policy** — `Server`, `ServerAuthorization`, `AuthorizationPolicy`:
  <https://linkerd.io/2/features/server-policy/>
- **Linkerd — Proxy resources** — why the proxy is small; the memory/latency profile:
  <https://linkerd.io/2/reference/proxy-metrics/>

## Cilium + eBPF (Wednesday)

- **Cilium — Getting started / install** — install the CNI + service mesh on Kind:
  <https://docs.cilium.io/en/stable/gettingstarted/>
- **Cilium — eBPF datapath** — how packets move through the kernel without a userspace proxy:
  <https://docs.cilium.io/en/stable/network/ebpf/>
- **Cilium — L7-aware network policy** — `CiliumNetworkPolicy` with HTTP rules (the embedded-Envoy path):
  <https://docs.cilium.io/en/stable/security/policy/language/#layer-7-examples>
- **What is eBPF? (the canonical primer)** — for the Lecture 2 background:
  <https://ebpf.io/what-is-ebpf/>

## The honest comparison (Thursday/Friday)

- **CNCF — service mesh project comparisons** — survey, not marketing; read several:
  <https://www.cncf.io/projects/>
- **Linkerd vs Istio (Linkerd's own framing — read critically)**:
  <https://linkerd.io/2/getting-started/>
- **Istio ambient vs sidecar (from Week 8)** — the third data-plane model in the comparison:
  <https://istio.io/latest/docs/ambient/overview/>
- **ADR (Architectural Decision Record) — the format** — Michael Nygard's original write-up:
  <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>

## Multi-cluster (stretch)

- **Linkerd — Multi-cluster** — the gateway model for cross-cluster traffic:
  <https://linkerd.io/2/features/multicluster/>
- **Cilium — ClusterMesh** — eBPF-native cross-cluster service discovery and policy:
  <https://docs.cilium.io/en/stable/network/clustermesh/clustermesh/>

## Talks worth your time (free, no signup)

- **KubeCon service-mesh comparison sessions** — the three-mesh debate, rehearsed publicly each cycle, on the CNCF YouTube:
  <https://www.youtube.com/c/cloudnativefdn>
- **eBPF Summit talks** — the Cilium maintainers on the kernel datapath:
  <https://ebpf.io/summit-2024/>
- **"Linkerd: a minimalist service mesh"** — search the CNCF channel for the design-philosophy talks from the Linkerd team.

## Tools you'll use this week

- **`linkerd`** — install (`linkerd install | kubectl apply -f -`), inject (`linkerd inject`), check (`linkerd check`), and the live `linkerd viz` dashboard + `linkerd viz stat`.
- **`cilium`** — install (`cilium install`), status (`cilium status`), connectivity test (`cilium connectivity test`), and Hubble for observability.
- **`fortio` / `ghz`** — the same load generators as Week 8, so the benchmark is comparable.
- **`kubectl top`** — per-pod (Linkerd proxy) and per-node (Cilium) memory/CPU for the resource comparison.
- **`hubble`** — Cilium's flow-observability CLI/UI; the eBPF equivalent of Kiali for seeing traffic.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Linkerd** | A minimalist CNCF service mesh; tiny Rust sidecar, simple by design. |
| **`linkerd2-proxy`** | Linkerd's purpose-built Rust micro-proxy — does only mesh-sidecar work, far smaller than Envoy. |
| **Cilium** | A CNI + service mesh built on eBPF; L4 + mTLS in the kernel, no per-pod proxy. |
| **eBPF** | Extended Berkeley Packet Filter — safe sandboxed programs the kernel runs on events (packets, syscalls). |
| **Datapath** | The path a packet takes through the system; in Cilium, mostly the kernel via eBPF. |
| **Sidecar-less** | A mesh with no per-pod proxy (Cilium's kernel path, Istio ambient's ztunnel). |
| **Embedded Envoy** | Cilium's per-node Envoy, used only for L7 (HTTP routing/policy), not for L4. |
| **Hubble** | Cilium's flow-observability layer — sees traffic via eBPF, like Kiali for Istio. |
| **Linkerd identity** | Linkerd's automatic-mTLS identity system (its own CA, certs per workload). |
| **`CiliumNetworkPolicy`** | Cilium's policy CRD; L3/L4 in the kernel, L7 via the embedded Envoy. |
| **`ServerAuthorization`** | Linkerd's authz primitive (with `Server`) — who may call a meshed port. |
| **ADR** | Architectural Decision Record — a short doc: context, options, decision, consequences, reversal conditions. |
| **Latency overhead** | The extra p50/p99 a mesh adds vs direct calls — the headline benchmark number. |
| **Decision axes** | Cost, ops complexity, L7 depth, mTLS model, multi-cluster, maturity — what drives a mesh choice. |

---

*If a link 404s, please open an issue so we can replace it.*
