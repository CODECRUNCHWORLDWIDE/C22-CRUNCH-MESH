# Exercise 2 — The SPIFFE-Keyed OPA Authorization Policy (runnable Rego)
#
# Goal: A COMPLETE, testable Rego policy that authorizes service-to-service calls
#       by the CALLER'S SPIFFE IDENTITY, deny-by-default, with an explicit
#       allow-matrix and a full `opa test` suite proving the allows AND the
#       denies. This is the request-time "what may talk" gate from Lecture 2,
#       keyed on the verifiable identity SPIRE issued in Exercise 1.
#
#       The crucial property: a workload with a VALID SVID is still DENIED if no
#       rule grants it. `cart` has a real identity and STILL can't call `payment`,
#       because identity is necessary but NOT sufficient.
#
# Estimated time: 60 minutes. Runnable.
#
# PREREQUISITES
#   - `opa` installed (opa version). Rego v1 syntax.
#   - Exercise 1 done (so the SPIFFE IDs are real), though this policy runs
#     standalone with `opa eval` / `opa test`.
#
# HOW TO RUN
#   # Run the policy's unit tests (the allow/deny matrix, asserted):
#   opa test exercise-02-opa-spiffe-authz.rego -v
#
#   # Evaluate a single decision — cart calling payment should be DENIED:
#   echo '{"caller_spiffe_id":"spiffe://shop/ns/shop/sa/cart","target_service":"payment","method":"Charge"}' \
#     | opa eval -d exercise-02-opa-spiffe-authz.rego -I 'data.authz.allow'
#   # -> false  (no rule grants cart -> payment)
#
#   # order calling payment should be ALLOWED:
#   echo '{"caller_spiffe_id":"spiffe://shop/ns/shop/sa/order","target_service":"payment","method":"Charge"}' \
#     | opa eval -d exercise-02-opa-spiffe-authz.rego -I 'data.authz.allow'
#   # -> true

package authz

import rego.v1

# ---------------------------------------------------------------------------
# DENY BY DEFAULT. allow is false unless a rule below makes it true. A new
# service, a forgotten path, or a compromised workload with an UNLISTED identity
# is denied by omission — the zero-trust posture.
# ---------------------------------------------------------------------------
default allow := false

# ---------------------------------------------------------------------------
# The allow-matrix: the EXPLICIT, least-privilege set of permitted call paths,
# keyed on the caller's verified SPIFFE identity. This is `data` in the
# input/data/decision model — the policy's reference data.
#
# Note what is ABSENT: there is NO rule for cart -> payment. So cart calling
# payment is DENIED, even though cart is a real, identified, in-mesh workload.
# That omission IS the security control against lateral movement.
# ---------------------------------------------------------------------------
access_rules := [
	{
		"caller": "spiffe://shop/ns/shop/sa/order",
		"target": "payment",
		"methods": ["Charge", "Refund", "Reverse"],
	},
	{
		"caller": "spiffe://shop/ns/shop/sa/order",
		"target": "inventory",
		"methods": ["Commit"],
	},
	{
		"caller": "spiffe://shop/ns/shop/sa/cart",
		"target": "inventory",
		"methods": ["Reserve", "Release"],
	},
	# cross-region: cart in either region may sync to cart (same trust domain only).
	# In a FEDERATED multi-trust-domain setup you'd also pin the remote trust
	# domain here; same-domain is the single-trust-domain case.
	{
		"caller": "spiffe://shop/ns/shop/sa/cart",
		"target": "cart",
		"methods": ["Sync"],
	},
]

# ---------------------------------------------------------------------------
# The decision: allow iff some rule permits this caller -> target.method.
# input.caller_spiffe_id is the VERIFIED identity from the caller's SVID (the
# ext_authz / sidecar extracts it from the validated mTLS peer cert) — not an IP,
# not a header, not a claim. That is why this is enforceable.
# ---------------------------------------------------------------------------
allow if {
	some rule in access_rules
	rule.caller == input.caller_spiffe_id
	rule.target == input.target_service
	input.method in rule.methods
}

