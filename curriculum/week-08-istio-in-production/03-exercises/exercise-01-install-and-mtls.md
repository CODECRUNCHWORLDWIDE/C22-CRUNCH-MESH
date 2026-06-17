# Exercise 1 — Install Istio and Turn On mTLS STRICT

**Goal:** Install Istio on your Kind cluster, bring `cart` and `inventory` into the mesh, flip the namespace to `STRICT` mTLS, and *prove* — three independent ways — that traffic between the services is actually mutually-authenticated and encrypted, not just "the mesh is installed." You will train the single most important Istio habit of the week: confirming the mesh is *enforcing* what you declared, not assuming it.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need `istioctl` and a Kind cluster with headroom.

```bash
istioctl version          # client present
kubectl get nodes         # Ready
```

**Fallback if your Phase 1 services aren't ready.** Use the Istio sample `httpbin` and `sleep` apps as stand-ins for `inventory` (a server) and `cart` (a client) — they ship with Istio and the whole exercise works identically. Wherever this exercise says `cart`/`inventory`, substitute `sleep`/`httpbin`.

---

## Step 1 — Install Istio

Install the demo profile (good for a lab; it bundles ingress + the addons):

```bash
istioctl install --set profile=demo -y
kubectl get pods -n istio-system
# istiod, istio-ingressgateway, istio-egressgateway Running
```

Install the observability addons (Kiali, Prometheus, Grafana, Jaeger) — you'll use Kiali in Exercise 2:

```bash
kubectl apply -f samples/addons/   # from the istio release directory
```

Confirm the control plane is healthy:

```bash
istioctl proxy-status     # no proxies yet — nothing is meshed
```

---

## Step 2 — Create a meshed namespace and deploy the services

Label a namespace for **sidecar injection**, then deploy:

```bash
kubectl create namespace shop
kubectl label namespace shop istio-injection=enabled

# Deploy cart and inventory into shop (your Phase 1 manifests, or the fallback):
kubectl apply -n shop -f cart-deployment.yaml
kubectl apply -n shop -f inventory-deployment.yaml
```

Confirm each pod has **two** containers — the app and the injected `istio-proxy`:

```bash
kubectl get pods -n shop
# NAME                         READY   STATUS
# cart-xxxxx                   2/2     Running     <-- 2/2, not 1/1: the sidecar is there
# inventory-xxxxx              2/2     Running
```

`2/2` is the proof the injection webhook fired. If you see `1/1`, the namespace label is wrong or the pod predates the label — delete and recreate the pod.

Now the proxies show up in the control plane:

```bash
istioctl proxy-status
# cart-xxxxx.shop      SYNCED   SYNCED   SYNCED   SYNCED
# inventory-xxxxx.shop SYNCED   SYNCED   SYNCED   SYNCED
```

All `SYNCED` means each sidecar has istiod's latest config. A `STALE` column is your first sign of a push problem.

---

## Step 3 — Confirm you start PERMISSIVE (the gap)

Before turning on STRICT, see the default state. A fresh mesh is *permissive* — it accepts mTLS AND plaintext, so it's not yet enforcing encryption:

```bash
istioctl x describe pod -n shop $(kubectl get pod -n shop -l app=inventory -o jsonpath='{.items[0].metadata.name}')
# ... look for the PeerAuthentication line. If it's absent or PERMISSIVE,
#     plaintext is still accepted — you have the CAPABILITY, not ENFORCEMENT.
```

This is the gap the whole industry trips on: "we have a mesh, so we have mTLS." You have it *available*. Enforcement is the next step.

---

## Step 4 — Turn on STRICT mTLS

Apply a namespace-wide `PeerAuthentication` in STRICT mode:

```yaml
# strict-mtls.yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: shop
spec:
  mtls:
    mode: STRICT
```

```bash
kubectl apply -f strict-mtls.yaml
istioctl analyze -n shop      # catch any config mistake before trusting it
```

> **Migration discipline:** in production you'd go PERMISSIVE → mesh every client → verify mTLS is flowing → *then* STRICT, so you never cut off an un-meshed client. Here every client is already meshed, so STRICT is safe immediately. Note in your writeup *why* the permissive step matters even though you skipped it.

