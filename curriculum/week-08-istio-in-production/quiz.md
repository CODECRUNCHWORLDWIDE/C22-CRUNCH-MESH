# Week 8 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 9. Answer key is at the bottom — don't peek.

---

**Q1.** What are istiod's three jobs?

- A) Routing, caching, and load balancing.
- B) Configuration (watch K8s + CRDs, push Envoy xDS), certificate authority (issue + rotate SPIFFE-identity certs), and sidecar injection.
- C) Running the application containers, scheduling pods, and storing logs.
- D) Terminating TLS, serving the dashboard, and billing.

---

**Q2.** A `VirtualService` and a `DestinationRule` correspond to which Envoy concepts?

- A) `VirtualService` → listeners; `DestinationRule` → endpoints.
- B) `VirtualService` → routes (matching, weights, retries, faults); `DestinationRule` → cluster config + subsets (LB, pools, outlier detection).
- C) Both map to a single Envoy filter.
- D) Neither maps to Envoy; Istio uses its own proxy.

---

**Q3.** What is the core architectural difference between sidecar mode and ambient mode?

- A) Ambient is faster because it's written in Rust.
- B) Sidecar mode runs a full Envoy per pod (full L7 on every hop, higher cost); ambient runs a per-node ztunnel for L4+mTLS cheaply and an opt-in per-namespace waypoint for L7.
- C) Ambient mode has no mTLS.
- D) Sidecar mode has no control plane.

---

**Q4.** In ambient mode, when does a request need to go through a waypoint proxy?

- A) Always — every request goes through the waypoint.
- B) Only when it needs L7 features (HTTP-attribute authz, VirtualService routing, retries, fault injection); L4+mTLS-only traffic stays on the cheaper ztunnel path.
- C) Never — waypoints are deprecated.
- D) Only for north-south traffic.

---

**Q5.** A fresh Istio install is applied to a namespace. Is traffic between its services encrypted?

- A) Yes — Istio enforces STRICT mTLS by default on install.
- B) The capability is there, but a fresh mesh is typically PERMISSIVE (accepts both mTLS and plaintext), so encryption is *available but not enforced* until you apply a STRICT `PeerAuthentication`.
- C) No — Istio never encrypts traffic.
- D) Only if you also install a separate TLS operator.

---

**Q6.** Why do you migrate mTLS PERMISSIVE → (mesh everyone) → STRICT rather than going straight to STRICT?

- A) STRICT is slower than PERMISSIVE.
- B) Going straight to STRICT on a namespace with un-meshed clients refuses their plaintext and cuts them off — an outage. Permissive accepts both during the transition so nobody is cut off until everyone is meshed.
- C) STRICT requires a license.
- D) There's no difference; the order doesn't matter.

---

**Q7.** What is the relationship between `PeerAuthentication` and `AuthorizationPolicy`?

- A) They're the same thing with different names.
- B) `PeerAuthentication` is authentication (who you are, via the mTLS channel); `AuthorizationPolicy` is authorization (what that identity may do, per request). A request must pass both.
- C) `AuthorizationPolicy` replaces `PeerAuthentication`.
- D) `PeerAuthentication` is for north-south; `AuthorizationPolicy` is for east-west.

---

**Q8.** Two pods are both in the mesh with valid mTLS certs. One calls `inventory` and succeeds; the other gets `RBAC: access denied`. Why?

- A) The second pod's cert expired.
- B) Authentication passed for both (both have valid certs), but only the first pod's SPIFFE principal is in `inventory`'s allow rules. Identity is necessary but not sufficient — authorization is a second gate.
- C) The second pod isn't really in the mesh.
- D) `inventory` is down for the second pod only.

---

**Q9.** In a weighted canary, what does the mesh give you "for free," and what must you still engineer?

- A) The mesh gives you everything, including the rollback decision.
- B) The mesh makes the weight change cheap (a config push, no restarts); you must still engineer the "notice it's going wrong and undo it" — the SLI/threshold that drives automatic rollback.
- C) The mesh gives you nothing; canary is all application code.
- D) You must engineer the proxy; the mesh handles the metrics.