# A helpful explicit-reason rule for debugging / audit logs (not the gate itself):
# why the request was denied, so the audit trail says more than "false".
deny_reason := "no allow rule for caller/target/method" if {
	not allow
	is_string(input.caller_spiffe_id)
}

deny_reason := "caller presented no verified SPIFFE identity" if {
	not is_string(input.caller_spiffe_id)
}

# Guard against a classic over-broad footgun: a rule must never use a wildcard
# caller. This is a self-check the test suite asserts — the Challenge is exactly
# the bug this prevents (an over-broad rule that authorizes everyone).
has_wildcard_caller if {
	some rule in access_rules
	rule.caller == "*"
}

# ===========================================================================
# TESTS — run with: opa test exercise-02-opa-spiffe-authz.rego -v
# An UNTESTED authz policy is how the over-broad rule (the Challenge) ships.
# ===========================================================================

# order -> payment.Charge is ALLOWED
test_order_can_charge_payment if {
	allow with input as {
		"caller_spiffe_id": "spiffe://shop/ns/shop/sa/order",
		"target_service": "payment",
		"method": "Charge",
	}
}

# cart -> payment is DENIED (no rule grants it) — the key zero-trust assertion
test_cart_cannot_call_payment if {
	not allow with input as {
		"caller_spiffe_id": "spiffe://shop/ns/shop/sa/cart",
		"target_service": "payment",
		"method": "Charge",
	}
}

# cart -> inventory.Reserve is ALLOWED
test_cart_can_reserve_inventory if {
	allow with input as {
		"caller_spiffe_id": "spiffe://shop/ns/shop/sa/cart",
		"target_service": "inventory",
		"method": "Reserve",
	}
}

# order -> payment with an UNLISTED method is DENIED (method-level least privilege)
test_order_cannot_call_unlisted_method if {
	not allow with input as {
		"caller_spiffe_id": "spiffe://shop/ns/shop/sa/order",
		"target_service": "payment",
		"method": "DrainAccount",
	}
}

# an UNKNOWN identity is DENIED (deny-by-default catches the unlisted caller)
test_unknown_identity_denied if {
	not allow with input as {
		"caller_spiffe_id": "spiffe://evil/ns/x/sa/attacker",
		"target_service": "payment",
		"method": "Charge",
	}
}

# a MISSING identity (no verified SVID) is DENIED
test_missing_identity_denied if {
	not allow with input as {
		"target_service": "payment",
		"method": "Charge",
	}
}

# the policy itself must NOT contain a wildcard caller (the over-broad footgun)
test_no_wildcard_caller if {
	not has_wildcard_caller
}

# ---------------------------------------------------------------------------
# Expected output
# ---------------------------------------------------------------------------
#
#   $ opa test exercise-02-opa-spiffe-authz.rego -v
#   data.authz.test_order_can_charge_payment: PASS
#   data.authz.test_cart_cannot_call_payment: PASS
#   data.authz.test_cart_can_reserve_inventory: PASS
#   data.authz.test_order_cannot_call_unlisted_method: PASS
#   data.authz.test_unknown_identity_denied: PASS
#   data.authz.test_missing_identity_denied: PASS
#   data.authz.test_no_wildcard_caller: PASS
#   --------------------------------------------------------------------------
#   PASS: 7/7
#
# ACCEPTANCE CRITERIA
#   [ ] `opa test` reports 7/7 PASS.
#   [ ] cart -> payment evaluates to FALSE (denied) while order -> payment is TRUE
#       (allowed) — a valid identity is necessary but not sufficient.
#   [ ] An unknown/missing identity is denied (deny-by-default).
#   [ ] A listed caller calling an UNLISTED method is denied (method-level least privilege).
#   [ ] The policy contains NO wildcard caller, and the test asserts it (the
#       over-broad-rule footgun from the Challenge is guarded against).
#   [ ] You can explain how input.caller_spiffe_id gets populated: the ext_authz /
#       sidecar extracts the SPIFFE ID from the VALIDATED mTLS peer certificate —
#       so it's the verified identity, not a spoofable claim.
# ---------------------------------------------------------------------------
