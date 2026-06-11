#!/usr/bin/env python3
# Exercise 3 — The Authorization Probe (runnable)
#
# Goal: Apply a deny-by-default AuthorizationPolicy plus an explicit allow on the
#       `inventory` service, then PROVE the policy with a probe:
#         - a call from the ALLOWED principal (cart's service account) succeeds
#         - a call from a DIFFERENT principal gets "RBAC: access denied"
#       even though BOTH callers are inside the mesh with valid mTLS certs.
#
#       This makes the authn/authz layering concrete: mTLS says WHO you are;
#       AuthorizationPolicy says WHAT you may do. Identity is necessary but not
#       sufficient.
#
# Estimated time: 60 minutes. Runnable.
#
# HOW THIS EXERCISE WORKS
#
#   The policy is YAML you apply to the cluster (printed by this script with
#   --print-policy). The PROBE is what this script automates: it runs from inside
#   two different pods (two different service accounts -> two different SPIFFE
#   identities) and reports which calls the mesh allowed and which it denied.
#
#   Because the actual gRPC call must originate from inside a meshed pod (so it
#   carries that pod's mTLS identity), this script is designed to be COPIED INTO
#   a pod and run there, OR driven via `kubectl exec`. It calls the inventory
#   service and classifies the result: OK, DENIED (RBAC), or UNAVAILABLE.
#
# STEP 0 — apply the policies (see --print-policy for the exact YAML):
#   python3 exercise-03-authz-probe.py --print-policy | kubectl apply -f -
#
# STEP 1 — probe from the ALLOWED identity (a pod using cart's service account):
#   kubectl cp exercise-03-authz-probe.py shop/cart-XXXX:/tmp/probe.py -c <app>
#   kubectl exec -n shop deploy/cart -c <app> -- python3 /tmp/probe.py --probe \
#     --target inventory.shop.svc.cluster.local:50051
#   # expect: VERDICT: ALLOWED (the call succeeded)
#
# STEP 2 — probe from a DIFFERENT identity (a pod using another service account):
#   kubectl exec -n shop deploy/frontend -c <app> -- python3 /tmp/probe.py --probe \
#     --target inventory.shop.svc.cluster.local:50051
#   # expect: VERDICT: DENIED (RBAC: access denied) — mesh-enforced, not app code
#
# PREREQUISITES
#   - Exercise 1 done: shop namespace meshed + STRICT mTLS.
#   - inventory exposes a gRPC health service (grpc.health.v1.Health) OR your
#     real inventory.v1 methods. This probe calls the health Check by default;
#     pass --method to call a different one.
#   - cart runs under a service account named `cart`; a second workload
#     (`frontend`) runs under a DIFFERENT service account. The AuthorizationPolicy
#     allows only cart's principal.

import argparse
import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc


DENY_ALL_AND_ALLOW_CART = """\
# Deny everything targeting inventory by default. An ALLOW policy whose rules
# match nothing = nothing is allowed = deny-all. This is the zero-trust posture.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: inventory-deny-all
  namespace: shop
spec:
  selector:
    matchLabels:
      app: inventory
  action: ALLOW
  rules: []          # no rules -> nothing matches -> all denied
---
# Now punch ONE hole: allow only cart's SPIFFE principal to call the inventory
# service methods. Any other in-mesh caller is still denied.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: inventory-allow-cart
  namespace: shop
spec:
  selector:
    matchLabels:
      app: inventory
  action: ALLOW
  rules:
  - from:
    - source:
        principals: ["cluster.local/ns/shop/sa/cart"]   # cart's verified identity
    to:
    - operation:
        # gRPC rides on HTTP/2 POST; methods are the package-qualified path.
        methods: ["POST"]
        paths: ["/inventory.v1.InventoryService/*", "/grpc.health.v1.Health/*"]
"""


def print_policy() -> None:
    print(DENY_ALL_AND_ALLOW_CART)


