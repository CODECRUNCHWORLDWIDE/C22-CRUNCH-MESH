# Week 21 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 22. Answer key is at the bottom — don't peek.

---

**Q1.** What is the core idea of zero trust, summarized as "identity is the new perimeter"?

- A) Encrypt everything and trust the encrypted network.
- B) No workload is trusted because of its network *location*; every workload must prove its identity and every access must be authorized against explicit policy, on every request. A foothold buys only that workload's identity and authorizations, not the run of the network.
- C) Put a stronger firewall around the cluster.
- D) Only allow traffic from known IP ranges.

---

**Q2.** What is a SPIFFE ID, and what is an SVID?

- A) They're the same thing.
- B) A SPIFFE ID is a URI *naming* a workload (`spiffe://trust-domain/path`); an SVID is the *credential that proves* it (an X.509 cert with the ID in a URI SAN, or a JWT). The ID is a claim; the SVID is the proof.
- C) A SPIFFE ID is the private key; the SVID is the public key.
- D) A SPIFFE ID is for users; an SVID is for services.

---

**Q3.** What does the SPIRE *server* do versus the SPIRE *agent*?

- A) They're redundant copies of each other.
- B) The server is the trust domain's CA/signing authority (issues + rotates SVIDs, holds registration entries); the agent runs per-node, attests its node to the server, attests local workloads, and serves SVIDs over the Workload API.
- C) The server runs the apps; the agent stores logs.
- D) The agent signs certs; the server distributes them.

---

**Q4.** What is workload attestation, and why does it matter?

- A) The workload sends a password to SPIRE.
- B) The agent determines a workload's identity by *inspecting* it (its kubelet metadata, service account, uid) — proving *what it is* — rather than the workload presenting a secret. It matters because the workload holds no credential to steal.
- C) The workload attests other workloads.
- D) It's a health check.

---

**Q5.** What is the "no secret zero" property of SPIFFE/SPIRE?

- A) SPIRE uses zero secrets internally.
- B) A workload never *holds* a long-lived credential that could be stolen — it proves *what it is* (attestation) and is *handed* a short-lived SVID over a local socket. There's no bootstrap secret on disk/env to leak.
- C) Secrets are stored with zero encryption.
- D) The first secret is free.

---

**Q6.** Why are SPIRE's SVIDs short-lived, and how is rotation handled?

- A) To save storage.
- B) Short lifetimes are a *security* feature — a stolen SVID is worthless in minutes. SPIRE rotates them automatically over the Workload API before expiry, transparently to the app (the TLS stack swaps the cert; no restart). This designs out the "cert expired at 3 a.m." outage.
- C) They're long-lived; rotation is manual.
- D) Rotation requires restarting every pod.

---

**Q7.** What is OPA's input/data/decision model?

- A) Input is the policy; data is the code; decision is the output.
- B) `input` is the request being decided (e.g. caller SPIFFE ID, target, method); `data` is the policy's reference data (the allow-matrix); the policy computes a decision (conventionally `allow`). Rego evaluates the request against the rules.
- C) They're three separate databases.
- D) Input and data are the same thing.

---

**Q8.** A workload has a valid SVID but its call is denied by OPA. What does this illustrate?

- A) The SVID is invalid.
- B) Identity is *necessary but not sufficient*: mTLS verified *who* the workload is, but OPA's authorization is a second gate deciding *what* it may do — and no rule grants this call. `cart` can prove it's cart and still be denied `payment`.
- C) OPA is broken.
- D) The workload isn't really in the mesh.

---

**Q9.** What is the difference between admission control and request-time authorization?

- A) They're the same gate.
- B) Admission control decides what may be *created/run* in the cluster ("what may run" — e.g. deny privileged pods, via a validating webhook); request-time authz decides which service-to-service *calls* may proceed ("what may talk"). A complete posture needs both.
- C) Admission is for users; request-time is for services.
- D) Admission is faster.

---

**Q10.** What is the tradeoff between OPA Gatekeeper and Kyverno for admission control?

- A) Gatekeeper is free; Kyverno is paid.
- B) Gatekeeper uses Rego (powerful, expressive, one language shared with request-time authz, but a learning curve); Kyverno uses Kubernetes-native YAML (lower learning curve, can mutate/generate, but less expressive). Many orgs use Kyverno for admission and OPA for request-time.
- C) Kyverno can't do admission control.
- D) They're identical.

---

**Q11.** Why is deny-by-default the right posture, and how can it still be undermined?

- A) It can't be undermined.
- B) `default allow := false` denies anything no rule covers — so a forgotten path or an unlisted (compromised) identity is denied by omission. But it's *undermined by an over-broad rule*: if a single rule grants `*` → `*`, the default never fires because that rule covers everything. Deny-by-default + an over-broad allow = a back door.
- C) Deny-by-default blocks all traffic always.
- D) It only works with Kyverno.

---

**Q12.** Why is a SPIFFE identity an *enforceable* basis for authorization, where an IP or header isn't?

- A) IPs are slower to compare.
- B) The SPIFFE ID is read from a *cryptographically validated* SVID (the mTLS peer cert) — an attacker can't forge it without an SVID they were never attested for. An IP or header is asserted and spoofable, so a rule keyed on it isn't a real control.
- C) SPIFFE IDs are shorter.
- D) Headers can't be read by OPA.

---

**Q13.** With SPIRE handling automatic rotation, what is the remaining certificate-related failure mode?

- A) None — certs never cause problems with SPIRE.
- B) If the SPIRE *server* (the CA) is down longer than the SVID TTL, agents can't get fresh SVIDs and, as the short-lived ones expire, workloads fail to authenticate. So SPIRE-server availability gates SVID rotation — it's a named failure mode (certificate expiry) requiring server HA.
- C) The certs become too long.
- D) Rotation corrupts the trust bundle.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Identity, not location, is the perimeter; a foothold buys only that workload's identity. (Lecture 1 §1.)
2. **B** — SPIFFE ID = the name (URI); SVID = the verifiable credential proving it. (Lecture 1 §2.)
3. **B** — Server = CA/signing/registration; agent = per-node attestation + Workload API. (Lecture 1 §3.1.)
4. **B** — The agent inspects the workload to determine identity; no secret held. (Lecture 1 §3.3.)
5. **B** — No long-lived credential to steal; proves what it is, is handed a short-lived SVID. (Lecture 1 §3.4.)
6. **B** — Short lifetimes shrink a stolen cred's value; auto-rotation over the Workload API, transparent. (Lecture 1 §4.)
7. **B** — input (request) + data (reference) → decision (allow). (Lecture 2 §1.2.)
8. **B** — Identity necessary, not sufficient; authz is a second gate. (Lecture 2 §1.3; Exercise 3.)
9. **B** — Admission = what may run; request-time = what may talk; both needed. (Lecture 2 §2.)
10. **B** — Gatekeeper/Rego (powerful, shared language) vs Kyverno/YAML (ergonomic, k8s-native). (Lecture 2 §3.1.)
11. **B** — Deny-by-default only governs uncovered requests; an over-broad rule covers everything and defeats it. (Lecture 2 §1.3; Challenge.)
12. **B** — The SPIFFE ID comes from a validated SVID (unforgeable); IP/header is spoofable. (Lecture 2 §1.3; Lecture 1 §2.2.)
13. **B** — SPIRE-server down > SVID TTL → SVIDs expire → auth fails; needs server HA. (Lecture 1 §4.3.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
