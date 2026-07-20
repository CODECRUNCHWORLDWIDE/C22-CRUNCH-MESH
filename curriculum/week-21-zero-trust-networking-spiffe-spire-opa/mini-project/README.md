# Mini-Project — `cart-zerotrust`: The Multi-Region Cart, Identity-First and Policy-Enforced

> Close the zero-trust loop on the multi-region, CRDT-backed cart: SPIRE issues a verifiable SVID to every `cart`/`inventory`/`payment` workload in both regions, mTLS authenticates every hop by those SPIFFE identities, an OPA/Rego policy authorizes every call by identity (deny-by-default, least privilege, *tested*), admission control governs what may run, and — the part that makes you dangerous — a **deliberate violation that the policy denies**, proving the loop is enforcing, not decorating.

This is the artifact that turns "we have mTLS" into "every workload is identified, every access is authorized, and I can *prove* a compromised pod can't move laterally." After this week, zero trust is a *defensible posture*: identity from attestation (no secret to steal), authorization as tested code, two enforcement gates, and a demonstrated deny — so when an auditor asks "what stops a breached cart from charging cards?", you answer with a passing test, not a hope.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `cart-zerotrust` is the security layer of your **capstone Polyglot Marketplace Backbone** ("Istio service mesh with mTLS strict, SPIFFE identities via SPIRE, OPA admission policy" — the syllabus capstone spec). It sits on the Week-19 two-region substrate and the Week-20 active-active CRDT cart, securing every cross-region hop. Week 22's gameday includes **certificate expiry** as one of the runbook's named failure modes — which, with SPIRE, is the SPIRE-server-down-longer-than-the-SVID-TTL scenario you'll document here. Build the loop so the deny is *proven* (a deliberate violation refused) and the policy is *least-privilege* (no wildcards, test-covered), because that's exactly what the capstone audit and the gameday will exercise.

---

## What you will build

A repo `cart-zerotrust` with five deliverables:

