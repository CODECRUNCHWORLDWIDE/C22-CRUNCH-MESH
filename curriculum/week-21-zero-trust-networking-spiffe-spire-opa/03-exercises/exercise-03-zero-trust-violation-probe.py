#!/usr/bin/env python3
# Exercise 3 — The Zero-Trust Violation Probe (runnable)
#
# Goal: PROVE the zero-trust loop is ENFORCING, not decorating, by deliberately
#       committing violations and confirming they're DENIED. Three probes:
#         1. order -> payment      : ALLOWED (order is authorized)
#         2. cart  -> payment      : DENIED by OPA (valid SVID, but not authorized)
#         3. forged -> payment     : DENIED at mTLS (cannot prove identity at all)
#
#       The point is probe #2: cart is a REAL, identified, in-mesh workload with a
#       valid SVID — and it is STILL denied payment, because authorization is a
#       second gate that identity alone does not open. Identity is necessary but
#       NOT sufficient. That is what "zero-trust loop closed" means concretely.
#
# Estimated time: 60 minutes. Runnable.
#
# WHAT THIS DEMONSTRATES (and how it maps to the real stack)
#   - The mTLS layer (SPIRE-issued SVIDs) decides WHO you are. A forged identity
#     (no valid SVID / wrong trust domain) can't even establish the connection.
#   - The OPA layer (Exercise-2 policy) decides WHAT you may do. A valid identity
#     with no allow-rule is rejected before the call reaches payment's app code.
#
#   This script SIMULATES the decision pipeline locally so you can run it without
#   a full ext_authz wiring: it models (a) the mTLS identity check and (b) the OPA
#   policy evaluation (calling a local `opa` or the embedded matrix). In the
#   mini-project you wire the REAL ext_authz so the same verdicts come from the
#   live mesh + OPA, not this simulator.
#
# PREREQUISITES
#   - Python 3.10+ (standard library only).
#   - Optional: `opa` installed, to evaluate against the real Exercise-2 policy
#     (pass --opa-policy exercise-02-opa-spiffe-authz.rego). Without it, the
#     script uses an embedded copy of the same allow-matrix.
#
#   Run: python3 exercise-03-zero-trust-violation-probe.py

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

# The same allow-matrix as the Exercise-2 Rego policy (embedded fallback so this
# runs without opa installed). The REAL gate uses the Rego; this mirrors it.
ACCESS_RULES = [
    {"caller": "spiffe://shop/ns/shop/sa/order", "target": "payment", "methods": {"Charge", "Refund", "Reverse"}},
    {"caller": "spiffe://shop/ns/shop/sa/order", "target": "inventory", "methods": {"Commit"}},
    {"caller": "spiffe://shop/ns/shop/sa/cart", "target": "inventory", "methods": {"Reserve", "Release"}},
    {"caller": "spiffe://shop/ns/shop/sa/cart", "target": "cart", "methods": {"Sync"}},
]

# Which identities have a VALID SVID in our trust domain. A "forged" caller has
# no entry here -> the mTLS layer rejects it (it can't present a real SVID signed
# by the trust domain's CA). This models the identity (authentication) gate.
VALID_SVIDS = {
    "spiffe://shop/ns/shop/sa/order",
    "spiffe://shop/ns/shop/sa/cart",
    "spiffe://shop/ns/shop/sa/inventory",
    "spiffe://shop/ns/shop/sa/payment",
}


def mtls_identity_check(caller_spiffe_id: str | None) -> tuple[bool, str]:
    """Gate 1 (authentication): does the caller present a VALID SVID in our trust
    domain? A forged/missing/wrong-trust-domain identity fails here — it can't
    even establish the mutually-authenticated connection.
    """
    if not caller_spiffe_id:
        return False, "no SVID presented (cannot establish mTLS)"
    if caller_spiffe_id not in VALID_SVIDS:
        return False, f"SVID not valid in trust domain (forged/foreign): {caller_spiffe_id}"
    return True, "valid SVID"


def opa_authz_check(caller: str, target: str, method: str, policy_file: str | None) -> bool:
    """Gate 2 (authorization): does OPA's policy permit this call? Uses the real
    Rego policy if `opa` + a policy file are available, else the embedded matrix.
    """
    if policy_file and shutil.which("opa"):
        inp = json.dumps({"caller_spiffe_id": caller, "target_service": target, "method": method})
        proc = subprocess.run(
            ["opa", "eval", "-d", policy_file, "-I", "-f", "raw", "data.authz.allow"],
            input=inp, capture_output=True, text=True,
        )
        return proc.stdout.strip() == "true"
    # Embedded fallback: mirror the Rego allow-matrix.
    return any(
        r["caller"] == caller and r["target"] == target and method in r["methods"]
        for r in ACCESS_RULES
    )