---

**Q10.** What is mesh-layer fault injection for, and what's the cardinal rule about it?

- A) It's a permanent resilience feature; leave it on.
- B) It injects latency/aborts into a route to *test* whether callers handle a slow/failing dependency, without touching app code — and the rule is to DELETE it when done (leaving it in a live namespace is a self-inflicted outage).
- C) It speeds up slow services.
- D) It's only available in ambient mode.

---

**Q11.** You instrument your apps with OpenTelemetry, mesh them, and the trace breaks at `cart` instead of continuing to `inventory`. Why?

- A) The mesh doesn't support tracing.
- B) The mesh emits the network spans, but your app must *propagate* the tracing headers (`traceparent`/B3) from inbound to outbound requests; if cart doesn't forward them, the trace breaks at cart.
- C) `inventory` isn't meshed.
- D) STRICT mTLS strips tracing headers.

---

**Q12.** A service ran fine un-meshed and now crash-loops after joining the mesh. The app makes a network call at startup. What is the most likely cause and the correct fix?

- A) The app code changed; revert it.
- B) The sidecar startup-ordering race: the app's startup call fires before the sidecar Envoy is ready to proxy it. Fix: `holdApplicationUntilProxyStarts: true` (wait for the proxy), NOT removing the sidecar.
- C) The image is corrupt; rebuild it.
- D) The namespace label is wrong; the pod isn't actually meshed.

---

**Q13.** Why is `istioctl proxy-config` (not your CRD YAML) the ground truth when debugging the mesh?

- A) The CRD YAML is encrypted.
- B) The CRD is what you *asked for*; `proxy-config` shows what istiod *actually pushed to the proxy* — and they differ when a push is stale, a port is mis-named, or a policy is in the wrong namespace. The proxy's real config is what carries traffic.
- C) `proxy-config` is faster to read.
- D) There's no difference; they're always identical.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Config/xDS, the CA (SPIFFE-identity certs + rotation), and the injection webhook. (Lecture 1 §1.1.)
2. **B** — `VirtualService`→routes, `DestinationRule`→cluster+subsets. The mapping that makes Istio legible. (Lecture 1 §2; Lecture 2 §1.1.)
3. **B** — Per-pod Envoy (full L7, higher cost) vs per-node ztunnel (L4+mTLS, cheap) + opt-in waypoint (L7). (Lecture 1 §1.2–1.3.)
4. **B** — Only L7 traffic needs the waypoint; L4+mTLS stays on ztunnel. That opt-in is ambient's cost savings. (Lecture 1 §1.3.)
5. **B** — Capability present, but PERMISSIVE by default; not enforced until STRICT. The industry's favorite false sense of security. (Lecture 1 §3.2.)
6. **B** — Straight-to-STRICT cuts off un-meshed clients; permissive bridges the transition. (Lecture 1 §3.2.)
7. **B** — Authn (channel/identity) vs authz (per-request permission); both required. (Lecture 1 §4.2.)
8. **B** — Both authenticate; only one is authorized. Identity is necessary, not sufficient. (Lecture 1 §4.1; Exercise 3.)
9. **B** — The weight change is free; the SLI-driven notice-and-undo is the engineering. (Lecture 2 §1.3.)
10. **B** — A resilience *test*, code-free; delete it when done. (Lecture 2 §2.1.)
11. **B** — The mesh gives network spans; header propagation across your app logic is still your job. (Lecture 2 §2.2.)
12. **B** — The startup race; fix with `holdApplicationUntilProxyStarts`, not by un-meshing. (Lecture 2 §3.2; Challenge 1.)
13. **B** — `proxy-config` is what's actually on the proxy; the CRD is only intent, and they diverge on stale pushes / mis-named ports / wrong-namespace policies. (Lecture 2 §3.3; Lecture 1 §5.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
