# Week 9 — Linkerd and Cilium Service Mesh — The Alternatives

Welcome to the week you stop being an Istio user and become a mesh *architect*. Last week you ran Istio: sidecars, mTLS, canary, the works. This week you run the same cart topology on **Linkerd** and on **Cilium**, measure the latency each one adds against your Istio baseline, and write the architectural decision record that recommends one of the three to a real org. The deliverable is not "I can install Linkerd" — it's "I can defend a mesh choice under cross-examination with numbers and a clear-eyed account of the trade-offs."

We assume you finished Week 8. You have `cart` and `inventory` meshed on Istio with STRICT mTLS, a working canary, and — crucially — a **latency baseline** captured in your `cart-mesh` `bench/` directory. That baseline is the control group for this entire week. Every number you produce on Linkerd and Cilium is measured against it. If you skipped the benchmark in Week 8, go back and capture it first; a comparison with no baseline is just three sets of numbers floating in space.

The one thing to internalize before you read another line: **the three meshes embody three different philosophies, and "which is best" is the wrong question — the right question is "best for whom."** Istio is the maximalist: the most features, the most knobs, sidecar-or-ambient flexibility, and the most operational surface. Linkerd is the minimalist: a tiny purpose-built Rust micro-proxy, ruthless simplicity, "it just works" as an explicit design goal — at the cost of fewer L7 features. Cilium is the structuralist: no per-pod proxy *at all* for L4, because mTLS and policy live in the kernel via **eBPF** — radically efficient, but it asks you to think about your mesh as part of your CNI, and its L7 story (an embedded Envoy) is younger than Istio's. None of these is "the winner." Each wins for a particular org, and the skill this week builds is naming *which* org and *why*.

This week is where you earn the right to have an opinion about service meshes.

## Learning objectives

By the end of this week, you will be able to:

- **Describe** Linkerd's architecture — the control plane, the Rust-based `linkerd2-proxy` micro-proxy, and the design choices (no Lua, no Envoy, minimal config surface) that make it the "simple mesh."
- **Describe** Cilium's service-mesh architecture — eBPF-based L4 + mTLS in the kernel with *no per-pod proxy*, and the per-node embedded Envoy used only for L7 — and explain what eBPF buys and what it constrains.
- **Articulate** the sidecar vs sidecar-less debate precisely: where the sidecar's per-pod cost comes from, what sidecar-less (ambient, Cilium) saves, and what each gives up.
- **Install** Linkerd and Cilium service mesh on Kind, bring the `cart`/`inventory` topology onto each, and turn on mTLS — reaching the same security posture three different ways.
- **Measure** p50/p99 latency overhead empirically across Istio, Linkerd, and Cilium on an identical workload, and interpret the numbers honestly (including the limits of a Kind benchmark).
- **Compare** the three meshes on the axes that actually drive adoption: latency/resource cost, operational complexity, L7 feature depth, mTLS model, multi-cluster story, and ecosystem maturity.
- **Write** an Architectural Decision Record (ADR) that recommends one mesh for a specific hypothetical 200-engineer org, defends the choice against the obvious counter-arguments, and states what would change the decision.
- **Recognize** when the right answer is *no mesh at all* — that a 6-service shop is better served by the Week 7 gateway-plus-library approach, and that adopting any of these three by reflex is the mistake.

## Prerequisites

This week assumes you have completed **C22 weeks 1–8**, or have equivalent fluency. Specifically:

- A working **Kind** cluster you can tear down and rebuild quickly — you'll install three different meshes this week, and the clean approach is a fresh cluster per mesh (or careful uninstall between them; meshes do not coexist).
- Your **`cart`/`inventory`** topology deployable, and your **Week 8 Istio latency baseline** captured in `bench/`. This is the control group.
- **`linkerd`** and **`cilium`** CLIs installable (`linkerd version`, `cilium version` after install).
- The **mesh literacy from Week 8**: you know what a sidecar, mTLS STRICT, a canary, and the sidecar tax are. This week is about *how three meshes differ* on exactly those concepts.
- Comfort with a **load generator** (`fortio`, `ghz`) and reading p50/p99 latency, and with `kubectl top` for memory.
- Conceptual familiarity with **eBPF** is helpful but not required — Lecture 2 starts from "programs the kernel attaches to events" and builds up.

You do **not** need prior Linkerd or Cilium experience. We install both from scratch. If you have only ever run Istio, this is the week you learn that "service mesh" is a category, not a product.

## Topics covered

