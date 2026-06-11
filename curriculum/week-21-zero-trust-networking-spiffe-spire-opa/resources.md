# Week 21 — Resources

Every resource here is **free** and **open**. SPIFFE, SPIRE, OPA, Gatekeeper, and Kyverno are all CNCF projects (SPIFFE/SPIRE graduated; OPA graduated; Kyverno incubating) with openly published, versioned docs. No paywalled material is linked.

This week targets **SPIRE 1.9+** (the line where the Kubernetes attestors and the SPIFFE CSI driver are mature), **OPA 0.6x+ / Rego v1**, **Gatekeeper 3.1x+**, and **Kyverno 1.1x+**. When a link is to `latest`, the *concepts* are stable; only occasional field/flag names move, so pin to your installed version.

## Required reading (work it into your week)

- **SPIFFE — Overview / "SPIFFE concepts"** — the SPIFFE ID, the SVID, the trust bundle, the Workload API. Read it Monday and again Friday:
  <https://spiffe.io/docs/latest/spiffe-about/overview/>
- **SPIRE — "Understanding SPIRE"** — the server, the agent, node and workload attestation, the registration model:
  <https://spiffe.io/docs/latest/spire-about/spire-concepts/>
- **OPA — "Introduction" + "Policy Language (Rego)"** — the input/data/decision model and the Rego basics you'll write all week:
  <https://www.openpolicyagent.org/docs/latest/>
- **OPA — Rego policy language** — the language reference for the authz policy:
  <https://www.openpolicyagent.org/docs/latest/policy-language/>
- **NIST SP 800-207 — Zero Trust Architecture** — the canonical definition of zero trust; read the tenets (especially "all resource authentication and authorization are dynamic and strictly enforced before access"):
  <https://csrc.nist.gov/pubs/sp/800/207/final>

## SPIFFE / SPIRE in depth (skim, then refer back)

- **SPIRE — Kubernetes quickstart** — deploying the server + agent on Kubernetes, the path the exercise follows:
  <https://spiffe.io/docs/latest/try/getting-started-k8s/>
- **SPIFFE — SVID (X.509 and JWT)** — the credential formats; where the SPIFFE ID lives in the cert (the URI SAN):
  <https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/#spiffe-verifiable-identity-document-svid>
- **SPIRE — Node attestation** — how the agent proves its node to the server (the k8s/`k8s_psat`/AWS/etc. attestors):
  <https://spiffe.io/docs/latest/spire-about/spire-concepts/#node-attestation>
- **SPIRE — Workload attestation & the Workload API** — how a workload gets its SVID with no secret to hold:
  <https://spiffe.io/docs/latest/spire-about/spire-concepts/#workload-attestation>
- **SPIFFE CSI driver** — mounting the Workload API socket into pods, the modern delivery path:
  <https://github.com/spiffe/spiffe-csi>

## OPA, Rego, and admission control

- **OPA — Gatekeeper** — the Kubernetes admission controller built on OPA/Rego (ConstraintTemplates + Constraints):
  <https://open-policy-agent.github.io/gatekeeper/website/docs/>
- **OPA — `opa test` (policy testing)** — Rego unit tests; you'll write tests for the authz policy:
  <https://www.openpolicyagent.org/docs/latest/policy-testing/>
- **Kyverno — documentation** — the Kubernetes-native (YAML, no Rego) policy alternative to Gatekeeper:
  <https://kyverno.io/docs/>
- **Kyverno vs Gatekeeper (community comparisons)** — read a couple to form your own view; the tradeoff is Rego's power/reuse vs Kyverno's k8s-native ergonomics.

## Zero-trust references

- **BeyondCorp (Google)** — the production zero-trust paper that popularized "identity, not network location, is the perimeter":
  <https://research.google/pubs/pub43231/>
- **"Zero Trust Networks" (Gilman & Barth)** — the book-length treatment; the framing for the threat-model homework. Widely available.
- **SPIFFE — "Use cases"** — federation across trust domains, the multi-region story you do in the stretch:
  <https://spiffe.io/docs/latest/spiffe-about/use-cases/>

## Tools you'll use this week

- **SPIRE server + agent** (`spire-server`, `spire-agent`) — deployed on Kind; you'll register workloads and inspect SVIDs.
- **`spire-server entry` CLI** — create registration entries that map a SPIFFE ID to an attestation selector (the k8s service account / namespace).
- **`opa`** — run policy locally (`opa eval`, `opa test`), and as a server (`opa run -s`) for request-time decisions.
- **Gatekeeper** and/or **Kyverno** — admission control (the stretch and the mini-project's "what may run" gate).
- **`openssl` / `spiffe-tls`** — decode an SVID and read the SPIFFE ID out of the URI SAN.
- **The Week-8 Istio mesh** — SPIRE can supply the identities Istio uses; the two compose for the cart's mTLS.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Zero trust** | No workload is trusted by network *location*; every workload proves its identity and every access is authorized, on every request. "Identity is the perimeter." |
| **SPIFFE** | A standard for workload identity: a universal naming scheme (the SPIFFE ID) and credential format (the SVID). |
| **SPIFFE ID** | A URI naming a workload: `spiffe://<trust-domain>/<path>`, e.g. `spiffe://shop/ns/shop/sa/cart`. |
| **SVID** | SPIFFE Verifiable Identity Document — the credential proving a SPIFFE ID: an X.509 cert (ID in a URI SAN) or a JWT. |
| **Trust bundle** | The set of CA certificates that validate SVIDs within a trust domain (and, when federated, across domains). |
| **Trust domain** | The identity boundary (`spiffe://shop`); SVIDs from a different trust domain are not trusted unless federated. |
| **SPIRE** | The reference SPIFFE runtime: a server (CA/signing) + agents (per-node attestation + Workload API). |
| **SPIRE server** | The trust domain's signing authority: issues and rotates SVIDs, holds the CA, stores registration entries. |
| **SPIRE agent** | Per-node: attests its node to the server, attests local workloads, serves SVIDs over the Workload API. |
| **Node attestation** | The agent proving *which node* it runs on to the server (via a k8s/AWS/etc. attestor) before it can get SVIDs. |
| **Workload attestation** | The agent proving a *workload's* identity by inspecting it (kubelet metadata, uid, service account) — no secret held by the workload. |
| **Workload API** | The local (Unix-socket) API a workload calls to fetch its SVID and trust bundle, and over which they auto-rotate. |
| **No secret zero** | The property that a workload never holds a long-lived credential to be stolen — it proves *what it is* and is *handed* a short-lived SVID. |
| **SVID rotation** | Automatic refresh of short-lived SVIDs before expiry over the Workload API; transparent to the app; a stolen SVID expires in minutes. |
| **OPA** | Open Policy Agent — a general policy engine that answers allow/deny given an `input`. |
| **Rego** | OPA's declarative policy language: `input` (the request) + `data` (reference data) → a decision (`allow`). |
| **Gatekeeper** | OPA-based Kubernetes admission controller (Rego ConstraintTemplates + Constraints) — "what may run." |
| **Kyverno** | Kubernetes-native (YAML, no Rego) policy engine — the admission-control alternative to Gatekeeper. |
| **Admission control** | Deciding which Kubernetes resources may be *created* (a validating/mutating webhook) — "what may run." |
| **Request-time authz** | Deciding which service-to-service *calls* may proceed, per request — "what may talk." |

---

*If a link 404s, please open an issue so we can replace it.*
