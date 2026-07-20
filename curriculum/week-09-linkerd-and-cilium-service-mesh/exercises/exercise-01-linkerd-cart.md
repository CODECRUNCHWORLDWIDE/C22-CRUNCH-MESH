# Exercise 1 — Linkerd Cart

**Goal:** Install Linkerd on a fresh Kind cluster, bring `cart` and `inventory` into the mesh, confirm that automatic mTLS is *already on* (no `PeerAuthentication` to write), and measure the proxy's overhead — latency and per-pod memory — against the Istio baseline you captured in Week 8. You will feel, directly, the difference between the maximalist mesh and the minimalist one.

**Estimated time:** 75 minutes. Guided.

---

## Setup

Use a **fresh Kind cluster** (don't try to run Linkerd alongside last week's Istio — meshes don't coexist).

```bash
kind delete cluster        # if your Istio cluster is still up
kind create cluster
linkerd version            # CLI present
```

**Fallback if your Phase 1 services aren't ready.** Linkerd's own `emojivoto` sample (`linkerd inject` + the bundled manifest) stands in for the cart topology — it's two services that talk gRPC, exactly the shape you need. Substitute it wherever this says `cart`/`inventory`.

---

## Step 1 — Pre-flight and install

Linkerd's install is a deliberate two-step, gated by a check:

```bash
# Will this cluster support Linkerd? (Catches kernel/RBAC/cluster issues up front.)
linkerd check --pre

# Install the CRDs, then the control plane.
linkerd install --crds | kubectl apply -f -
linkerd install | kubectl apply -f -

# Confirm the control plane is healthy — this is your primary diagnostic all week.
linkerd check
```

`linkerd check` is the Linkerd equivalent of `istioctl analyze` + `istioctl proxy-status` in one: a human-readable checklist of green/red. When something's wrong this week, run it first.

Install the viz extension for the dashboard and golden-signal metrics:

```bash
linkerd viz install | kubectl apply -f -
linkerd check
```

---

## Step 2 — Deploy and mesh cart/inventory

```bash
kubectl create namespace shop
kubectl apply -n shop -f cart-deployment.yaml
kubectl apply -n shop -f inventory-deployment.yaml

# Mesh them: inject the linkerd2-proxy and re-apply.
kubectl get deploy -n shop -o yaml | linkerd inject - | kubectl apply -f -
```

Confirm each pod is now `2/2` (app + the injected `linkerd-proxy`):

```bash
kubectl get pods -n shop
# cart-xxxxx        2/2   Running    <-- the linkerd2-proxy sidecar is there
# inventory-xxxxx   2/2   Running
```

---

## Step 3 — Confirm automatic mTLS is ALREADY on

This is the Linkerd "wow" moment and the contrast with Istio. You wrote a STRICT `PeerAuthentication` last week to *turn on* enforcement. In Linkerd, meshed-to-meshed traffic is mutual TLS **automatically, with no policy to write**. Verify:

```bash
linkerd viz edges deploy -n shop
# SRC    DST        SRC_NS  DST_NS  SECURED
# cart   inventory  shop    shop    √          <-- the checkmark = mTLS, no config
```

```bash
# Or watch live traffic and see the tls=true marker:
linkerd viz tap deploy/cart -n shop | grep -m3 tls
# ... tls=true ...
```

`SECURED √` and `tls=true` are the proof: cart→inventory is encrypted and mutually authenticated, and you didn't apply a single security CRD. Note this in your writeup — it's the single clearest difference from Istio's available-but-not-enforced default.

---

## Step 4 — Measure the overhead

Now the number that feeds your ADR. Drive the same load you used for the Week 8 Istio baseline:

```bash
# golden signals straight from Linkerd:
linkerd viz stat deploy -n shop
# NAME       MESHED  SUCCESS  RPS   LATENCY_P50  LATENCY_P99
# cart       1/1     100.00%  50    2ms          7ms
# inventory  1/1     100.00%  50    1ms          5ms

# per-pod proxy memory — the architecture made visible:
kubectl top pod -n shop --containers | grep linkerd-proxy
# cart-xxxxx   linkerd-proxy   3m   12Mi      <-- compare to your Istio sidecar (~50+ Mi)
```

Record p50, p99, and the `linkerd-proxy` memory. Put them next to your Week 8 Istio numbers. The expected shape: **Linkerd's micro-proxy is a fraction of the Istio sidecar's memory**, with comparable-or-tighter latency. You're measuring the Rust-micro-proxy bet directly.

---

## Step 5 — Mesh-vs-no-mesh delta

To isolate the mesh's tax, compare meshed latency to a direct call. Run the same load against the service *before* meshing (or against an un-meshed copy) and against the meshed path:

```bash
# Drive both and diff p50/p99. The delta IS Linkerd's latency overhead.
```

Record the delta. This is one row of the three-way table Exercise 3 builds.

---

## Step 6 — (Optional) least-privilege authz, the Linkerd way

For the stretch / to compare config volume against Istio: Linkerd's authorization uses `Server` + `AuthorizationPolicy`. Lock `inventory` to allow only `cart`:

```yaml
# A Server defines a meshed port; an AuthorizationPolicy says who may reach it.
apiVersion: policy.linkerd.io/v1beta3
kind: Server
metadata: { name: inventory-grpc, namespace: shop }
spec:
  podSelector: { matchLabels: { app: inventory } }
  port: 50051
  proxyProtocol: gRPC
---
apiVersion: policy.linkerd.io/v1alpha1
kind: AuthorizationPolicy
metadata: { name: inventory-allow-cart, namespace: shop }
spec:
  targetRef: { group: policy.linkerd.io, kind: Server, name: inventory-grpc }
  requiredAuthenticationRefs:
  - { group: policy.linkerd.io, kind: MeshTLSAuthentication, name: cart-id }
```

Note how much (or how little) config this took versus Istio's `AuthorizationPolicy` — a data point for your comparison.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `linkerd check` is all green and `cart`/`inventory` pods are `2/2`.
- [ ] `linkerd viz edges` shows the cart→inventory edge `SECURED √` **with no security CRD applied** — automatic mTLS confirmed.
- [ ] You recorded p50, p99, and `linkerd-proxy` per-pod memory, and placed them next to your Week 8 Istio numbers.
- [ ] You can state the per-pod memory difference between the Linkerd micro-proxy and the Istio sidecar (Linkerd is much smaller).
- [ ] You can state, in one sentence, the difference between Linkerd's automatic-mTLS and Istio's available-but-not-enforced default.

---

## Stretch

- Add a **Linkerd traffic split** (`HTTPRoute` / the `TrafficSplit` story) to canary cart v1→v2, and compare how it feels versus Istio's `VirtualService` weights. Less config, fewer knobs — is that a win for your use case?
- Run `linkerd viz dashboard` and explore the live topology. Compare the experience to Kiali. Which would you rather hand a new on-call engineer?
- Measure **CPU** (not just memory) under a longer, heavier `fortio` run. Linkerd's efficiency claim is partly a CPU claim; verify it on your hardware.

---

When this feels comfortable, move to [Exercise 2 — Cilium service mesh](exercise-02-cilium-mesh.yaml).
