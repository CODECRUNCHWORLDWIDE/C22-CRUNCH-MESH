# Exercise 1 — Deploy SPIRE and Issue SVIDs

**Goal:** Deploy the SPIRE **server** and **agent** on your Kind cluster, register `cart` and `inventory` as workloads, have them receive SVIDs over the Workload API, and *inspect* the SPIFFE identity baked into the X.509 SVID — the URI SAN that says `spiffe://shop/ns/shop/sa/cart`. By the end you've issued verifiable workload identity from *attestation* (no secret distributed) and confirmed it on the wire — the foundation everything else this week builds on.

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need a Kind cluster and `kubectl`. SPIRE installs via the published Kubernetes quickstart manifests.

```bash
kubectl get nodes          # Ready
kubectl create namespace spire
```

**Fallback if your Phase 1 services aren't ready.** SPIRE ships sample `client`/`server` workloads in the quickstart; the whole exercise works with those as stand-ins for `cart`/`inventory`. Wherever this says `cart`/`inventory`, substitute the SPIRE sample workloads.

---

## Step 1 — Deploy the SPIRE server (the trust domain's CA)

The SPIRE server is the signing authority for the trust domain. Its config sets the **trust domain** (we'll use `shop`) and the **node attestor** (`k8s_psat` — projected service account tokens, the Kubernetes way an agent proves its node).

```bash
# (Using the SPIRE Kubernetes quickstart manifests; key config shown.)
# spire-server ConfigMap (excerpt):
#   trust_domain = "shop"
#   NodeAttestor "k8s_psat" { ... }   # agents attest their node via projected SA tokens
#   KeyManager / Datastore ...        # the CA keys + the registration-entry store

kubectl apply -f spire-server.yaml -n spire
kubectl rollout status statefulset/spire-server -n spire
```

Confirm the server is up and is the CA for `shop`:

```bash
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server healthcheck
# Server is healthy.
```

---

## Step 2 — Deploy the SPIRE agent (per-node attestation + Workload API)

The agent runs on every node (a DaemonSet). It **attests its node** to the server, then **attests workloads** and serves them SVIDs over the **Workload API** (a Unix socket the workloads call).

```bash
kubectl apply -f spire-agent.yaml -n spire     # DaemonSet
kubectl rollout status daemonset/spire-agent -n spire
```

Confirm the agent attested its node to the server (the node now has an identity):

```bash
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server agent list
# Found 1 attested agent:
# SPIFFE ID : spiffe://shop/spire/agent/k8s_psat/...   <- the NODE's identity
```

The agent proved *which node it is* using the platform's own attestation (the projected SA token validated against the k8s API) — **no secret you distributed.** That's node attestation.

---

## Step 3 — Register the workloads (the identity rules)

A **registration entry** maps "a workload with these attested properties" → "this SPIFFE ID." We register `cart` and `inventory` against their Kubernetes service accounts, so the agent will hand the correct SVID to whichever pod is genuinely running as that service account.

```bash
# Register cart: any workload attested as ns=shop, sa=cart gets spiffe://shop/ns/shop/sa/cart
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://shop/ns/shop/sa/cart \
  -parentID spiffe://shop/spire/agent/k8s_psat/<node-attestor-id> \
  -selector k8s:ns:shop \
  -selector k8s:sa:cart

# Register inventory likewise:
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://shop/ns/shop/sa/inventory \
  -parentID spiffe://shop/spire/agent/k8s_psat/<node-attestor-id> \
  -selector k8s:ns:shop \
  -selector k8s:sa:inventory
```

The **selectors** (`k8s:ns:shop`, `k8s:sa:cart`) are the *attestation criteria*: a workload gets `spiffe://shop/ns/shop/sa/cart` *only if* the agent attests it really is running in namespace `shop` under service account `cart`. A pod that *claims* to be cart but runs under a different service account does **not** match — it can't get cart's identity, because identity comes from *what the workload is* (attested), not what it asserts.

```bash
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry show
# 2 entries: cart, inventory — each bound to its k8s namespace+service-account selectors.
```

---

## Step 4 — Deploy cart with the Workload API mounted

The workload reaches the agent's Workload API over a Unix socket, mounted via the SPIFFE CSI driver (or a hostPath to the agent socket). Deploy `cart` under its `cart` service account with the socket mounted:

```yaml
# cart-deploy.yaml (excerpt) — runs as serviceAccountName: cart, mounts the Workload API socket
spec:
  serviceAccountName: cart                  # <- this is what the agent attests
  containers:
  - name: cart
    image: <your-cart-image>
    volumeMounts:
    - name: spiffe-workload-api
      mountPath: /spiffe-workload-api
      readOnly: true
  volumes:
  - name: spiffe-workload-api
    csi:
      driver: csi.spiffe.io                 # the SPIFFE CSI driver mounts the agent socket
      readOnly: true
```

```bash
kubectl create serviceaccount cart -n shop
kubectl apply -n shop -f cart-deploy.yaml
kubectl rollout status deploy/cart -n shop
```

---

## Step 5 — Inspect the SVID (the proof)

Now confirm `cart` actually received an SVID carrying its SPIFFE identity. Fetch it via the Workload API and decode the cert — the SPIFFE ID lives in the **URI SAN**:

```bash
# Ask the Workload API (from inside the cart pod) for the current SVID:
kubectl exec -n shop deploy/cart -- \
  /opt/spire/bin/spire-agent api fetch x509 \
  -socketPath /spiffe-workload-api/spire-agent.sock -write /tmp/

# Decode the issued cert and read the URI SAN:
kubectl exec -n shop deploy/cart -- \
  openssl x509 -in /tmp/svid.0.pem -noout -text | grep -A1 "Subject Alternative Name"
# URI:spiffe://shop/ns/shop/sa/cart       <-- the verifiable identity, in the cert
```

`URI:spiffe://shop/ns/shop/sa/cart` in the SAN is the proof: `cart` holds a cert that *cryptographically asserts* its SPIFFE identity, signed by the `shop` trust domain's CA. A peer that has the trust bundle can validate it. And critically — **`cart` never held a secret to get this.** It proved what it is (attested as ns=shop/sa=cart) and was *handed* this short-lived cert. No secret zero.

---

## Step 6 — Confirm it's short-lived (rotation is coming)

Check the SVID's validity window — it's short by design:

```bash
kubectl exec -n shop deploy/cart -- openssl x509 -in /tmp/svid.0.pem -noout -dates
# notBefore=...    notAfter=... (an hour or less from now)
```

A short lifetime means a stolen SVID is worthless in minutes. SPIRE will rotate it automatically over the Workload API before it expires (the stretch lets you *watch* that happen). The certificate-expiry outage (Week 8 §5.2) is designed out — *unless* the SPIRE server is down longer than the SVID TTL, which is the failure mode you'll put in the runbook.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `spire-server agent list` shows the node attested (the agent proved its node — node attestation).
- [ ] `spire-server entry show` shows registration entries for `cart` and `inventory`, each bound to `k8s:ns:` + `k8s:sa:` selectors.
- [ ] `cart` (running under its `cart` service account) received an X.509 SVID via the Workload API.
- [ ] You decoded the SVID and confirmed `URI:spiffe://shop/ns/shop/sa/cart` in the **URI SAN**.
- [ ] You confirmed the SVID is short-lived (notAfter is an hour or less out).
- [ ] You can state, in one sentence, why `cart` getting this identity required **no secret** to be distributed to it (it proved what it is by attestation).

---

## Stretch

- **Watch a rotation.** Configure a short SVID TTL (a couple of minutes) and stream the Workload API (`spire-agent api watch`); observe a *fresh* SVID arrive before the old one expires, with the workload serving throughout — rotation-without-downtime, made visible.
- **Prove attestation can't be spoofed.** Deploy a pod under a *different* service account (say `frontend`) that *tries* to obtain cart's identity. Show it receives `frontend`'s SVID (or none), *not* cart's — because the agent attests what it actually *is*, not what it claims. This is why selectors are the security boundary.
- **No-secret-zero, demonstrated.** Show the cart pod has *no* long-lived credential on disk or in env — only the Workload API socket. Contrast with mounting a static cert/key Secret (the old model) that a filesystem read would steal.

---

When this feels comfortable, move to [Exercise 2 — The SPIFFE-keyed OPA policy](./exercise-02-opa-spiffe-authz.rego).
