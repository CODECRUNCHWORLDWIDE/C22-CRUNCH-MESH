# Challenge 1 — The Over-Broad Policy

**Time estimate:** ~90 minutes.

## Problem statement

You are the security engineer reviewing the cart platform's zero-trust posture before a compliance audit. The team is confident: SPIRE issues SVIDs to every workload, mTLS is strict, and there's an OPA policy with `default allow := false` right at the top. The checkbox says "zero-trust authorization: yes." But during a tabletop exercise, you ask the obvious question — "if the `cart` pod is compromised, what can it reach?" — and the answer comes back wrong: **a compromised `cart` can call `payment` and charge cards.** It should not be able to. `cart` has no business touching `payment`; only `order` orchestrates charges. Yet the policy allows it.

Here's the twist that makes it a real incident-in-waiting: **the policy *looks* correct.** It has the deny-by-default line. It has SPIFFE identities. It passed review because three engineers read `default allow := false`, nodded, and didn't read the rules below it carefully. The hole is one over-broad allow rule — a wildcard, or a match that's looser than anyone intended — that silently grants far more than the author meant. The policy isn't *missing*; it's *too permissive*, which is harder to spot and exactly as dangerous.

Your job: prove that a workload which *should* be denied (`cart` → `payment`) is actually *allowed*, find and name the over-broad rule that opened the hole, and fix it to genuine least privilege — **without** breaking the legitimate call paths (`order` → `payment`, `cart` → `inventory`), and with a *test* that would have caught the hole before it shipped. "Just delete OPA and use the mesh" is not an answer; "add `default allow := false`" is not an answer (it's already there — that's the trap).

This mirrors the most common real zero-trust failure. The absence of authorization is obvious and gets caught. An *over-broad* authorization is invisible in a casual read, has all the trappings of security, and is precisely how a single compromised pod becomes a full breach via lateral movement.

## The harness

Reproduce it. Here is the policy "as reviewed" — it has the deny-by-default and the SPIFFE identities, and it has the bug:

```rego
# overbroad.rego — looks zero-trust, allows lateral movement to payment.
package authz
import rego.v1

default allow := false        # <- everyone reads this and stops. The bug is BELOW.

access_rules := [
    {"caller": "spiffe://shop/ns/shop/sa/order", "target": "payment",   "methods": ["Charge", "Refund"]},
    {"caller": "spiffe://shop/ns/shop/sa/order", "target": "inventory", "methods": ["Commit"]},
    {"caller": "spiffe://shop/ns/shop/sa/cart",  "target": "inventory", "methods": ["Reserve", "Release"]},
    # The over-broad rule. Intended (a comment claims) to "let internal services
    # talk to each other for health checks", but it authorizes ANY shop caller to
    # ANY target for ANY method. THIS is the lateral-movement hole.
    {"caller": "spiffe://shop/*",                "target": "*",         "methods": ["*"]},
]

allow if {
    some rule in access_rules
    glob.match(rule.caller, ["/"], input.caller_spiffe_id)   # wildcard caller match
    glob.match(rule.target, [], input.target_service)         # wildcard target match
    rule.methods[_] == "*"                                    # wildcard method
}

allow if {
    some rule in access_rules
    rule.caller == input.caller_spiffe_id
    rule.target == input.target_service
    input.method in rule.methods
}
```

```bash
# The hole, demonstrated: cart can call payment.Charge.
echo '{"caller_spiffe_id":"spiffe://shop/ns/shop/sa/cart","target_service":"payment","method":"Charge"}' \
  | opa eval -d overbroad.rego -I 'data.authz.allow'
# -> true     <-- WRONG. cart should NEVER be able to charge payment.
```

You now have the bug: a policy that reads as zero-trust but authorizes `cart` → `payment` (and, in fact, *everything* → *everything* within `shop`) via the over-broad wildcard rule. Diagnose it from the policy before reading the fix.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Symptom** — exactly what you observe: a call that *should* be denied (`cart` → `payment.Charge`) evaluates to `allow == true`. Show it with `opa eval`. Then show the *scope* of the hole: enumerate a few caller/target pairs that should be denied and demonstrate they're all allowed (it's not just cart→payment — it's everything-to-everything in `shop`).
2. **Proof the hole is the over-broad rule, not deny-by-default** — show that `default allow := false` is present and correct, and that the *grant* is coming from the wildcard rule (e.g., temporarily remove the `spiffe://shop/*` rule and watch `cart → payment` flip to denied). This isolates the bug to the over-broad rule, not the default.
3. **The mechanism** — name it precisely: the rule `{"caller": "spiffe://shop/*", "target": "*", "methods": ["*"]}` (a wildcard on caller, target, AND method) authorizes *any* `shop` identity to call *any* target with *any* method. Deny-by-default is irrelevant when a single rule grants everything — the default only matters for what *no* rule covers, and this rule covers all of `shop`. The "for health checks" justification is the classic over-broad-for-convenience footgun.
4. **The fix** — replace the wildcard rule with **explicit least-privilege rules** for whatever the wildcard was *actually* needed for (if health checks really need cross-service calls, grant *only* the health-check method between the *specific* identities that need it — e.g., a dedicated `Health/Check` method, not `*`). Show `cart → payment` now evaluates to `false` while the legitimate paths (`order → payment`, `cart → inventory`) still evaluate to `true`.
5. **The test that catches it** — write the `opa test` assertion that *would have caught this in CI*: `test_cart_cannot_call_payment` asserting `not allow` for `cart → payment`, plus a `test_no_wildcard_caller` (or `_target`/`_method`) assertion that fails if any rule contains a `*`. Show the test failing on the broken policy and passing on the fix.

