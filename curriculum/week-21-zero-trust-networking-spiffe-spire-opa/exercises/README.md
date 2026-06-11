# Week 21 — Exercises

Three focused drills that close the zero-trust loop: issue verifiable identity, author the policy that authorizes it, and *prove* the loop denies a violation. Each takes 45–90 minutes. Do them in order — exercise 1 deploys SPIRE and issues SVIDs (the identity), exercise 2 writes the OPA/Rego policy that authorizes those identities (the authorization), and exercise 3 probes the closed loop with a deliberate violation (the proof). Run everything against your **`cart`/`inventory`/`payment`** services from Phase 1–2 (or the minimal stand-ins each exercise names).

## Index

1. **[Exercise 1 — Deploy SPIRE and issue SVIDs](exercise-01-deploy-spire-issue-svids.md)** — deploy the SPIRE server + agent on Kind, register `cart` and `inventory` as workloads, issue them SVIDs via the Workload API, and inspect the SPIFFE identity in the X.509 SVID's URI SAN. (~75 min, guided)
2. **[Exercise 2 — The SPIFFE-keyed OPA policy](exercise-02-opa-spiffe-authz.rego)** — a complete Rego policy authorizing service-to-service calls by SPIFFE identity, deny-by-default, with the allow-matrix and a full `opa test` suite proving allows and denies. (~60 min, runnable)
3. **[Exercise 3 — The zero-trust violation probe](exercise-03-zero-trust-violation-probe.py)** — probe the closed loop: an allowed identity passes; a valid-but-unauthorized identity is DENIED by OPA; a forged/wrong-trust-domain identity is rejected at mTLS. (~60 min, runnable)

## How to work the exercises

- Have a **Kind** cluster with headroom and **SPIRE 1.9+** installable (the exercise uses the Kubernetes quickstart manifests). `kubectl get nodes` is Ready.
- Have **`opa`** installed (`opa version`) for exercise 2 (`opa eval`, `opa test`) and **Python 3.10+** for exercise 3.
- Have the **Week 8 SPIFFE/mTLS** literacy fresh — you've seen `spiffe://...` identities and deny-by-default authz; this makes the identity explicit (SPIRE) and the policy programmable (OPA).
- **Inspect the identity before and after every change.** `kubectl exec` into a workload and call the Workload API (or decode the SVID with `openssl x509 -text`) to *see* the SPIFFE ID in the URI SAN — the zero-trust equivalent of last week's convergence proof. Train the habit of confirming the identity is *really* what you registered, not what you assumed.
- When a call is denied and you don't expect it (or allowed and you do), check three things in order: does the workload have a valid SVID (Workload API returns it)? does its SPIFFE ID match a rule in the OPA allow-matrix? did OPA actually evaluate (the ext_authz/sidecar is wired)?
- Each runnable exercise ends with an **expected output** block. If a *denied* call succeeds, you've found the over-broad-policy footgun (the Challenge), not the fix.

## Running the exercises

The `.rego` exercise is evaluated and tested with `opa`:

```bash
opa test exercise-02-opa-spiffe-authz.rego -v          # run the policy's unit tests
echo '{"caller_spiffe_id":"spiffe://shop/ns/shop/sa/cart","target_service":"payment","method":"Charge"}' \
  | opa eval -d exercise-02-opa-spiffe-authz.rego -I 'data.authz.allow'   # expect false (cart can't call payment)
```

The `.py` exercise drives the violation probe:

```bash
python3 exercise-03-zero-trust-violation-probe.py
```

The header of each file lists the exact prerequisites. If your Phase-1 services aren't ready, exercise 1 names the SPIRE sample workloads as stand-ins.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-21` to compare.
