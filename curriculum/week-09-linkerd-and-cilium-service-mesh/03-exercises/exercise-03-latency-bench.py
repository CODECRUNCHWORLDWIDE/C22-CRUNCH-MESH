#!/usr/bin/env python3
# Exercise 3 — The Latency Bench (runnable)
#
# Goal: Benchmark the SAME cart->inventory gRPC workload across four configurations
#       — no-mesh, Istio, Linkerd, Cilium — and emit the comparison table your ADR
#       is built on. The driver runs a load generator (ghz or fortio), parses
#       p50/p99, records per-pod proxy memory (from `kubectl top`), and stores one
#       row per mesh in a JSON file so the final --summary prints the whole table.
#
#       The point is METHODOLOGICAL: measure the same thing the same way on each
#       mesh, run long enough to be stable, and be honest that a Kind benchmark is
#       a RELATIVE instrument (ordering + ratios), not absolute production numbers.
#
# Estimated time: 60 minutes. Runnable.
#
# HOW TO USE THIS FILE
#
#   For EACH mesh (set up that mesh per Exercises 1/2, or none for the baseline),
#   run the driver tagged with the mesh name:
#
#     # baseline (no mesh): direct gRPC
#     python3 exercise-03-latency-bench.py --mesh no-mesh \
#       --target cart.shop.svc.cluster.local:50051
#
#     # with Istio meshed (Week 8 cluster):
#     python3 exercise-03-latency-bench.py --mesh istio --proxy-container istio-proxy \
#       --target cart.shop.svc.cluster.local:50051
#
#     # with Linkerd meshed:
#     python3 exercise-03-latency-bench.py --mesh linkerd --proxy-container linkerd-proxy \
#       --target cart.shop.svc.cluster.local:50051
#
#     # with Cilium (no per-pod proxy; proxy memory is N/A):
#     python3 exercise-03-latency-bench.py --mesh cilium \
#       --target cart.shop.svc.cluster.local:50051
#
#   Each run appends a row to bench-results.json. When all four are done:
#
#     python3 exercise-03-latency-bench.py --summary
#
#   ...prints the comparison table. RUN EACH MESH ON ITS OWN FRESH CLUSTER (they
#   don't coexist); the JSON accumulates across runs so the summary is cross-mesh.
#
# REQUIREMENTS
#   - ghz (preferred, gRPC-native) or fortio on PATH. The driver shells out to it.
#   - kubectl access to the cluster currently running the mesh under test.
#   - A load generator pod/binary that can reach the target. Running the driver
#     from a host with kubectl + a port-forward, or from inside the cluster, both work.
#   - pip install numpy   (for percentile aggregation if you parse raw latencies)

import argparse
import json
import os
import re
import subprocess
import sys

RESULTS_FILE = "bench-results.json"

# Fixed load parameters — IDENTICAL across meshes so the comparison is fair.
# Changing these between meshes invalidates the comparison. That is the whole
# methodological point.
QPS = 200
CONCURRENCY = 8
DURATION_S = 60          # long enough to be stable; discard warm-up
WARMUP_S = 10


def run_ghz(target: str, method: str) -> dict:
    """Drive ghz against the target and parse p50/p99 (milliseconds).

    ghz emits JSON with a latencyDistribution; we pull the 50th and 99th
    percentiles. If you use fortio instead, swap this function — the contract is
    'return {p50_ms, p99_ms, rps, error_rate}'.
    """
    cmd = [
        "ghz", "--insecure",
        "--call", method,
        "-c", str(CONCURRENCY),
        "--qps", str(QPS),
        "-z", f"{DURATION_S}s",
        "-x", f"{WARMUP_S}s",      # skip warm-up window
        "--format", "json",
        target,
    ]
    print(f"  $ {' '.join(cmd)}")
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)

    # ghz reports latencies in nanoseconds in latencyDistribution.
    dist = {d["percentage"]: d["latency"] for d in data.get("latencyDistribution", [])}
    p50_ms = dist.get(50, 0) / 1e6
    p99_ms = dist.get(99, 0) / 1e6
    rps = data.get("rps", 0.0)
    total = data.get("count", 1)
    errors = sum(v for k, v in data.get("statusCodeDistribution", {}).items() if k != "OK")
    return {
        "p50_ms": round(p50_ms, 2),
        "p99_ms": round(p99_ms, 2),
        "rps": round(rps, 1),
        "error_rate": round(errors / total, 4) if total else 0.0,
    }