def probe(label: str, caller: str | None, target: str, method: str, policy_file: str | None) -> str:
    """Run one call through BOTH gates and return the verdict + reason."""
    ok_id, id_reason = mtls_identity_check(caller)
    if not ok_id:
        # Gate 1 failed: rejected at mTLS, never reaches OPA or the target app.
        return f"DENIED   (mTLS rejects: {id_reason})"
    # Gate 1 passed: identity is verified. Now Gate 2 (authorization).
    allowed = opa_authz_check(caller, target, method, policy_file)
    if allowed:
        return f"ALLOWED  ({label} is authorized to call {target}.{method})"
    return f"DENIED   (valid SVID, but OPA: no rule for {caller} -> {target}.{method})"


def main() -> int:
    p = argparse.ArgumentParser(description="Zero-trust violation probe.")
    p.add_argument("--opa-policy", default=None,
                   help="path to the Exercise-2 Rego policy (uses real opa if installed)")
    args = p.parse_args()

    print("=== Zero-trust loop: deliberate violations should be DENIED ===\n")

    cases = [
        # label,    caller SPIFFE id,                          target,    method
        ("order", "spiffe://shop/ns/shop/sa/order", "payment", "Charge"),   # allowed
        ("cart", "spiffe://shop/ns/shop/sa/cart", "payment", "Charge"),     # DENIED by OPA
        ("forged", None, "payment", "Charge"),                              # DENIED at mTLS
        ("foreign", "spiffe://evil/ns/x/sa/attacker", "payment", "Charge"), # DENIED at mTLS (wrong domain)
    ]

    all_expected = True
    for label, caller, target, method in cases:
        cid = caller if caller else "(no SVID)"
        verdict = probe(label, caller, target, method, args.opa_policy)
        print(f"[probe] {label:7s} -> {target}   (SPIFFE: {cid})")
        print(f"        VERDICT: {verdict}")
        # sanity: only `order` should be ALLOWED in this matrix
        is_allowed = verdict.startswith("ALLOWED")
        if (label == "order") != is_allowed:
            all_expected = False
        print()

    print("-" * 68)
    print("ZERO-TRUST LOOP CLOSED: identity is verified (SPIFFE) AND access is")
    print("authorized (OPA). A valid identity is necessary but NOT sufficient —")
    print("cart is in the mesh with a real SVID and is STILL denied payment.")
    print("-" * 68)

    if not all_expected:
        print("FAIL: a verdict did not match the expected allow/deny matrix.")
        return 1
    print("PASS: every violation was correctly denied; only the authorized call passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   === Zero-trust loop: deliberate violations should be DENIED ===
#
#   [probe] order   -> payment   (SPIFFE: spiffe://shop/ns/shop/sa/order)
#           VERDICT: ALLOWED  (order is authorized to call payment.Charge)
#
#   [probe] cart    -> payment   (SPIFFE: spiffe://shop/ns/shop/sa/cart)
#           VERDICT: DENIED   (valid SVID, but OPA: no rule for ...cart -> payment.Charge)
#
#   [probe] forged  -> payment   (SPIFFE: (no SVID))
#           VERDICT: DENIED   (mTLS rejects: no SVID presented (cannot establish mTLS))
#
#   [probe] foreign -> payment   (SPIFFE: spiffe://evil/ns/x/sa/attacker)
#           VERDICT: DENIED   (mTLS rejects: SVID not valid in trust domain (forged/foreign))
#
#   PASS: every violation was correctly denied; only the authorized call passed.
#
# ACCEPTANCE CRITERIA
#   [ ] order -> payment is ALLOWED; cart -> payment is DENIED by OPA (valid SVID,
#       no allow-rule) — identity necessary but not sufficient, demonstrated.
#   [ ] A forged/missing identity is DENIED at mTLS (can't even connect).
#   [ ] A foreign-trust-domain identity is DENIED at mTLS (the trust domain boundary).
#   [ ] You can name the TWO gates each verdict came from: mTLS (who you are) and
#       OPA (what you may do).
#   [ ] BONUS: wire the REAL ext_authz so these verdicts come from the live mesh +
#       OPA policy (Exercise 2) on your actual SPIRE-issued SVIDs, not the simulator.
# -----------------------------------------------------------------------------
