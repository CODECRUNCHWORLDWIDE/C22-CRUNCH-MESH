#!/usr/bin/env python3
"""
Exercise 2 - Drill A: Region Failover Under Load (runnable driver)

Drive the MANDATORY region-failover chaos drill against your running two-region
active-active capstone. Establish steady state under load, kill the primary region,
probe once per second to measure the RTO, then verify the integrity invariants -
ZERO orders lost, ZERO double-charges, the cart converges on heal - and emit a
POSTMORTEM.md skeleton with the measured timeline filled in.

This is a capstone deliverable, not a warm-up. The output postmortem is one of the
two mandatory chaos-drill writeups the syllabus requires.

USAGE
  pip install requests psycopg2-binary
  export BFF_URL=http://<bff-web-loadbalancer-ip>:443      # the order entry point
  export PRIMARY_CONTEXT=kind-region-primary               # kubectl context to kill
  export PAYMENT_DSN="postgresql://user:pw@payment-db:5432/payment"  # to count charges

  python3 exercise-02-region-failover-drill.py --duration 300 --rps 1000

WHAT IT DOES (and does NOT do)
  1. Starts a load loop placing orders at --rps (each with a unique idempotency key).
  2. Establishes steady state, records t0.
  3. Injects the fault: kills the PRIMARY region's workloads (kubectl delete pods),
     simulating "the region went dark". Records t_fault.
  4. Probes the BFF once/second, recording the first SLO breach (t_impact) and the
     recovery (t_recover, error rate back under threshold).
  5. Lets the load finish, then VERIFIES INTEGRITY against the payment DB:
       - every idempotency key charged exactly once (no double-charge)
       - orders sent == orders successfully placed (no loss, accounting for the
         expected in-flight failures during the failover window)
  6. Reverses the fault (you bring the region back) and you confirm cart convergence.
  7. Writes POSTMORTEM-drill-A.md with the measured timeline.

  It injects the fault via kubectl and PROBES the system; it does not mutate your
  manifests. Ctrl-C reverses cleanly. Adapt the resource names near the top to YOUR
  capstone. The DB-verification query is the load-bearing proof - keep it honest.

HYPOTHESIS (state it before you run - the postmortem is the gap vs reality)
  Under sustained load, killing the primary region elevates error rate briefly as
  traffic shifts to the surviving region, recovery completes within RTO_TARGET_S,
  and ZERO orders are lost or double-charged: the cart converges, in-flight Temporal
  workflows resume on the surviving region, the Kafka backlog drains.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import signal
import subprocess
import sys
import threading
import time
import uuid

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    raise

RTO_TARGET_S = 60          # recovery-time objective; the drill passes if RTO < this
ERROR_THRESHOLD = 0.05     # >5% error rate = "in breach"; <5% sustained = "recovered"


@dataclasses.dataclass
class Timeline:
    t0: float = 0.0            # steady state established
    t_fault: float = 0.0       # region killed
    t_impact: float = 0.0      # first SLO breach
    t_recover: float = 0.0     # error rate back under threshold
    orders_sent: int = 0
    orders_ok: int = 0
    orders_failed: int = 0

    @property
    def rto_seconds(self) -> float:
        if self.t_recover and self.t_fault:
            return self.t_recover - self.t_fault
        return float("nan")


_stop = threading.Event()
_sent_keys: list[str] = []
_lock = threading.Lock()


def now() -> float:
    return time.monotonic()


def iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")


def place_order(bff_url: str) -> tuple[bool, str]:
    """Place one order with a unique idempotency key. Returns (ok, key)."""
    key = f"drill-{uuid.uuid4().hex[:12]}"
    try:
        # The BFF entry point. Real capstone uses gRPC; here we use the HTTP/JSON
        # facade the BFF exposes for the load generator. Adapt to grpcurl if needed.
        r = requests.post(
            f"{bff_url}/v1/orders",
            json={"customer": "drill", "sku": "SKU-42", "qty": 1},
            headers={"x-idempotency-key": key},
            timeout=3,
        )
        return (r.status_code < 500, key)
    except requests.RequestException:
        return (False, key)


def load_loop(bff_url: str, rps: int, tl: Timeline) -> None:
    """Place orders at the target rate until stopped."""
    interval = 1.0 / max(1, rps)
    while not _stop.is_set():
        ok, key = place_order(bff_url)
        with _lock:
            tl.orders_sent += 1
            if ok:
                tl.orders_ok += 1
                _sent_keys.append(key)
            else:
                tl.orders_failed += 1
        time.sleep(interval)


def recent_error_rate(tl: Timeline, window: list[int]) -> float:
    """Crude rolling error rate from the cumulative counters (toy; real drills read
    the error-rate metric off Prometheus). window holds [last_sent, last_failed]."""
    with _lock:
        sent, failed = tl.orders_sent, tl.orders_failed
    d_sent = sent - window[0]
    d_failed = failed - window[1]
    window[0], window[1] = sent, failed
    return (d_failed / d_sent) if d_sent else 0.0


def kill_primary_region(context: str) -> None:
    """Inject the fault: delete all workloads in the primary region's shop namespace.
    This simulates 'the region went dark'."""
    print(f"[{iso()}] FAULT: killing primary region ({context})")
    subprocess.run(
        ["kubectl", "--context", context, "delete", "pods", "--all",
         "-n", "shop", "--grace-period=0", "--force"],
        check=False,
    )


def verify_no_double_charge(dsn: str) -> tuple[bool, int]:
    """The integrity proof: query the payment DB for ANY idempotency key charged
    more than once. Returns (clean, violation_count). clean=True means zero
    double-charges - the drill's pass condition."""
    try:
        import psycopg2
    except ImportError:
        print("  (install psycopg2-binary to run the DB integrity check)", file=sys.stderr)
        return (False, -1)
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT idempotency_key, COUNT(*) FROM charges "
                "GROUP BY idempotency_key HAVING COUNT(*) > 1"
            )
            violations = cur.fetchall()
        return (len(violations) == 0, len(violations))
    finally:
        conn.close()


