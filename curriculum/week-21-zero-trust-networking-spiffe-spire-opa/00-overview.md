# Week 21 — Zero-Trust Networking: SPIFFE, SPIRE, OPA

Welcome to the week the perimeter dies. For most of this course the network has been a place you *trusted* once a request was inside it — the mesh encrypted the hops (Week 8), but the implicit model was still "in the cluster is safe, outside is not." That model is a fiction, and an expensive one: the moment an attacker lands a single pod — a compromised dependency, a leaked token, a supply-chain payload — a perimeter-trust network lets them move laterally to *everything*, because everything inside trusts everything else inside. This week you replace that fiction with **zero trust**: nothing is trusted by location; every workload proves *who it is* cryptographically, and every access is *authorized* against an explicit policy, on every request, regardless of where it came from.

We assume you finished Week 8 (Istio mTLS, `AuthorizationPolicy`, the SPIFFE identity baked into every cert) and Week 19/20 (the cart, now active-active across two regions). That literacy is load-bearing this week, because **you already met SPIFFE — Istio used it implicitly.** This week you deploy it *explicitly* with **SPIRE**, the reference SPIFFE runtime, so the identity isn't a thing Istio happens to issue but a thing you operate, attest, and rotate yourself. And you move policy out of the mesh's `AuthorizationPolicy` CRDs into **OPA** (Open Policy Agent) with **Rego**, so authorization is *policy as code* — versioned, tested, and enforced both at the admission gate (what may run) and at the request gate (what may talk).

The one sentence to internalize before you read another line: **identity is the new perimeter.** The old question was "is this request coming from inside the network?" — and the answer was always yes for an attacker who got one foothold. The new question is "can this workload *cryptographically prove* it is the `cart` service, and is the `cart` service *authorized* by an explicit policy to make *this* call?" — and a stolen foothold can't answer it, because it can't forge a SPIFFE SVID it was never attested for, and it can't satisfy a Rego policy that names exactly which identities may do what. SPIFFE gives you the verifiable identity; SPIRE issues and rotates it from node and workload *attestation* (proving a workload is what it claims by *what it is*, not what secret it holds); OPA decides what each identity may do. That triad — issue identity, prove identity, authorize identity — is the zero-trust loop, and closing it on your multi-region cart is this week's work.

This week is where "the network is secure" stops meaning "we encrypted it" and starts meaning "every workload is identified and every access is authorized — there is no trusted inside."

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the SPIFFE standard — the SPIFFE ID (`spiffe://trust-domain/path`), the SVID (the X.509 or JWT credential that carries it), and the trust bundle — and why a *cryptographically verifiable workload identity* is the foundation zero trust is built on.
- **Deploy and operate** SPIRE: the SPIRE **server** (the CA / signing authority for a trust domain) and the SPIRE **agent** (the per-node component that attests workloads and hands them SVIDs), and explain **node attestation** and **workload attestation** — how SPIRE proves a workload *is* what it claims without the workload holding a long-lived secret.
- **Issue SVIDs** to workloads via registration entries and the **Workload API**, and explain why this beats the bootstrapping problem of distributing secrets — the workload proves *what it is* (its kubelet-attested identity) and receives a short-lived cert, with **no secret zero** to leak.
- **Rotate mTLS without downtime**: explain SPIRE's automatic SVID rotation (short-lived certs refreshed before expiry over the Workload API), why short lifetimes are a *security* feature (a stolen SVID is useless in minutes), and how rotation happens with zero service interruption.
- **Write OPA policy in Rego**: the `allow`/`deny` decision model, input/data separation, and policies that authorize service-to-service access keyed on SPIFFE identity — moving authorization from mesh CRDs to versioned, testable policy-as-code.
- **Enforce policy at two gates**: **admission** (OPA Gatekeeper / Kyverno deciding what Kubernetes resources may be *created* — no privileged pods, required labels, image provenance) and **request-time** (OPA authorizing service calls), and explain the difference between "what may run" and "what may talk."
- **Compare** OPA/Gatekeeper with **Kyverno** (the Kubernetes-native policy alternative) and choose between them for an admission-control use case with evidence.
- **Close the zero-trust loop** on the multi-region cart: SPIRE-issued SPIFFE identities on every cart/inventory/payment workload, mTLS via those identities, OPA enforcing namespace-and-identity-level access, and a *deliberate violation* that the policy *denies* — proving the loop is enforcing, not decorating.

## Prerequisites

This week assumes you have completed **C22 weeks 1–20**, or have equivalent fluency. Specifically:

- The **Week 8 SPIFFE/mTLS** literacy: you've seen `spiffe://cluster.local/ns/<ns>/sa/<sa>` identities, `PeerAuthentication` STRICT, and `AuthorizationPolicy`. This week makes the identity explicit (SPIRE) and the policy programmable (OPA).
- The **two-region, active-active cart** from Weeks 19–20: the system you'll secure end-to-end with SPIFFE identities and OPA policy across regions.
- The **`cart`/`inventory`/`payment` services** from Phase 1–2, deployable to the cluster as gRPC servers — these are the workloads that get SVIDs and policy.
- **Kubernetes** comfort: service accounts, namespaces, admission webhooks, CRDs, `kubectl apply` and `kubectl describe` — because SPIRE attests against Kubernetes identity and admission control runs as a webhook.
- The **Week 8 mesh**: SPIRE can issue the identities Istio uses, so the two compose; you'll wire SPIFFE identities into the mesh's mTLS.
- Comfort reading **a small DSL** — Rego is a declarative policy language; if you can read SQL or a config language, you can read Rego.

You do **not** need prior SPIFFE/SPIRE or OPA experience. We start at the SPIFFE concepts and build up to a SPIRE deployment, OPA admission and request-time policy, and the deliberate-violation proof that the zero-trust loop is closed.

## Topics covered

- **SPIFFE — the standard**: the **SPIFFE ID** (`spiffe://<trust-domain>/<path>`, a URI naming a workload), the **SVID** (the credential — an X.509 cert with the SPIFFE ID in a URI SAN, or a JWT — that *proves* the identity), and the **trust bundle** (the set of CA certs that validate SVIDs in a trust domain). Why a standard identity beats per-system bespoke identity, and how it federates across trust domains.
- **SPIRE — the runtime**: the **SPIRE server** (the trust domain's signing authority — issues and rotates SVIDs, holds the CA), the **SPIRE agent** (per-node, attests workloads and serves the Workload API), **node attestation** (the agent proves the *node* it runs on to the server, via a k8s/AWS/etc. attestor), and **workload attestation** (the agent proves a *workload's* identity by inspecting it — its kubelet metadata, its Unix uid, its k8s service account — without the workload holding any secret).
- **The no-secret-zero property**: why SPIFFE/SPIRE solves the bootstrapping problem that plagues secret-distribution — a workload never *holds* a long-lived credential to be stolen; it proves *what it is* (attestation) and is *handed* a short-lived SVID over a local Unix socket (the Workload API). There is no "secret zero" to leak.
- **SVID rotation without downtime**: short-lived SVIDs (minutes to an hour) refreshed automatically over the Workload API before expiry, why short lifetimes shrink the value of a stolen credential to near zero, and how the rotation is transparent to the application (the SPIFFE library / mesh swaps the cert under the hood).
- **OPA and Rego — policy as code**: Open Policy Agent as a general policy engine; **Rego** as its declarative language; the **input/data/decision** model (`input` = the request, `data` = the policy's reference data, the policy computes `allow`); and authorization decisions keyed on the SPIFFE identity of the caller.
- **Two enforcement gates**: **admission control** (OPA **Gatekeeper** as a validating admission webhook deciding which Kubernetes resources may be *created* — deny privileged pods, require provenance, enforce labels) versus **request-time authorization** (OPA deciding which service-to-service calls may proceed). "What may run" vs "what may talk."
- **Gatekeeper vs Kyverno**: OPA Gatekeeper (Rego-based, the general-purpose policy engine on Kubernetes) versus **Kyverno** (Kubernetes-native, YAML-based policies, no Rego) — the tradeoff (Rego's power and reusability vs Kyverno's lower learning curve and k8s-native ergonomics) and when each wins.
- **Closing the loop on the cart**: SPIRE issuing SVIDs to every cart/inventory/payment workload across both regions, mTLS via those SPIFFE identities, OPA policy enforcing that (e.g.) only `order` may call `payment` and only same-trust-domain workloads talk across regions, and a **deliberate violation** (a workload with the wrong identity, or a disallowed call) that the policy **denies** — the proof the zero-trust loop is enforcing.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Zero-trust; SPIFFE IDs, SVIDs, trust bundles            |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | SPIRE server/agent; node + workload attestation         |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | SVID issuance + rotation; the Workload API; no secret-0  |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | OPA + Rego; request-time authz; SPIFFE-keyed policy      |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Admission control: Gatekeeper vs Kyverno; the violation  |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                  |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, threat-model polish                      |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./00-overview.md) | This overview (you are here) |
| [resources.md](./01-resources.md) | The SPIFFE/SPIRE docs, the OPA/Rego material, the zero-trust references worth your time |
| [lecture-notes/01-spiffe-spire-workload-identity-and-attestation.md](./02-lecture-notes/01-spiffe-spire-workload-identity-and-attestation.md) | Zero trust, SPIFFE IDs/SVIDs/bundles, SPIRE server/agent, node + workload attestation, rotation, no-secret-zero |
| [lecture-notes/02-opa-rego-policy-as-code-and-admission-control.md](./02-lecture-notes/02-opa-rego-policy-as-code-and-admission-control.md) | OPA/Rego, request-time authz keyed on SPIFFE identity, admission control, Gatekeeper vs Kyverno, closing the loop |
| [exercises/README.md](./03-exercises/00-overview.md) | Index of the three exercises |
| [exercises/exercise-01-deploy-spire-issue-svids.md](./03-exercises/exercise-01-deploy-spire-issue-svids.md) | Deploy SPIRE server + agent, register cart/inventory, issue SVIDs, and inspect the SPIFFE identity in the cert |
| [exercises/exercise-02-opa-spiffe-authz.rego](./03-exercises/exercise-02-opa-spiffe-authz.rego) | A complete Rego policy authorizing service-to-service calls by SPIFFE identity, with the allow/deny matrix and tests |
| [exercises/exercise-03-zero-trust-violation-probe.py](./03-exercises/exercise-03-zero-trust-violation-probe.py) | Probe the closed loop: an allowed identity passes; a wrong/forged identity and a disallowed call are both DENIED |
| [challenges/README.md](./04-challenges/00-overview.md) | Index of the weekly challenge |
| [challenges/challenge-01-the-over-broad-policy.md](./04-challenges/challenge-01-the-over-broad-policy.md) | A Rego policy that *looks* zero-trust but allows everything via an over-broad rule — find the lateral-movement hole and close it |
| [quiz.md](./05-quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./06-homework.md) | Six problems including the zero-trust threat-model memo |
| [mini-project/README.md](./07-mini-project/00-overview.md) | `cart-zerotrust`: the multi-region cart with SPIRE identities, OPA policy, rotation, and a deliberate-violation proof |

