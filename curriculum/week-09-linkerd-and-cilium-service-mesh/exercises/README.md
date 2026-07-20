# Week 9 — Exercises

Three focused drills that put the *same* cart topology on Linkerd and Cilium and measure them against your Week 8 Istio baseline. Each takes 45–90 minutes. Do them in order — exercise 3 (the benchmark) consumes the meshes that exercises 1 and 2 stand up. Run everything against your **`cart`/`inventory`** services and your **Week 8 latency baseline** (the control group).

> **Cluster hygiene:** the three meshes do **not** coexist. The clean approach is a **fresh Kind cluster per mesh** (Cilium in particular replaces the CNI). Tear down and rebuild between exercises, or carefully uninstall the previous mesh first. Each exercise's setup section says how.

## Index

1. **[Exercise 1 — Linkerd cart](exercise-01-linkerd-cart.md)** — install Linkerd, mesh `cart`/`inventory`, confirm automatic mTLS is on, and measure the proxy overhead against your Istio baseline. (~75 min, guided)
2. **[Exercise 2 — Cilium service mesh](exercise-02-cilium-mesh.yaml)** — install Cilium as CNI + mesh, enable mutual authentication, apply an L7 `CiliumNetworkPolicy`, and confirm there's no per-pod proxy — runnable manifests. (~75 min, runnable)
3. **[Exercise 3 — The latency bench](exercise-03-latency-bench.py)** — a driver that benchmarks p50/p99 across no-mesh, Istio, Linkerd, and Cilium on the identical workload, and emits the comparison table your ADR is built on. (~60 min, runnable)

## How to work the exercises

- Have your **Week 8 baseline** (Istio p50/p99 + sidecar memory) in hand. Every number this week is read against it.
- Have the **`linkerd`** and **`cilium`** CLIs installed. `linkerd version` and (after install) `cilium version` work.
- **Measure the same thing the same way on each mesh.** Same workload, same load generator, same QPS, same duration. A comparison is only fair if the only thing that changed is the mesh.
- When a mesh "isn't working," use its own check command first: `linkerd check` for Linkerd, `cilium status` / `cilium connectivity test` for Cilium. They're the analogue of `istioctl analyze`.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match the *shape* (not the exact ms — those are hardware-dependent), you're not done.

## Running the exercises

The `.yaml` exercise is applied with `kubectl` after `cilium install`:

```bash
cilium install
kubectl apply -f exercise-02-cilium-mesh.yaml
cilium connectivity test         # confirm the mesh works end to end
```

The `.py` benchmark driver shells out to your load generator and aggregates:

```bash
pip install numpy
python3 exercise-03-latency-bench.py --mesh linkerd --target cart.shop.svc.cluster.local:50051
```

The header of each file lists exact prerequisites and the per-mesh setup. There are no solutions checked in. After you finish, search GitHub for `c22-week-09` to compare.