def classify_error(err: grpc.RpcError) -> str:
    """Map a gRPC failure onto a verdict.

    The mesh denies an unauthorized call by RESETTING the request; the client
    sees PERMISSION_DENIED or UNAVAILABLE with 'RBAC: access denied' in the
    details. We treat the RBAC signature as DENIED and other transport failures
    as UNAVAILABLE (so you don't mistake a down backend for an authz denial).
    """
    code = err.code()
    details = (err.details() or "").lower()
    if "rbac" in details or "access denied" in details or code == grpc.StatusCode.PERMISSION_DENIED:
        return "DENIED"
    if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.UNKNOWN):
        # Could be a reset from RBAC at L4, or a genuinely down backend. The
        # details string disambiguates; if it's empty, report UNAVAILABLE and
        # tell the user to check the sidecar logs for the RBAC line.
        if "rbac" in details:
            return "DENIED"
        return "UNAVAILABLE"
    return f"ERROR({code.name})"


def probe(target: str, method: str) -> int:
    """Make one call through the mesh and print a verdict. Returns an exit code."""
    # plaintext to the LOCAL sidecar; the sidecar wraps it in mTLS to the remote.
    # That is the whole point: the app speaks plaintext to its own sidecar, the
    # mesh adds identity + encryption transparently.
    channel = grpc.insecure_channel(target)
    try:
        if method == "health":
            stub = health_pb2_grpc.HealthStub(channel)
            resp = stub.Check(health_pb2.HealthCheckRequest(), timeout=5.0)
            print(f"VERDICT: ALLOWED  (health status={resp.status})")
            return 0
        else:
            print(f"unknown --method {method}; use 'health' or wire your own stub", file=sys.stderr)
            return 2
    except grpc.RpcError as e:
        verdict = classify_error(e)
        print(f"VERDICT: {verdict}  (code={e.code().name} details={e.details()!r})")
        # DENIED is the EXPECTED outcome for the unauthorized caller — exit 0 so a
        # test harness can assert 'this caller is correctly denied'. UNAVAILABLE is
        # a real problem (backend down or misdiagnosed) — exit non-zero.
        if verdict == "DENIED":
            return 0
        return 1
    finally:
        channel.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Istio AuthorizationPolicy probe.")
    parser.add_argument("--print-policy", action="store_true",
                        help="print the deny-all + allow-cart YAML and exit")
    parser.add_argument("--probe", action="store_true",
                        help="run the probe (do this from INSIDE a meshed pod)")
    parser.add_argument("--target", default="inventory.shop.svc.cluster.local:50051")
    parser.add_argument("--method", default="health", help="'health' or a custom method")
    args = parser.parse_args()

    if args.print_policy:
        print_policy()
        return 0
    if args.probe:
        return probe(args.target, args.method)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   # From the ALLOWED identity (cart's pod / service account):
#   $ kubectl exec -n shop deploy/cart -c app -- python3 /tmp/probe.py --probe
#   VERDICT: ALLOWED  (health status=1)
#
#   # From a DIFFERENT identity (frontend's pod / a different service account):
#   $ kubectl exec -n shop deploy/frontend -c app -- python3 /tmp/probe.py --probe
#   VERDICT: DENIED  (code=PERMISSION_DENIED details='RBAC: access denied')
#
#   # Proof it's the MESH denying, not the app: check inventory's sidecar log:
#   $ kubectl logs -n shop deploy/inventory -c istio-proxy | grep -i rbac
#   ... "rbac_access_denied_matched_policy" ...
#
# THE LESSON: BOTH callers are in the mesh with valid mTLS certs (authentication
# passes for both). Only cart is AUTHORIZED. Identity is necessary but not
# sufficient — STRICT mTLS + deny-by-default + an explicit allow is what
# "zero-trust mesh" means concretely. The frontend was denied by the data plane
# before the request ever reached inventory's application code.
#
# ACCEPTANCE CRITERIA
#   [ ] The allowed caller (cart's SA) gets VERDICT: ALLOWED.
#   [ ] A different caller (another SA) gets VERDICT: DENIED with 'RBAC: access denied'.
#   [ ] inventory's istio-proxy log shows the RBAC denial — proving the MESH denied
#       it, not the application.
#   [ ] You can state the authn/authz layering: mTLS verifies WHO; AuthorizationPolicy
#       decides WHAT; a request must pass both.
#   [ ] Removing the allow-cart policy makes EVEN cart get DENIED (deny-by-default
#       is real) — verify it, then re-apply.
# -----------------------------------------------------------------------------