- **Linkerd architecture**: the control plane (destination, identity, proxy-injector), the **`linkerd2-proxy`** — a purpose-built, memory-safe **Rust** micro-proxy that does *only* what a mesh sidecar needs (far smaller and lighter than a general-purpose Envoy), and Linkerd's explicit "simplicity is a feature" philosophy.
- **Cilium service mesh**: **eBPF** as the substrate — L4 load balancing, network policy, and **mTLS handled in the kernel** with no per-pod proxy; the per-node **embedded Envoy** invoked only for L7 (HTTP routing, L7 policy); the convergence of CNI and mesh into one layer.
- **The sidecar vs sidecar-less debate**: the per-pod Envoy cost (memory × pods, two extra hops, startup ordering) versus sidecar-less models (Istio ambient's ztunnel, Cilium's kernel path, Linkerd's still-sidecar-but-tiny proxy). What each model can and cannot do, and why the debate is about *cost-vs-L7-flexibility*, not "sidecars bad."
- **mTLS three ways**: Linkerd's automatic mTLS with its own identity system; Cilium's eBPF/SPIFFE-based mutual authentication; and how both compare to Istio's istiod-CA + Envoy model from Week 8.
- **Empirical comparison**: measuring p50/p99 latency overhead and per-pod (or per-node) memory across the three on an identical `cart`→`inventory` workload, and the honesty required to interpret a local Kind benchmark (it shows *relative* overhead, not production absolutes).
- **The decision axes**: latency/resource cost, operational complexity (how many moving parts, how steep the learning curve), L7 feature depth (rich routing/policy vs the essentials), the multi-cluster story, and ecosystem/maturity. How real orgs weight these.
- **The ADR discipline**: writing a decision record that states the context, the options, the decision, the consequences, and the conditions that would reverse it — the staff-engineer artifact that turns "I prefer X" into "we chose X for these reasons, and here's when we'd revisit."
- **When no mesh wins**: recognizing that the gateway-plus-library approach from Week 7 is the right answer for small/simple systems, and that the cost of *any* mesh is only justified at a scale and team-count where uniform east-west security and telemetry can't be achieved another way.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Linkerd architecture; the Rust micro-proxy; simplicity |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Install Linkerd; mesh cart/inventory; measure overhead |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Cilium + eBPF; sidecar-less mTLS; the kernel data plane |   2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | The three-way comparison; the latency bench; the axes  |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | The ADR; defending a mesh choice; when no mesh wins     |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work (the bench + the ADR)           |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, ADR polish                               |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The Linkerd docs, the Cilium/eBPF material, the honest comparison reading, the talks worth your time |
| [lecture-notes/01-linkerd-and-the-rust-micro-proxy.md](./lecture-notes/01-linkerd-and-the-rust-micro-proxy.md) | Linkerd architecture, the linkerd2-proxy, automatic mTLS, and the simplicity philosophy |
| [lecture-notes/02-cilium-ebpf-and-the-three-way-comparison.md](./lecture-notes/02-cilium-ebpf-and-the-three-way-comparison.md) | Cilium + eBPF, sidecar-less mTLS, the empirical comparison, the decision axes, and the ADR |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-linkerd-cart.md](./exercises/exercise-01-linkerd-cart.md) | Install Linkerd, mesh cart/inventory, turn on mTLS, and measure the overhead vs your Istio baseline |
| [exercises/exercise-02-cilium-mesh.yaml](./exercises/exercise-02-cilium-mesh.yaml) | Cilium service mesh: enable mTLS + an L7 CiliumNetworkPolicy on the cart topology — runnable manifests |
| [exercises/exercise-03-latency-bench.py](./exercises/exercise-03-latency-bench.py) | A driver that benchmarks p50/p99 across all three meshes and emits a comparison table |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-defend-the-mesh-choice.md](./challenges/challenge-01-defend-the-mesh-choice.md) | A mock staff design review: defend a mesh recommendation against three pointed objections |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the 200-engineer-org mesh ADR |
| [mini-project/README.md](./mini-project/README.md) | `mesh-bakeoff`: the cart topology on all three meshes, benchmarked, with a defensible ADR |

## The "the numbers are real" promise

C22 uses a recurring marker for every exercise that ends in a measured result you can defend. This week's canonical one is the latency comparison, captured identically across meshes:

```
$ python3 exercise-03-latency-bench.py --summary
MESH        p50(ms)   p99(ms)   proxy-mem/pod   notes
no-mesh       1.8       6.1        -             baseline (direct gRPC)
istio         2.4       9.3       ~55 MB         sidecar (Week 8 baseline)
linkerd       2.1       7.4       ~12 MB         Rust micro-proxy, smaller
cilium        1.9       6.8        -             eBPF L4, no per-pod proxy
```

If your three meshes produce numbers in the *same ballpark shape* as this — Cilium and Linkerd lighter than the Istio sidecar on this workload, all three adding measurable-but-modest overhead — your benchmark is trustworthy. If one mesh shows wildly different numbers, that's a finding to investigate (a misconfiguration, a cold cache), not a result to report. The point of this week is to make "I measured it" the foundation of your recommendation, and to make a *number you can't reproduce* something you discard rather than cite.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **Cilium eBPF datapath** documentation until you can explain how a packet traverses the kernel from socket to socket without a userspace proxy: <https://docs.cilium.io/en/stable/network/ebpf/>.
- Run a **multi-cluster** experiment: connect two Kind clusters with Linkerd's multi-cluster gateway, then with Cilium ClusterMesh, and note how differently each models cross-cluster traffic — a major real-world differentiator.
- Measure the **CPU** cost (not just latency and memory) of each mesh under sustained load with `kubectl top` and a longer `fortio` run. eBPF's efficiency claim is partly a CPU claim; verify it on your hardware.
- Take Linkerd's automatic mTLS and write a `ServerAuthorization`/`AuthorizationPolicy` (Linkerd's authz primitive) for cart→inventory, reaching the same least-privilege posture you built in Istio — and compare how much config it took.

## Up next

Week 9 closes Phase 2's service-mesh arc. Week 10 turns to the *other* half of inter-service communication: **eventing** with Kafka and Redpanda. The mesh carries synchronous request/response; the log carries asynchronous events — and the capstone needs both. Everything you learned across Weeks 7–9 about securing and shaping the synchronous network is what lets Phase 3 reason about the asynchronous one. Push your `mesh-bakeoff` ADR before you start it; the midterm architecture-review essay (end of Week 12) expects exactly this caliber of written architectural argument.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