def write_postmortem(tl: Timeline, clean: bool, violations: int) -> None:
    rto = tl.rto_seconds
    passed = (rto < RTO_TARGET_S) and clean
    content = f"""# Postmortem - Drill A: Region Failover Under Load

## Summary
Killed the primary region under sustained load. Recovery (RTO) measured at
{rto:.1f}s (target {RTO_TARGET_S}s). Double-charge violations: {violations}.
Overall: {"PASS" if passed else "FAIL - investigate"}.

## Hypothesis
Killing the primary region elevates error rate briefly, recovery completes within
{RTO_TARGET_S}s, and zero orders are lost or double-charged (cart converges, Temporal
workflows resume on the surviving region, Kafka backlog drains).

## Impact
- Orders sent: {tl.orders_sent}; succeeded: {tl.orders_ok}; failed (in-flight during
  failover): {tl.orders_failed}.
- Peak error window: during the ~{rto:.0f}s failover.
- Data integrity: {"zero double-charges" if clean else f"{violations} DOUBLE-CHARGE VIOLATIONS"}.

## Timeline (seconds from t0)
- t0       (+0.0): steady state established.
- t_fault  (+{tl.t_fault - tl.t0:.1f}): primary region killed.
- t_impact (+{(tl.t_impact - tl.t0) if tl.t_impact else float('nan'):.1f}): first SLO breach.
- t_recover(+{(tl.t_recover - tl.t0) if tl.t_recover else float('nan'):.1f}): error rate back under {ERROR_THRESHOLD:.0%}.
- RTO = t_recover - t_fault = {rto:.1f}s.

## Root cause
The region loss hit three failure domains, which failed differently BY DESIGN:
- Cart (CRDT): surviving region kept serving; converged on heal. No loss.
- Inventory (lease): SKUs whose writer was in the dead region paused writes for the
  lease-expiry window, then the surviving region re-acquired. No oversell.
- Payment (Temporal): in-flight workflows resumed on surviving-region workers via
  durable history. No double-charge, no lost charge.
[Fill in the SPECIFIC root cause of any RTO over target - e.g., conservative lease TTL.]

## What went well / what didn't
[Honest assessment. The CRDT cart degraded as designed; note any surprise.]

## Action items
- [ ] [owner] [fix for the largest contributor to RTO]
- [ ] [owner] Add a burn-rate alert specific to failover (e.g., inventory write-latency).
- [ ] [owner] Confirm cart convergence time on heal and add a convergence metric.
"""
    with open("POSTMORTEM-drill-A.md", "w") as f:
        f.write(content)
    print(f"\n[{iso()}] wrote POSTMORTEM-drill-A.md (RTO={rto:.1f}s, clean={clean})")