---

## Step 5 — Prove mTLS is real, three ways

This is the diagnostic muscle. Confirm enforcement with three independent signals.

**1. Effective policy:**

```bash
istioctl x describe pod -n shop $(kubectl get pod -n shop -l app=inventory -o jsonpath='{.items[0].metadata.name}')
# Effective PeerAuthentication: STRICT
```

**2. The cert is loaded in the sidecar (SPIFFE identity present):**

```bash
istioctl proxy-config secret -n shop deploy/cart -o json | jq '.dynamicActiveSecrets[].name'
# "default"
# "ROOTCA"
```

**3. The strongest signal — plaintext is now REFUSED.** Try to reach `inventory` from a pod that is *not* in the mesh (no sidecar, so it can only speak plaintext):

```bash
kubectl run plain --image=curlimages/curl -n default --rm -it --restart=Never -- \
  curl -sS http://inventory.shop.svc.cluster.local:50051/ -m 5
# connection reset / failure — STRICT refused the plaintext connection.
```

Compare with the same call from a meshed pod in `shop` (which speaks mTLS via its sidecar), which succeeds. The un-meshed call failing while the meshed call works is the wire-level proof that STRICT is enforcing, not decorating.

**Bonus — the telemetry label** (the single strongest evidence): drive a little traffic and check the metric:

```bash
kubectl exec -n shop deploy/cart -c istio-proxy -- \
  pilot-agent request GET stats/prometheus 2>/dev/null | grep connection_security_policy
# istio_requests_total{...,connection_security_policy="mutual_tls",...}
```

`connection_security_policy="mutual_tls"` is the mesh *reporting* the request it actually carried was mutually authenticated.

---

## Step 6 — Break it on purpose, then fix it

Set the namespace back to `PERMISSIVE` and re-run the un-meshed plaintext call. It now *succeeds* — because permissive accepts plaintext. That's the difference between "available" and "enforced," demonstrated. Set it back to `STRICT` and confirm the plaintext call fails again.

```bash
# flip to PERMISSIVE, plaintext works; flip to STRICT, plaintext is refused.
kubectl patch peerauthentication default -n shop --type merge -p '{"spec":{"mtls":{"mode":"PERMISSIVE"}}}'
# ...re-run the plain curl: it succeeds now...
kubectl patch peerauthentication default -n shop --type merge -p '{"spec":{"mtls":{"mode":"STRICT"}}}'
# ...re-run: it fails again. THAT toggle is enforcement.
```

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `kubectl get pods -n shop` shows `cart` and `inventory` as `2/2` (the sidecar is injected).
- [ ] `istioctl proxy-status` shows both proxies `SYNCED` across all columns.
- [ ] `istioctl x describe pod` reports `Effective PeerAuthentication: STRICT` for inventory.
- [ ] A plaintext call from an **un-meshed** pod to `inventory` **fails** under STRICT and **succeeds** under PERMISSIVE — you demonstrated the difference.
- [ ] The `istio_requests_total` metric carries `connection_security_policy="mutual_tls"` for the cart→inventory path.
- [ ] You can state, in one sentence, why a fresh mesh has mTLS *available but not enforced* until you apply a STRICT `PeerAuthentication`.

---

## Stretch

- Re-do this in **ambient mode**: install with `istioctl install --set profile=ambient`, label the namespace `istio.io/dataplane-mode=ambient` instead of `istio-injection=enabled`, and confirm the pods are now `1/1` (no sidecar) yet `istioctl ztunnel-config` shows mTLS is still carried by the per-node ztunnel. Same encryption, no per-pod proxy.
- Add a `Sidecar` resource that scopes cart's sidecar to only discover `inventory` (not every service in the mesh) and confirm with `istioctl proxy-config clusters` that the cluster list shrank — the scale technique that keeps istiod's push cost bounded.
- Inspect the actual cert: `istioctl proxy-config secret deploy/cart -o json` and decode the SPIFFE SAN. Confirm it reads `spiffe://cluster.local/ns/shop/sa/<cart-serviceaccount>`.

---

When this feels comfortable, move to [Exercise 2 — The weighted canary](./exercise-02-weighted-canary.yaml).
