#!/usr/bin/env python3
# Exercise 3 — The Capacity Model (runnable calculator)
#
# Goal: Turn the capacity math from Lecture 2 into a calculator that produces the
#       numbers your capacity memo defends. Feed it an arrival rate and a per-request
#       service time and it computes:
#         1. Little's Law concurrency (L = lambda * W)
#         2. The M/M/c utilization-latency curve (latency vs replica count)
#         3. The replica count needed to hold a target utilization
#         4. The single-replica-failure headroom (does rho stay inside SLO?)
#         5. A Universal Scalability Law fit against sample load data (the ceiling)
#
#       Its output IS your memo's numbers. The homework turns these numbers into the
#       one-page memo you defend in next week's mock staff system-design interview.
#
# Estimated time: 60 minutes. Runnable.
#
#   python3 exercise-03-capacity-model.py --rps 800 --service-ms 5 --target-util 0.65
#   python3 exercise-03-capacity-model.py --rps 1200 --service-ms 8 --target-util 0.6 --replicas 12
#
# Only the USL fit uses numpy (optional). Everything else is plain Python/math, on
# purpose — the point is that you can do this on a whiteboard in the interview.
#
# THE MODEL, STATED ONCE
#   lambda (rps)        : arrival rate, requests per second
#   W      (s)          : mean service time per request, measured under LIGHT load
#   mu     (rps/replica): service RATE of one replica = 1 / W
#   c      (replicas)   : number of parallel servers
#   rho                 : utilization = lambda / (c * mu); MUST be < 1 for stability
#   L                   : mean concurrency in the system = lambda * W   (Little's Law)
#
#   The catastrophe is the latency curve: for an M/M/1 server the mean response time
#   is W / (1 - rho), so latency goes VERTICAL as rho -> 1. You size c to keep rho in
#   the 0.6-0.7 band so a burst doesn't push you over the cliff.

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass


# -----------------------------------------------------------------------------
# 1. Little's Law
# -----------------------------------------------------------------------------
def littles_law_concurrency(lam_rps: float, service_s: float) -> float:
    """L = lambda * W. Mean number of in-flight requests."""
    return lam_rps * service_s


# -----------------------------------------------------------------------------
# 2. M/M/c utilization and queueing latency
# -----------------------------------------------------------------------------
def utilization(lam_rps: float, c: int, mu_rps: float) -> float:
    """rho = lambda / (c * mu). Fraction of total capacity in use."""
    return lam_rps / (c * mu_rps)


def erlang_c(c: int, a: float) -> float:
    """Erlang-C: probability an arriving request must QUEUE (wait for a free server).

    a = offered load in Erlangs = lambda / mu = lambda * W (the Little's-Law L, in
    server-seconds of demand). Requires a < c for stability. This is the exact
    M/M/c queueing probability; the mean wait then follows from it.
    """
    if a >= c:
        return 1.0  # unstable / saturated: effectively everything queues
    # numerator: (a^c / c!) * (c / (c - a))
    # denominator: sum_{k=0}^{c-1} a^k/k!  +  (a^c/c!)*(c/(c-a))
    top = (a ** c / math.factorial(c)) * (c / (c - a))
    bottom = sum(a ** k / math.factorial(k) for k in range(c)) + top
    return top / bottom


def mmc_mean_response_time(lam_rps: float, c: int, mu_rps: float) -> float:
    """Mean response time W_total for an M/M/c queue = service time + mean queue wait.

    W_total = (1/mu) + (C(c, a) / (c*mu - lambda))
    where the second term is the mean time spent waiting in the queue (Erlang-C).
    """
    a = lam_rps / mu_rps  # offered load in Erlangs
    if a >= c:
        return float("inf")  # saturated
    wait = erlang_c(c, a) / (c * mu_rps - lam_rps)
    return (1.0 / mu_rps) + wait


def mm1_latency_factor(rho: float) -> float:
    """The 1/(1-rho) blow-up factor for a single server — the cliff, in one number."""
    if rho >= 1.0:
        return float("inf")
    return 1.0 / (1.0 - rho)


# -----------------------------------------------------------------------------
# 3. Replica count for a target utilization
# -----------------------------------------------------------------------------
def replicas_for_target_util(lam_rps: float, mu_rps: float, target_rho: float) -> int:
    """Smallest c such that rho = lambda/(c*mu) <= target_rho. Rounds UP."""
    raw = lam_rps / (target_rho * mu_rps)
    return max(1, math.ceil(raw))