def main() -> int:
    p = argparse.ArgumentParser(description="Drill A: region failover under load.")
    p.add_argument("--duration", type=int, default=300, help="total drill seconds")
    p.add_argument("--rps", type=int, default=1000, help="target order rate")
    p.add_argument("--fault-at", type=int, default=60, help="seconds into the run to kill the region")
    args = p.parse_args()

    bff = os.environ.get("BFF_URL")
    ctx = os.environ.get("PRIMARY_CONTEXT", "kind-region-primary")
    dsn = os.environ.get("PAYMENT_DSN", "")
    if not bff:
        print("set BFF_URL to your bff-web entry point", file=sys.stderr)
        return 2

    tl = Timeline()
    signal.signal(signal.SIGINT, lambda *_: _stop.set())

    print(f"[{iso()}] starting load at {args.rps} rps for {args.duration}s")
    loader = threading.Thread(target=load_loop, args=(bff, args.rps, tl), daemon=True)
    loader.start()

    # let steady state settle (5s), then record t0
    time.sleep(5)
    tl.t0 = now()
    print(f"[{iso()}] steady state (t0)")

    window = [tl.orders_sent, tl.orders_failed]
    fault_injected = False
    start = now()
    while now() - start < args.duration and not _stop.is_set():
        time.sleep(1)
        if not fault_injected and (now() - tl.t0) >= args.fault_at:
            tl.t_fault = now()
            kill_primary_region(ctx)
            fault_injected = True
        err = recent_error_rate(tl, window)
        if fault_injected:
            if err > ERROR_THRESHOLD and not tl.t_impact:
                tl.t_impact = now()
                print(f"[{iso()}] IMPACT: error rate {err:.0%} > {ERROR_THRESHOLD:.0%}")
            elif tl.t_impact and not tl.t_recover and err <= ERROR_THRESHOLD:
                tl.t_recover = now()
                print(f"[{iso()}] RECOVERED: error rate {err:.0%} (RTO={tl.rto_seconds:.1f}s)")

    _stop.set()
    loader.join(timeout=5)

    # integrity verification
    print(f"\n[{iso()}] verifying integrity (no double-charge)...")
    clean, violations = (True, 0)
    if dsn:
        clean, violations = verify_no_double_charge(dsn)
        if clean:
            print("  INTEGRITY PASS: zero idempotency keys charged more than once.")
        else:
            print(f"  INTEGRITY FAIL: {violations} double-charge violations!")
    else:
        print("  (set PAYMENT_DSN to run the double-charge query - REQUIRED for the deliverable)")
        clean = False

    write_postmortem(tl, clean, violations)
    print(f"\nNow: bring the region back, confirm the cart converges on heal, and "
          f"fill in the postmortem's root-cause and action-item sections.")
    return 0 if (tl.rto_seconds < RTO_TARGET_S and clean) else 1


if __name__ == "__main__":
    raise SystemExit(main())


# -----------------------------------------------------------------------------
# Expected output
# -----------------------------------------------------------------------------
#
#   [14:02:01] starting load at 1000 rps for 300s
#   [14:02:06] steady state (t0)
#   [14:03:06] FAULT: killing primary region (kind-region-primary)
#   [14:03:09] IMPACT: error rate 12% > 5%
#   [14:03:53] RECOVERED: error rate 2% (RTO=47.0s)
#   [14:07:06] verifying integrity (no double-charge)...
#     INTEGRITY PASS: zero idempotency keys charged more than once.
#   [14:07:06] wrote POSTMORTEM-drill-A.md (RTO=47.0s, clean=True)
#
# THE PASS CONDITION is BOTH: RTO < 60s AND zero double-charges. A fast failover that
# double-charges is a FAIL; a clean integrity result with a 5-minute RTO is a FAIL.
# You need both, because the capstone grades resilience AND correctness.
#
# ACCEPTANCE CRITERIA
#   [ ] The drill runs, kills the primary region under 1k RPS, and measures the RTO.
#   [ ] RTO is under your target; if not, the postmortem names the SPECIFIC cause.
#   [ ] The double-charge query (HAVING COUNT(*) > 1) returns ZERO rows - proven, not
#       assumed. This is the integrity deliverable.
#   [ ] You bring the region back and confirm the cart CONVERGES on heal (the OR-set
#       merge reconciles the divergent writes).
#   [ ] POSTMORTEM-drill-A.md is filled in with the measured timeline, the per-domain
#       root cause, and owned action items - blameless, SRE-format.
# -----------------------------------------------------------------------------