## The "the policy actually denied it" promise

C22 uses a recurring marker for every exercise that ends in the system actually enforcing what you declared. This week's canonical one is a *deliberate violation that gets denied* — zero trust you can prove, not assume:

```
$ python3 exercise-03-zero-trust-violation-probe.py
[probe] order -> payment   (SPIFFE: spiffe://shop/ns/shop/sa/order)
        VERDICT: ALLOWED  (order is authorized to call payment)            ✔
[probe] cart  -> payment   (SPIFFE: spiffe://shop/ns/shop/sa/cart)
        VERDICT: DENIED   (cart has a valid SVID but is NOT authorized)    ✔
[probe] forged -> payment  (no valid SVID / wrong trust domain)
        VERDICT: DENIED   (mTLS rejects: cannot prove identity at all)     ✔
--------------------------------------------------------------------
ZERO-TRUST LOOP CLOSED: identity is verified (SPIFFE) AND access is
authorized (OPA). A valid identity is necessary but NOT sufficient —
cart is in the mesh with a real SVID and is STILL denied payment.
```

If `cart` (a real, identified workload) is *denied* `payment` while `order` is *allowed*, and a forged identity can't even establish the connection — the loop is enforcing. The point of this week is to make that proof *ordinary*: a deliberate violation that the policy refuses, the way you made a measured failover ordinary in Week 19, and to make an *over-broad* policy (one that authorizes more than it should — the lateral-movement hole) something you catch in a test, not in a breach.

## Stretch goals

If you finish the regular work early and want to push further:

- **Federate two trust domains.** Run SPIRE in *both* Week-19 regions with *different* trust domains, federate them (exchange trust bundles), and authorize a cross-region call by the *remote* trust domain's SPIFFE identity — the multi-region zero-trust story.
- **Watch a rotation happen.** Set a short SVID TTL (a couple of minutes), stream the Workload API, and *observe* the cert rotate live with the service serving traffic throughout — rotation-without-downtime made visible.
- **Add admission policy.** Write a Gatekeeper (Rego) *and* a Kyverno (YAML) policy that both deny a privileged pod, deploy both, and write a one-paragraph comparison of the developer experience — the Gatekeeper-vs-Kyverno decision with evidence.
- **Prove no-secret-zero.** Demonstrate that a workload holds *no* long-lived credential on disk — it only ever talks to the local Workload API socket and receives a short-lived SVID — and contrast with the old model of mounting a long-lived secret that, if leaked, is game over.

## Up next

Week 22 takes the secured, multi-region, CRDT-backed system you've now built and *attacks it on purpose*: **chaos engineering and the gameday.** You'll inject region loss, broker loss, and dependency latency with chaos-mesh, run a 90-minute gameday, and write the blameless postmortems — and the zero-trust loop you closed this week is part of what must *survive* the chaos (and part of what you'll deliberately break to test: certificate expiry is one of the runbook's named failure modes). Everything across Phase 4 — multi-region (19), CRDTs (20), zero-trust (21) — now gets stress-tested as one system. Push your `cart-zerotrust` mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