1. **`identity/`** — the SPIRE deployment (server + agent) and the **registration entries** issuing a SPIFFE SVID to every `cart`/`inventory`/`payment` workload, in both Week-19 regions. Identity from attestation, no secret distributed.
2. **`authz/`** — the **OPA/Rego policy** authorizing service-to-service calls by SPIFFE identity: deny-by-default, least-privilege allow-matrix (the intended graph: `order`→`payment`, `cart`→`inventory`, `cart`↔`cart` cross-region sync, and nothing else), **with an `opa test` suite** proving the allows *and* the denies — and a lint asserting no wildcard rules (the Challenge's guard).
3. **`admission/`** — at least one **admission-control** policy (Gatekeeper *or* Kyverno) enforcing "what may run" — no privileged pods, required ownership labels, or trusted-image-only — demonstrating the second gate.
4. **`proof/`** — the **deliberate-violation proof**: the Exercise-3 probe (wired to the real mesh + OPA where possible) showing an allowed identity passes, a valid-but-unauthorized identity (`cart`→`payment`) is **denied by OPA**, and a forged/foreign identity is **rejected at mTLS**. Plus a *rotation* demonstration (a short-TTL SVID rotating with the service serving throughout).
5. **`threat-model.md`** + **`runbook.md`** — the **threat model** (what a compromised `cart` can and cannot reach, and why) and the **certificate-expiry runbook** (the SPIRE-server-availability failure mode and its handling — a Week-22 gameday scenario).

By the end you have a public repo of SPIRE identities + a tested OPA policy + an admission policy + a deliberate-violation proof + a threat model and runbook that any auditor or on-call engineer could read.

---

## Why this and not "just turn on mTLS"

You could enable strict mTLS and call the system "zero-trust." Don't stop there — that's the gap this whole week is about. A defensible zero-trust posture gives you:

- **Verifiable identity from attestation, with no secret zero** — every workload proves *what it is* and holds no long-lived credential to leak (the single biggest security win over mounted-secret models).
- **Authorization that's tested code**, not scattered in-app `if` checks — a deny-by-default, least-privilege policy you can `opa test` and gate in CI, so the over-broad rule (the Challenge) fails the build instead of shipping.
- **Two enforcement gates** — admission ("only safe pods run") *and* request-time ("they may only talk to what's allowed") — defense in depth.
- **A demonstrated deny**, so "zero trust" is a proof (a violation refused), not a claim — the difference between an audit pass and an audit finding.

The mesh gives you mTLS and a built-in CA; running SPIRE explicitly and authorizing with OPA is what gives you *control* over the identity and *testable, portable* policy — the senior-shop posture in 2026, and exactly what the capstone spec requires.

---

## Repo layout

```
cart-zerotrust/
├── README.md
├── identity/
│   ├── spire-server.yaml         # the trust domain CA (trust_domain = shop)
│   ├── spire-agent.yaml          # per-node attestation + Workload API (DaemonSet)
│   └── entries.sh                # registration entries: cart/inventory/payment SVIDs, both regions
├── authz/
│   ├── policy.rego               # deny-by-default, least-privilege, SPIFFE-keyed allow-matrix
│   ├── policy_test.rego          # opa test: allows AND denies; no-wildcard lint
│   └── ext-authz.yaml            # wiring OPA as the request-time gate (Envoy ext_authz / sidecar)
├── admission/
│   └── no-privileged.yaml        # Gatekeeper (Rego) or Kyverno (YAML): the "what may run" gate
├── proof/
│   ├── violation-probe.py        # allowed passes; cart->payment denied by OPA; forged denied at mTLS
│   └── rotation-demo.sh          # short-TTL SVID rotating with the service serving throughout
├── threat-model.md               # what a compromised cart can/can't reach, and why
└── runbook.md                    # certificate-expiry (SPIRE-server-down) failure mode + handling
```

---

## Deliverable 1 — `identity/` (SPIRE, both regions)

Deploy SPIRE (server + agent) and register every workload. `entries.sh` creates the registration entries mapping each service account to its SPIFFE ID (`spiffe://shop/ns/shop/sa/cart`, etc.), in both Week-19 regions. Document: the trust domain, the node attestor (`k8s_psat`), and — for the cross-region case — whether the two regions share a trust domain (simplest) or federate two trust domains (the stretch). Confirm each workload's SVID by decoding the URI SAN (Exercise 1). The rule: identity comes from *attestation*, so a pod under the wrong service account can't obtain another's identity — note this in the threat model.

---

## Deliverable 2 — `authz/` (the tested, least-privilege policy)

The OPA/Rego policy (Exercise 2), hardened:

- **`policy.rego`** — deny-by-default, the least-privilege allow-matrix keyed on SPIFFE identity. The intended graph and *nothing else*. No wildcard callers/targets/methods.
- **`policy_test.rego`** — `opa test` asserting every allowed path passes *and* every should-be-denied path (especially `cart`→`payment`) is denied, plus a **no-wildcard lint** that fails if any rule contains `*` (the Challenge's guard).
- **`ext-authz.yaml`** — wire OPA as the request-time gate so the policy actually governs live calls (Envoy `ext_authz` to an OPA sidecar, or the mesh's OPA integration).

> **The rule the project enforces:** the policy must *deny* a valid-but-unauthorized identity, and the deny must be *tested*. A policy that "has OPA" but allows everything (a wildcard, an over-broad rule) fails this project — least privilege, test-covered, is the point.

---

## Deliverable 3 — `admission/` (the "what may run" gate)

At least one admission policy demonstrating the second gate: a Gatekeeper (Rego ConstraintTemplate + Constraint) *or* Kyverno (YAML) policy that denies a privileged pod (or requires ownership labels / trusted images). Show it *denying* a deliberately-bad resource (`kubectl apply` of a privileged pod → rejected by the webhook). Document why this is a zero-trust control (it shrinks the attack surface — refuses to *run* the things an attacker would want) and is *complementary* to request-time authz, not a substitute.

---

## Deliverable 4 — `proof/` (the demonstrated deny + rotation)

The heart of the project — zero trust you *prove*:

- **`violation-probe.py`** (Exercise 3, wired to the real stack where possible): `order`→`payment` ALLOWED; `cart`→`payment` DENIED by OPA (valid SVID, no rule); forged/foreign identity DENIED at mTLS. The deliberate violation, refused.
- **`rotation-demo.sh`**: set a short SVID TTL, drive traffic, and show the SVID rotating automatically *with the service serving throughout* — rotation-without-downtime, and the basis for the certificate-expiry runbook.

> **The rule the proof enforces:** a deliberate violation must be *denied and observed*. Zero trust you didn't test with a violation is zero trust you're assuming. The probe producing the deny on purpose is the deliverable.

---

## Deliverable 5 — `threat-model.md` + `runbook.md`

The senior artifacts:

- **`threat-model.md`** — "if `cart` is compromised, what can it reach?" Enumerate: what `cart`'s identity authorizes (inventory.Reserve/Release, cart.Sync) and — crucially — what it *cannot* (payment, anything else), and *why* (no allow-rule, and it can't forge another identity because identity is attested). Name the residual risks (the SPIRE server as a high-value target; an over-broad rule as the failure mode). This is the document that answers an auditor's "what's your blast radius?".
- **`runbook.md`** — the **certificate-expiry** failure mode: with SPIRE, certs rotate automatically, *but* if the SPIRE server is down longer than the SVID TTL, SVIDs expire and workloads fail to authenticate. The runbook: how you'd detect it, the SPIRE-server HA you run to prevent it, and the recovery. This is a named Week-22 gameday scenario.

---

## Rules

- **You may** read the SPIFFE/SPIRE, OPA, Gatekeeper, and Kyverno docs and the lecture notes.
- **You must not** declare the system "zero-trust" with an over-broad or untested policy. The policy must be least-privilege, `opa test`-covered, and have no wildcard rules (the Challenge is exactly this bug).
- **You must not** claim a deny without *demonstrating* it — the violation probe must produce the refusal on purpose.
- **You must not** distribute a long-lived secret to a workload as its identity — the whole point is no secret zero; identity comes from the Workload API.
- **You must not** treat admission and request-time authz as interchangeable — you need both, and the threat model must say why.
- SPIRE 1.9+, OPA / Gatekeeper / Kyverno, Kind, the two Week-19 regions. Everything runs locally.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-21-cart-zerotrust-<yourhandle>`.
- [ ] SPIRE issues a verifiable SVID to every `cart`/`inventory`/`payment` workload (URI SAN confirmed), in both regions, from attestation (no secret distributed).
- [ ] `authz/policy.rego` is deny-by-default, least-privilege, SPIFFE-keyed, with `opa test` covering allows *and* denies and a no-wildcard lint — all passing.
- [ ] An admission policy (Gatekeeper or Kyverno) denies a privileged pod (demonstrated).
- [ ] `proof/violation-probe.py` shows `order`→`payment` allowed, `cart`→`payment` denied by OPA, forged identity denied at mTLS — the deliberate violation refused.
- [ ] `proof/rotation-demo.sh` shows an SVID rotating with the service serving throughout.
- [ ] `threat-model.md` enumerates a compromised `cart`'s blast radius (and what it can't reach, and why); `runbook.md` covers the certificate-expiry / SPIRE-server failure mode.
- [ ] A `README.md` with the zero-trust loop diagram, the policy's allow-matrix, the deny proof output, and a paragraph on Gatekeeper-vs-Kyverno for your admission choice.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **SPIRE identity (no secret zero)** | 20 | Every workload SVID'd from attestation; URI SAN confirmed; both regions; no distributed secret. |
| **Least-privilege OPA policy** | 25 | Deny-by-default; SPIFFE-keyed; no wildcards; `opa test` covers allows AND denies; CI-gateable. |
| **The demonstrated deny** | 20 | A valid-but-unauthorized identity (cart→payment) is *shown* denied; forged denied at mTLS. |
| **Admission gate + rotation** | 15 | A working "what may run" policy denying a bad resource; SVID rotation without downtime shown. |
| **Threat model & runbook** | 15 | Blast-radius enumerated with reasons; certificate-expiry/SPIRE-server failure mode handled. |
| **Docs & hygiene** | 5 | Clear README, loop diagram, sensible commits, no secrets/artifacts checked in. |

**90+** is portfolio-grade and *is* the capstone's security layer. **70–89** works but likely has an untested or over-broad policy, or claims a deny it doesn't demonstrate. **Below 70** usually means the policy allows lateral movement (a wildcard) or a secret was distributed as identity — fix those first; they're the two things this week exists to prevent.

---

## Stretch goals

- **Federate two trust domains.** Run SPIRE with a *different* trust domain per region, federate (exchange trust bundles), and authorize a cross-region call by the *remote* domain's SPIFFE identity — the genuine multi-region zero-trust story.
- **Both admission engines.** Write the same "no privileged pod" policy in Gatekeeper (Rego) *and* Kyverno (YAML), run both, and put a one-paragraph evidence-based comparison in the README — the choice made with data.
- **The full test matrix.** Enumerate *every* caller/target/method combination and assert each is allowed-or-denied as intended — proving the policy has no lateral hole, not just that one path is blocked (the Challenge stretch).
- **Break it in the gameday rehearsal.** Take the SPIRE server down for longer than the SVID TTL and watch authentication start failing as SVIDs expire — the certificate-expiry failure mode, observed — then recover and document it. The Week-22 drill, rehearsed.

---

## Common pitfalls (read before you start)

The mistakes that cost the most points and the most debugging:

- **An over-broad policy.** The single biggest trap: a wildcard rule (`caller: "*"` or `target: "*"`) that defeats deny-by-default and authorizes lateral movement. Every rule must be explicit and least-privilege, and a test must assert the deny (the Challenge).
- **An untested policy.** Shipping a policy with no `opa test` suite. The over-broad rule slips through precisely when there's no test asserting "cart cannot call payment." Test the allows *and* the denies.
- **Claiming a deny without demonstrating it.** Writing "the policy denies cart→payment" without producing the refusal on purpose. A security control's failure mode is silent allow — you must *show* the deny.
- **Distributing a secret as identity.** Mounting a long-lived cert/key into a pod instead of using the Workload API. The whole point is no secret zero; a mounted secret is exactly what SPIFFE/SPIRE replaces.
- **Un-wired ext_authz.** The policy exists and `opa test` passes, but it's not actually in the request path — so forbidden calls *succeed in production*. "We have a policy" is not "the policy is enforced."
- **Selector mismatch.** A registration entry whose selectors don't match the workload's service account, so it gets no SVID (or the wrong one). Confirm the *issued* SVID, not the entry.
- **Conflating the two gates.** Treating admission ("what may run") and request-time authz ("what may talk") as interchangeable. You need both; the threat model must say why.

A submission that avoids all seven is portfolio-grade; the lost points cluster on the first (over-broad/untested policy) and the third (an undemonstrated deny).

## How this connects to the rest of C22

- **Week 8 (Istio mTLS)** introduced SPIFFE identities implicitly; here you issue them explicitly with SPIRE and author the policy in OPA, with full control.
- **Week 19 (multi-region)** is the two-region substrate; here every cross-region hop is identified and authorized.
- **Week 20 (CRDT cart)** is the active-active cart whose every sync hop this secures.
- **Week 22 (gameday) + capstone** stress-test this as part of the whole system, with certificate-expiry as a named failure mode — and this *is* the capstone's "SPIFFE via SPIRE, OPA admission policy" deliverable.

## A suggested order of work

If you're not sure where to start:

1. **Day 1 (Thursday):** deploy SPIRE (server + agent), register `cart`/`inventory`/`payment`, and *confirm each SVID* by decoding the URI SAN (`identity/`). Don't move on until every workload has the right identity — a selector mismatch here blocks everything downstream.
2. **Day 1–2:** write the OPA/Rego policy and its `opa test` suite (`authz/`), including the `cart-cannot-call-payment` assertion and the no-wildcard lint. Get `opa test` green *first* — the policy is the heart of the project.
3. **Day 2 (Friday):** wire ext_authz so the policy gates live calls, then run the deliberate-violation probe (`proof/`) and capture the deny (cart→payment denied, forged denied at mTLS). This is the proof the loop enforces.
4. **Day 2–3:** the admission policy (`admission/`) and the rotation demo, then `threat-model.md` and `runbook.md`.
5. **Day 3 (Saturday):** the federation / both-engines stretch, and the README writeup.

The dependency that trips people: confirm the *issued SVIDs* (step 1) before anything else — if a workload has the wrong (or no) identity, your mTLS and your authz will fail in confusing ways, and you'll waste an afternoon debugging policy when the real bug was a registration-entry selector.

## What "done" looks like

A finished `cart-zerotrust` lets you run three commands and get three convincing results:

1. `kubectl exec deploy/cart -- spire-agent api fetch x509 ...` → an SVID whose URI SAN reads `spiffe://shop/ns/shop/sa/cart`. **Identity is real.**
2. `opa test authz/` → all assertions pass, including `cart-cannot-call-payment` and the no-wildcard lint. **Authorization is least-privilege and tested.**
3. `python3 proof/violation-probe.py` → `order→payment` ALLOWED, `cart→payment` DENIED by OPA, forged DENIED at mTLS. **The loop enforces, demonstrated.**

If those three commands produce those three results, you've closed the zero-trust loop and can defend it: every workload is cryptographically identified, every access is authorized by tested policy, and a deliberate violation is refused. That's the artifact — and it's the capstone's security layer.

When you've finished, push the repo and take the [quiz](../quiz.md).
