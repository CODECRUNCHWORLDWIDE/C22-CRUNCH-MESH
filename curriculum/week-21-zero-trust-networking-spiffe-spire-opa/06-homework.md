# Week 21 Homework

Six problems that revisit the week's topics and force the zero-trust operational literacy into your fingers. The full set should take about **5 hours**. Work in your Week 21 Git repository (the same workspace as the exercises and the `cart-zerotrust` mini-project) so every problem produces at least one commit you can point to at the Phase 4 review and the capstone audit.

The headline deliverable is **Problem 4 — the zero-trust threat-model memo**, the artifact a security reviewer reads to understand your blast radius. Treat it as a security design document, not a journal entry.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **SPIRE** deployed and your **`cart`/`inventory`/`payment`** workloads SVID'd (Exercise 1), and **`opa`** installed. Problems 1, 2, 3, 5, and 6 are runnable; problem 4 is the memo.

---

## Problem 1 — The identity inventory

**Problem statement.** For every workload in your meshed `shop` namespace(s), capture its *actual* SPIFFE identity from the issued SVID (not from your registration YAML). Build a table in `notes/week-21/identity-inventory.md` with one row per workload: workload, service account, the SPIFFE ID from the SVID's URI SAN, SVID validity window (notAfter), and whether it matches the intended identity.

**Acceptance criteria.**

- `notes/week-21/identity-inventory.md` has one row per workload (at least cart, inventory, payment) with the SPIFFE ID read from the *decoded SVID*, not the YAML.
- Each row shows the short validity window (proving short-lived SVIDs).
- At least one row is checked against the intended identity (and any mismatch flagged with a reason).
- Committed.

**Hint.** `kubectl exec <pod> -- openssl x509 -in <svid.pem> -noout -text | grep -A1 "Subject Alternative Name"` gives the URI SAN. The validity window comes from `openssl x509 -noout -dates`. A workload with no SVID, or the wrong SPIFFE ID, is your flagged row — likely a registration-entry selector that doesn't match its service account.

**Estimated time.** 40 minutes.

---

## Problem 2 — Prove the policy denies (the deliberate violation)

**Problem statement.** Using your Exercise-2 OPA policy, demonstrate the zero-trust loop denying a violation. Show that `order`→`payment` is allowed, `cart`→`payment` is denied by OPA (valid identity, no rule), and an unknown/forged identity is denied. Quote the OPA evaluation for each.

**Acceptance criteria.**

- `notes/week-21/deny-proof.md` shows the three evaluations: order→payment (allow=true), cart→payment (allow=false), unknown identity (allow=false).
- You state, in one sentence, why `cart` being denied `payment` *despite a valid SVID* is the whole point (identity necessary, not sufficient).
- If you wired the real ext_authz, quote the live denial; otherwise quote `opa eval`.
- Committed.

**Hint.** `echo '{"caller_spiffe_id":"spiffe://shop/ns/shop/sa/cart","target_service":"payment","method":"Charge"}' | opa eval -d policy.rego -I 'data.authz.allow'` → false. Swap the caller to `order` → true. The deny is the deliverable, not the allow.

**Estimated time.** 40 minutes.

---

## Problem 3 — Hunt the over-broad rule

**Problem statement.** Take the Challenge's over-broad policy (or plant a wildcard rule in your own), and prove it authorizes lateral movement. Write the `opa test` assertions that *catch* it: a `cart-cannot-call-payment` test and a no-wildcard lint. Show the tests failing on the broken policy and passing once you fix it to least privilege.

**Acceptance criteria.**

- `notes/week-21/overbroad.md` shows the broken policy allowing `cart`→`payment` (the hole), the test that catches it failing, the least-privilege fix, and the test passing.
- The fix preserves the legitimate paths (`order`→`payment`, `cart`→`inventory`).
- You include a no-wildcard lint assertion and show it would block the bad rule in CI.
- Committed.

**Hint.** The no-wildcard lint: a rule that fails if any `access_rules` entry has `caller == "*"` (or target/method). The whack-a-mole non-fix (an explicit deny bolted onto a wildcard) doesn't pass — only *removing* the over-broad grant does. That's the Challenge's lesson.

**Estimated time.** 45 minutes.

---

## Problem 4 — The zero-trust threat-model memo (headline deliverable)

**Problem statement.** This is the syllabus skill ("closing the zero-trust loop"). Write a one-to-two-page memo at `notes/week-21/threat-model-memo.md` that a security reviewer reads to understand your blast radius. Take the multi-region cart system and answer, concretely, what an attacker gains from a foothold and why. Your memo must hit these headings:

1. **The assets** — what's worth protecting (payment/charges, customer data, inventory integrity).
2. **The foothold scenario** — assume an attacker fully compromises *one* workload (pick `cart`). What identity do they now have, and what does that identity authorize?
3. **What they can reach** — the call paths `cart`'s SPIFFE identity is authorized for (inventory.Reserve/Release, cart.Sync), and why that's the *intended* blast radius.
4. **What they cannot reach, and why** — `payment` (no allow-rule), and any other identity's authorizations — and *why they can't escalate*: they can't forge another identity (it's attested, not asserted) and they hold no secret zero to steal another credential.
5. **The residual risks** — the things that *would* break this: an over-broad policy rule (lateral movement returns), a compromised SPIRE server (the CA — a high-value target), a leaked node-attestation path. Name them honestly.
6. **The controls** — which control stops which threat: mTLS (forged identity → can't connect), OPA least-privilege (lateral movement → denied), admission (privileged/escapable pod → can't run), short-lived SVIDs (stolen cred → expires fast), no-secret-zero (no credential to steal).