def proxy_memory_mib(namespace: str, proxy_container: str | None) -> str:
    """Sum the per-pod proxy-container memory via `kubectl top`.

    For Cilium there is no per-pod proxy, so proxy_container is None and we return
    'N/A (no per-pod proxy)' — which is itself a key result.
    """
    if proxy_container is None:
        return "N/A (no per-pod proxy)"
    try:
        out = subprocess.run(
            ["kubectl", "top", "pod", "-n", namespace, "--containers", "--no-headers"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return "unknown (metrics-server?)"
    total_mib = 0
    count = 0
    for line in out.splitlines():
        if proxy_container in line:
            m = re.search(r"(\d+)Mi", line)
            if m:
                total_mib += int(m.group(1))
                count += 1
    if count == 0:
        return f"0 (no {proxy_container} found)"
    return f"~{total_mib // count} MiB/pod"


def load_results() -> list:
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return []


def save_results(rows: list) -> None:
    with open(RESULTS_FILE, "w") as f:
        json.dump(rows, f, indent=2)


def bench(args) -> int:
    method = args.method
    print(f"[bench] mesh={args.mesh} target={args.target} "
          f"qps={QPS} c={CONCURRENCY} dur={DURATION_S}s")
    lat = run_ghz(args.target, method)
    mem = proxy_memory_mib(args.namespace, args.proxy_container)

    row = {"mesh": args.mesh, **lat, "proxy_mem": mem}
    rows = [r for r in load_results() if r["mesh"] != args.mesh]  # replace prior run for this mesh
    rows.append(row)
    save_results(rows)

    print(f"[bench] recorded: {row}")
    if lat["error_rate"] > 0.01:
        print(f"WARNING: error_rate {lat['error_rate']:.2%} > 1% — investigate before "
              f"trusting this row (a misconfigured mesh, not a real result).", file=sys.stderr)
        return 1
    return 0


def summary() -> int:
    rows = load_results()
    if not rows:
        print("no results yet — run the bench for each mesh first.", file=sys.stderr)
        return 1
    order = {"no-mesh": 0, "istio": 1, "linkerd": 2, "cilium": 3}
    rows.sort(key=lambda r: order.get(r["mesh"], 99))

    print(f"{'MESH':<12}{'p50(ms)':>9}{'p99(ms)':>9}{'RPS':>8}{'err':>7}  proxy-mem")
    print("-" * 64)
    for r in rows:
        print(f"{r['mesh']:<12}{r['p50_ms']:>9}{r['p99_ms']:>9}"
              f"{r['rps']:>8}{r['error_rate']*100:>6.1f}%  {r['proxy_mem']}")
    print("-" * 64)
    print("NOTE: a Kind benchmark is RELATIVE. Trust the ordering and ratios, not\n"
          "      the absolute ms. Qualify every claim to THIS workload (gRPC unary,\n"
          f"      {QPS} qps). Re-run any row you can't reproduce instead of citing it.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Cross-mesh latency benchmark driver.")
    p.add_argument("--mesh", choices=["no-mesh", "istio", "linkerd", "cilium"])
    p.add_argument("--target", default="cart.shop.svc.cluster.local:50051")
    p.add_argument("--method", default="grpc.health.v1.Health.Check")
    p.add_argument("--namespace", default="shop")
    p.add_argument("--proxy-container", default=None,
                   help="istio-proxy / linkerd-proxy; omit for no-mesh and cilium")
    p.add_argument("--summary", action="store_true", help="print the cross-mesh table")
    args = p.parse_args()

    if args.summary:
        return summary()
    if not args.mesh:
        p.print_help()
        return 2
    return bench(args)


if __name__ == "__main__":
    sys.exit(main())


# -----------------------------------------------------------------------------
# Expected output (--summary, after running all four)
# -----------------------------------------------------------------------------
#
#   MESH         p50(ms)  p99(ms)     RPS    err  proxy-mem
#   ----------------------------------------------------------------
#   no-mesh         1.80     6.10   200.0   0.0%  N/A (no per-pod proxy)
#   istio           2.40     9.30   199.6   0.0%  ~55 MiB/pod
#   linkerd         2.10     7.40   199.8   0.0%  ~12 MiB/pod
#   cilium          1.90     6.80   199.9   0.0%  N/A (no per-pod proxy)
#   ----------------------------------------------------------------
#   NOTE: a Kind benchmark is RELATIVE. ...
#
# YOUR exact ms will differ (hardware-dependent) — that's fine. The SHAPE is the
# result: all meshes add overhead; Linkerd's micro-proxy is far lighter than the
# Istio sidecar; Cilium's eBPF L4 path has no per-pod proxy memory at all. THAT
# table, with your numbers, is the evidence section of your ADR.
#
# ACCEPTANCE CRITERIA
#   [ ] You ran the IDENTICAL load (same qps/concurrency/duration/method) on all
#       four configurations — the comparison is fair.
#   [ ] --summary prints a four-row table with p50, p99, and proxy memory.
#   [ ] The proxy-mem column reflects the architecture: heavy for Istio sidecar,
#       light for Linkerd, N/A for Cilium L4.
#   [ ] You discarded (re-ran) any row whose error_rate exceeded 1% rather than
#       citing it — a high-error row is a misconfiguration, not a measurement.
#   [ ] Your writeup states the benchmark is RELATIVE and qualifies the claim to
#       this workload.
# -----------------------------------------------------------------------------