# -----------------------------------------------------------------------------
# 5. Universal Scalability Law fit (optional: needs numpy)
# -----------------------------------------------------------------------------
def usl_throughput(n: float, gamma: float, alpha: float, beta: float) -> float:
    """USL: X(N) = gamma*N / (1 + alpha*(N-1) + beta*N*(N-1)).

    gamma = ideal per-node throughput, alpha = contention (serialization),
    beta = coherency (coordination, grows as N(N-1) -> bends the curve back down).
    """
    return gamma * n / (1.0 + alpha * (n - 1) + beta * n * (n - 1))


def fit_usl(loads, throughputs):
    """Least-squares fit of (gamma, alpha, beta) to measured (N, X) load-test data.

    Returns (gamma, alpha, beta, peak_n) or None if numpy is unavailable. peak_n is
    the concurrency at which throughput is maximized (where adding workers stops
    helping). Derived: N_peak = sqrt((1 - alpha) / beta) for beta > 0.
    """
    try:
        import numpy as np
        from scipy.optimize import curve_fit  # type: ignore
    except Exception:
        return None
    n = np.array(loads, dtype=float)
    x = np.array(throughputs, dtype=float)
    # initial guess: gamma ~ first throughput, small alpha/beta
    p0 = [x[0] / n[0] if n[0] else 1.0, 0.05, 0.001]
    try:
        (gamma, alpha, beta), _ = curve_fit(usl_throughput, n, x, p0=p0, maxfev=10000)
    except Exception:
        return None
    peak = math.sqrt((1 - alpha) / beta) if beta > 0 and alpha < 1 else float("inf")
    return gamma, alpha, beta, peak


# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------
@dataclass
class CapacityReport:
    lam_rps: float
    service_ms: float
    target_util: float
    replicas: int

    def render(self) -> str:
        W = self.service_ms / 1000.0
        mu = 1.0 / W
        L = littles_law_concurrency(self.lam_rps, W)
        rec_c = replicas_for_target_util(self.lam_rps, mu, self.target_util)
        c = self.replicas or rec_c

        lines = []
        lines.append("=" * 64)
        lines.append("CAPACITY MODEL")
        lines.append("=" * 64)
        lines.append(f"  arrival rate  lambda = {self.lam_rps:.0f} rps")
        lines.append(f"  service time  W      = {self.service_ms:.1f} ms  (mu = {mu:.0f} rps/replica)")
        lines.append(f"  target util   rho*   = {self.target_util:.2f}")
        lines.append("")
        lines.append("1. LITTLE'S LAW")
        lines.append(f"   L = lambda * W = {self.lam_rps:.0f} * {W:.4f} = {L:.2f} requests in flight (mean)")
        lines.append(f"   -> your pool/concurrency must hold >= {math.ceil(L)} + headroom for variance")
        lines.append("")
        lines.append("3. REPLICAS FOR TARGET UTILIZATION")
        lines.append(f"   c = ceil(lambda / (rho* * mu)) = ceil({self.lam_rps:.0f} / ({self.target_util:.2f} * {mu:.0f})) = {rec_c}")
        lines.append(f"   -> deploy {rec_c} replicas to hold rho <= {self.target_util:.2f} at peak")
        lines.append("")
        lines.append("2. UTILIZATION-LATENCY CURVE (M/M/c, at the chosen replica count)")
        lines.append(f"   {'replicas c':>10} {'rho':>6} {'1/(1-rho)':>10} {'W_total(ms)':>12}")
        for cc in range(max(1, rec_c - 2), rec_c + 4):
            rho = utilization(self.lam_rps, cc, mu)
            wt = mmc_mean_response_time(self.lam_rps, cc, mu)
            wt_ms = wt * 1000.0 if wt != float("inf") else float("inf")
            factor = mm1_latency_factor(rho)
            mark = "  <- target" if cc == rec_c else ""
            f_s = f"{factor:.2f}" if factor != float("inf") else "inf"
            w_s = f"{wt_ms:.1f}" if wt_ms != float("inf") else "SATURATED"
            lines.append(f"   {cc:>10} {rho:>6.2f} {f_s:>10} {w_s:>12}{mark}")
        lines.append("")
        lines.append("4. SINGLE-REPLICA-FAILURE HEADROOM")
        if rec_c > 1:
            rho_fail = utilization(self.lam_rps, rec_c - 1, mu)
            wt_fail = mmc_mean_response_time(self.lam_rps, rec_c - 1, mu)
            wt_fail_ms = wt_fail * 1000.0 if wt_fail != float("inf") else float("inf")
            verdict = "SURVIVES (inside band)" if rho_fail < 0.85 else "AT RISK (on the cliff)"
            wfs = f"{wt_fail_ms:.1f} ms" if wt_fail_ms != float("inf") else "SATURATED"
            lines.append(f"   lose 1 replica -> {rec_c - 1} left, rho = {rho_fail:.2f}, W_total = {wfs}")
            lines.append(f"   verdict: {verdict}")
        else:
            lines.append("   1 replica: a single failure is a full outage. Add a replica.")
        lines.append("=" * 64)
        return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Capacity model calculator.")
    p.add_argument("--rps", type=float, required=True, help="arrival rate (requests/sec)")
    p.add_argument("--service-ms", type=float, required=True, help="per-request service time (ms), measured under light load")
    p.add_argument("--target-util", type=float, default=0.65, help="target utilization rho* (default 0.65)")
    p.add_argument("--replicas", type=int, default=0, help="optional: evaluate a specific replica count")
    p.add_argument("--usl-demo", action="store_true", help="run the USL fit on sample load data")
    args = p.parse_args()

    report = CapacityReport(args.rps, args.service_ms, args.target_util, args.replicas)
    print(report.render())

    if args.usl_demo:
        # Sample load-test data: throughput (rps) measured at increasing concurrency.
        # Realistic shape — rises, flattens (contention), then bends down (coherency).
        loads = [1, 2, 4, 8, 16, 32, 48, 64]
        throughput = [195, 380, 720, 1280, 1980, 2400, 2350, 2150]
        fit = fit_usl(loads, throughput)
        print("\n5. UNIVERSAL SCALABILITY LAW FIT (sample data)")
        if fit is None:
            print("   (install numpy + scipy to run the USL fit: pip install numpy scipy)")
        else:
            gamma, alpha, beta, peak = fit
            print(f"   gamma (ideal/node) = {gamma:.1f} rps")
            print(f"   alpha (contention) = {alpha:.4f}")
            print(f"   beta  (coherency)  = {beta:.5f}")
            pk = f"{peak:.1f}" if peak != float('inf') else "inf"
            print(f"   -> throughput PEAKS at N ~= {pk} workers; past it, coordination dominates")
            print("      and adding workers REDUCES total throughput. Do not scale past the peak.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# -----------------------------------------------------------------------------
# Expected output (python3 exercise-03-capacity-model.py --rps 800 --service-ms 5 --target-util 0.65)
# -----------------------------------------------------------------------------
#
#   ================================================================
#   CAPACITY MODEL
#   ================================================================
#     arrival rate  lambda = 800 rps
#     service time  W      = 5.0 ms  (mu = 200 rps/replica)
#     target util   rho*   = 0.65
#
#   1. LITTLE'S LAW
#      L = lambda * W = 800 * 0.0050 = 4.00 requests in flight (mean)
#      -> your pool/concurrency must hold >= 4 + headroom for variance
#
#   3. REPLICAS FOR TARGET UTILIZATION
#      c = ceil(lambda / (rho* * mu)) = ceil(800 / (0.65 * 200)) = 7
#      -> deploy 7 replicas to hold rho <= 0.65 at peak
#
#   2. UTILIZATION-LATENCY CURVE (M/M/c, at the chosen replica count)
#      replicas c    rho  1/(1-rho)  W_total(ms)
#               5   0.80       5.00          ...
#               6   0.67       3.03          ...
#               7   0.57       2.33          ...  <- target
#               ...
#
#   4. SINGLE-REPLICA-FAILURE HEADROOM
#      lose 1 replica -> 6 left, rho = 0.67, W_total = ... ms
#      verdict: SURVIVES (inside band)
#   ================================================================
#
# THE MEMO THIS PRODUCES: "order-service peaks at 800 rps, 5 ms service time. Little's
# Law says ~4 in flight. To hold utilization at 0.65 we need 7 replicas; at 7 we are
# at rho=0.57 with the queueing factor at 2.3x. Losing one replica puts us at rho=0.67,
# still inside the band, so we survive a single-replica failure without a latency SLO
# breach. Two losses put us near the cliff -> that's the autoscaling trigger." Defend
# THAT in the mock interview, not "two replicas felt right."
#
# ACCEPTANCE CRITERIA
#   [ ] The calculator runs and prints the Little's-Law L, the replica count, the
#       utilization-latency table, and the single-failure verdict.
#   [ ] You can explain why latency is non-linear in rho (the 1/(1-rho) column) and
#       why you target 0.6-0.7 rather than 0.9.
#   [ ] You run --usl-demo (with numpy+scipy) and read off the throughput peak — the N
#       past which coherency cost makes adding workers HURT.
#   [ ] You produce the order-service memo numbers from YOUR measured service time.
# -----------------------------------------------------------------------------