**Acceptance criteria.**

- `notes/week-21/threat-model-memo.md` exists, fits roughly one-to-two pages (600–1000 words), and hits all six headings.
- The foothold analysis is *specific* — it names exactly what `cart`'s identity can and cannot do, tied to your actual allow-matrix.
- The "cannot escalate" reasoning correctly invokes attested-not-asserted identity and no-secret-zero.
- The residual-risks section is honest — it names the SPIRE server and the over-broad-rule risk rather than claiming perfect security.
- Committed.

**Hint.** The strongest threat models are *specific and honest*. "A compromised cart can reach inventory (Reserve/Release) and other cart replicas (Sync), and *nothing else* — not payment, because no rule grants it, and it can't become order because identity is attested. The residual risks are the SPIRE server (compromise it and you can mint any identity) and any over-broad policy rule." That specificity — naming the exact blast radius and the exact residual risks — is what a reviewer trusts. A memo that says "we use zero trust so we're secure" fails; the value is in the precise blast-radius accounting.

**Estimated time.** 1 hour.

---

## Problem 5 — Watch a rotation (and reason about the failure mode)

**Problem statement.** Configure a short SVID TTL, observe an SVID rotate automatically with the workload serving throughout, and then reason about the failure mode: what happens if the SPIRE server is down longer than the SVID TTL?

**Acceptance criteria.**

- `notes/week-21/rotation.md` shows an SVID rotating (a new notBefore/notAfter) before the old one expired, with the service still serving.
- You describe (or demonstrate) what happens if the SPIRE server is unavailable longer than the SVID TTL: SVIDs expire, workloads fail to authenticate.
- You state the runbook line for this failure mode and the prevention (SPIRE server HA).
- Committed.

**Hint.** Set the SVID TTL to a couple of minutes, `spire-agent api watch` to see the stream, and observe SVID#2 arrive before SVID#1 expires. For the failure mode, scale the SPIRE server to 0 and wait past the TTL — fresh SVIDs stop coming and auth starts failing. That's the certificate-expiry failure mode, and it's a Week-22 gameday scenario.

**Estimated time.** 40 minutes.

---

## Problem 6 — Diagnose a planted zero-trust fault

**Problem statement.** Have a partner (or your future self) introduce ONE of these faults, then diagnose it from the outside: (a) a registration-entry selector that doesn't match a workload's service account (so it gets no SVID / the wrong one), (b) an over-broad OPA rule that authorizes lateral movement, or (c) the OPA ext_authz not actually wired (so the policy exists but doesn't gate live calls). For whichever fault, produce a diagnosis: symptom, evidence, root cause, fix.

**Acceptance criteria.**

- `notes/week-21/planted-fault.md` records which fault, the diagnostic steps, the evidence (the missing SVID / the allowed-but-shouldn't-be call / the un-gated request), the root cause, and the fix.
- You reach the diagnosis with at least two signals (e.g., the workload has no SVID from the Workload API *and* the registration entry's selectors don't match its pod).
- Committed.

**Hint.** The scariest is (c), the un-wired ext_authz: the policy is there and `opa test` passes, but live calls aren't actually being checked — so a forbidden call *succeeds in production* even though the policy would deny it. The two-signal tell: `opa eval` says deny, but the live call to payment *succeeds* — the gate isn't in the path. "We have a policy" is not "the policy is enforced."

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Identity inventory | 40 min |
| 2 — Prove the policy denies | 40 min |
| 3 — Hunt the over-broad rule | 45 min |
| 4 — Threat-model memo (headline) | 1 h 0 min |
| 5 — Watch a rotation | 40 min |
| 6 — Diagnose a planted fault | 35 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `cart-zerotrust` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — it *is* the capstone's security layer, and Week 22's gameday includes certificate-expiry as a named failure mode. Then take the [quiz](./05-quiz.md) with your notes closed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Identity inventory (P1)** | 15 | SPIFFE IDs read from decoded SVIDs; short validity windows; mismatches flagged. |
| **Deny proof (P2)** | 15 | order allowed, cart→payment denied, unknown denied; the "necessary not sufficient" point made. |
| **Over-broad hunt (P3)** | 15 | Hole demonstrated; catching test written; least-privilege fix preserves legit paths; no-wildcard lint. |
| **Threat-model memo (P4)** | 25 | Specific blast-radius accounting; "cannot escalate" reasoning correct; residual risks honest. |
| **Rotation + failure mode (P5)** | 20 | Rotation observed; SPIRE-server-down failure mode reasoned; HA prevention stated. |
| **Planted fault (P6)** | 10 | Two-signal diagnosis; correct root cause and fix. |

**90+** is portfolio-grade. **70–89** is solid but the memo likely hand-waves the blast radius or the residual risks. **Below 70** usually means Problem 2 or 4 was treated as a formality — they're the two that prove you understand zero trust is an *enforced, bounded* posture (the demonstrated deny, the precise blast radius), which is the whole difference between turning on mTLS and operating a zero-trust system.