You must reach the diagnosis with **at least two** independent signals — e.g., the `opa eval` showing `cart → payment` allowed *and* the scope-enumeration showing many should-be-denied pairs allowed (proving it's a broad grant, not a one-off). One signal is a guess; two is a diagnosis.

## The fix, applied

Least privilege, explicitly:

```rego
# fixed.rego — no wildcards; every grant is a specific caller/target/method.
access_rules := [
    {"caller": "spiffe://shop/ns/shop/sa/order", "target": "payment",   "methods": ["Charge", "Refund"]},
    {"caller": "spiffe://shop/ns/shop/sa/order", "target": "inventory", "methods": ["Commit"]},
    {"caller": "spiffe://shop/ns/shop/sa/cart",  "target": "inventory", "methods": ["Reserve", "Release"]},
    # If health checks genuinely need cross-service calls, grant ONLY that — and
    # only between the specific identities that need it. NOT a blanket wildcard.
    {"caller": "spiffe://shop/ns/shop/sa/healthcheck", "target": "payment", "methods": ["Health"]},
    {"caller": "spiffe://shop/ns/shop/sa/healthcheck", "target": "inventory", "methods": ["Health"]},
]

# Only the EXACT-MATCH allow rule remains. No wildcard rule.
allow if {
    some rule in access_rules
    rule.caller == input.caller_spiffe_id
    rule.target == input.target_service
    input.method in rule.methods
}
```

```bash
# cart -> payment now DENIED:
echo '{"caller_spiffe_id":"spiffe://shop/ns/shop/sa/cart","target_service":"payment","method":"Charge"}' \
  | opa eval -d fixed.rego -I 'data.authz.allow'
# -> false   ✔

# order -> payment STILL allowed (legitimate path unbroken):
echo '{"caller_spiffe_id":"spiffe://shop/ns/shop/sa/order","target_service":"payment","method":"Charge"}' \
  | opa eval -d fixed.rego -I 'data.authz.allow'
# -> true    ✔
```

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You demonstrate `cart → payment.Charge` evaluating to `true` on the broken policy (the hole) and the *scope* of the over-broad grant.
- [ ] You isolate the grant to the wildcard rule (removing it flips `cart → payment` to denied), proving it's the over-broad rule and not the default.
- [ ] Your fix removes the wildcard and uses explicit least-privilege rules; `cart → payment` is denied while `order → payment` and `cart → inventory` still work.
- [ ] You write the `opa test` (the `cart-cannot-call-payment` assertion and a no-wildcard assertion) that fails on the broken policy and passes on the fix.
- [ ] A `fixed.rego` checked in.
- [ ] Committed to your Week 21 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong "fixes" you must NOT write:

- **"Add `default allow := false`."** It's *already there* — and it's correct. The trap of this whole challenge is that deny-by-default gives a *false* sense of safety: it only governs what *no* rule matches, and the over-broad rule matches *everything*, so the default never fires. Re-adding a line that's already present and correct is a non-fix that proves you didn't read past line one — exactly the mistake the three reviewers made.
- **"Keep the wildcard but add an explicit deny for cart → payment."** This plays whack-a-mole: you've closed *one* hole (cart→payment) while leaving the wildcard authorizing *every other* lateral path (cart→inventory.DangerousMethod, frontend→payment, etc.). A deny-list bolted onto an allow-everything rule is not least privilege; it's an allow-everything rule with one exception, and you'll be adding exceptions forever while the breaches keep finding the ones you forgot. The fix is to *remove* the over-broad grant, not to patch around it.

A related real-world cousin worth naming in your writeup: the **over-broad admission policy** — a Gatekeeper/Kyverno constraint scoped so loosely (or with such a broad `exemptImages`/namespace exclusion) that the privileged-pod block it's supposed to enforce is effectively off for half the cluster. Same disease (a policy that *looks* enforcing but is too permissive), same cure (tighten the scope to exactly what's intended, and test the deny).

## Stretch

- **Find every hole, not just cart→payment.** Write a test matrix that enumerates *all* the should-be-denied caller/target/method combinations and asserts each is denied — turning "I found *a* hole" into "I proved there are *no* holes." This is the difference between spotting a bug and proving a policy correct.
- **Add the no-wildcard lint to CI.** Make the `test_no_wildcard_caller`/`_target`/`_method` assertions a required CI gate, so a future over-broad rule fails the build. The Challenge's lesson, automated — exactly the guard the mini-project requires.
- **Reproduce the admission-control cousin:** write a Gatekeeper or Kyverno "no privileged pods" policy with an over-broad namespace exclusion, show a privileged pod slips through, and tighten the scope. Same bug class at the "what may run" gate.

## Why this matters

Every zero-trust deployment is one over-broad rule away from being security theater. The policy that has *no* authorization gets caught in the first review. The policy that has authorization but grants too much *passes* review — because it has the deny-by-default line, the SPIFFE identities, the OPA checkbox — and then a single compromised pod walks straight to the payment service the policy was supposed to protect. The difference between a zero-trust posture that contains a breach and one that amplifies it is whether *someone* read past `default allow := false`, asked "what can a compromised cart actually reach?", and tightened every rule to exactly what it needs. When you defend your `cart-zerotrust` mini-project at the Phase 4 review, "my policy is least-privilege, every rule is explicit, there are no wildcards, and here's the test matrix proving no lateral path exists" is the line that says you built zero trust — not a deny-by-default line with a back door underneath it.
