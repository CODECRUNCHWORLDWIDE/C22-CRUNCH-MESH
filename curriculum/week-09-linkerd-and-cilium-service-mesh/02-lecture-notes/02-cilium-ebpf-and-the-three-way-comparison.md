# Lecture 2 — Cilium, eBPF, and the Three-Way Comparison

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain Cilium's eBPF-based, sidecar-less mesh and what eBPF buys and constrains; compare Istio, Linkerd, and Cilium on the axes that drive adoption; benchmark them honestly; and write an ADR that recommends one for a specific org and defends it.

Lecture 1 gave you the minimalist mesh. This lecture gives you the structuralist one — Cilium, which doesn't make the sidecar smaller (Linkerd) or optional-per-pod (Istio ambient); it dissolves the per-pod proxy into the *kernel*. Then we put all three side by side and turn the comparison into a decision. Three parts: (1) Cilium and eBPF, (2) the empirical comparison, (3) the ADR.

The sentence to carry through:

> **Istio asks "how powerful a proxy can we put next to every pod?" Linkerd asks "how small a proxy?" Cilium asks "do we need a per-pod proxy at all?" — and answers no, for L4, by moving the work into the kernel.**

---

## Part 1 — Cilium and eBPF

### 1.1 What eBPF is, in one paragraph

**eBPF** (extended Berkeley Packet Filter) lets you load small, sandboxed programs into the Linux kernel that run in response to events — a packet arriving, a socket connecting, a syscall firing — *without* writing a kernel module and *without* the program being able to crash the kernel (a verifier checks it before it runs). The payoff for networking: you can do load balancing, network policy enforcement, and connection handling **in the kernel datapath**, where the packets already are, instead of bouncing them up to a userspace proxy and back down. No context switch to userspace, no extra process in the path. That's the efficiency claim, and it's a real one.

### 1.2 Cilium's mesh: L4 in the kernel, L7 in a per-node Envoy

Cilium is first a **CNI** (the thing that wires up pod networking) and a **network-policy** engine, both built on eBPF. Its **service mesh** extends that:

- **L4 + mTLS in the kernel.** Service load balancing, network policy, and **mutual authentication** are handled by eBPF programs in the kernel datapath. There is **no per-pod proxy** for this path. A request from cart to inventory is load-balanced and (with mutual auth enabled) authenticated by kernel code, not by an Envoy sidecar. This is the headline: the L4 mesh costs you *no per-pod userspace proxy at all*.
- **L7 in a per-node embedded Envoy.** When you need L7 features — HTTP-aware policy, path-based routing, header matching — Cilium routes that traffic through a **per-node embedded Envoy** (one Envoy per node, not per pod). So L7 has a proxy, but it's amortized across every pod on the node, not duplicated per pod.

```
   Cilium: L4 is kernel (free of per-pod proxy); L7 is a per-NODE Envoy
   ┌──────────────── node ────────────────┐
   │  pod A          pod B                  │
   │    │              │                    │
   │  ┌─▼──────────────▼─┐  L4 + mTLS via   │
   │  │   eBPF datapath   │  kernel programs │  <-- no per-pod proxy
   │  └─────────┬─────────┘                  │
   │            │ (only if L7 policy/routing)│
   │     per-node embedded Envoy (L7)        │
   └─────────────────────────────────────────┘
```

### 1.3 Mutual authentication without a per-pod proxy

The interesting question Cilium has to answer: if there's no sidecar, *what* presents the mTLS certificate? Cilium's mutual-authentication feature uses workload identities (SPIFFE-based) and establishes authenticated, encrypted connections at the kernel/datapath level, with the identity machinery managed by Cilium's agents (one per node, the same DaemonSet that runs the CNI). The net effect is the same security property as Istio/Linkerd — each side cryptographically knows the other's identity and the traffic is encrypted — reached without a proxy in every pod.

The trade-offs to be honest about:

- **It's tied to your CNI.** Cilium-as-mesh means Cilium-as-CNI. You're not layering a mesh *onto* whatever networking you have; you're adopting Cilium for both. For a greenfield cluster that's clean; for a cluster already on another CNI it's a migration, not an add-on.
- **The L7 story is younger and node-scoped.** The per-node Envoy is real and capable, but Cilium's L7 mesh feature set and ecosystem are less mature than Istio's years of Envoy-everywhere. If your mesh is *mostly* L7-heavy, you're leaning on the part of Cilium that's newest.
- **eBPF needs a recent kernel.** The efficiency comes from kernel features; very old kernels limit what's available. On a modern cluster this is a non-issue; on legacy infrastructure it's a constraint to check.

> **The structuralist payoff:** for a mesh whose dominant need is "L4 service connectivity, network policy, and mTLS, cheaply, at scale," Cilium's kernel datapath is the most efficient of the three — no per-pod proxy memory, no extra userspace hop on the L4 path. For a mesh that's L7-rich everywhere, you're back to paying for Envoy (per-node, not per-pod, but still), and Istio's maturity there is a real advantage.

### 1.3.5 The CNI-and-mesh convergence

The deepest thing to understand about Cilium is *conceptual*, not technical: it collapses two layers that the other meshes keep separate. Istio and Linkerd are meshes that sit *on top of* whatever CNI you run (Calico, the cloud provider's CNI, or even Cilium). Cilium-as-mesh erases that boundary — the same eBPF layer that wires up pod networking (the CNI job) also does service load balancing, network policy, and mTLS (the mesh job). One layer, one mental model, one set of tooling.

This convergence is a genuine architectural argument, not just a packaging choice:

- **No duplicated identity/policy planes.** In an Istio-on-some-CNI setup, you have network policy at the CNI layer *and* authorization policy at the mesh layer — two systems, two places to express "who can talk to whom," two chances for them to disagree. Cilium expresses both in one `CiliumNetworkPolicy` model (L3/L4 in the kernel, L7 via the embedded Envoy), so there's one answer to "what's allowed."
- **The datapath is unified.** A packet isn't handed between a CNI's networking and a mesh's proxy; it flows through one eBPF datapath that does everything. That's where the efficiency comes from, and it's also why there's less to go wrong in the hand-off.
- **The cost is the coupling.** The flip side, which the trade-offs above name: you can't adopt Cilium's mesh *without* adopting Cilium's CNI. The convergence that's elegant on a greenfield cluster is a CNI migration on an existing one. There is no "just the mesh part" of Cilium — the unification cuts both ways.

For your ADR, the framing is: Cilium asks you to think of your mesh as *part of your network*, not a layer above it. Orgs that already lean into eBPF and want one unified networking-and-security layer find this compelling; orgs with an existing CNI investment and a "mesh is a separate concern" mental model find the coupling a cost. Neither view is wrong — they're different bets about where the networking/mesh boundary should be, and naming which bet fits your org is the architectural decision.

A concrete way to feel the convergence: in a Cilium cluster, the *same* `CiliumNetworkPolicy` resource expresses an L3 rule ("pods labeled cart may reach pods labeled inventory"), an L4 rule ("on TCP port 50051"), an L7 rule ("only POST to these gRPC method paths"), and an authentication requirement ("with mutual auth"), all in one document evaluated by one datapath. The Istio equivalent of that same intent is spread across a `NetworkPolicy` (or the CNI's policy), a `PeerAuthentication`, and an `AuthorizationPolicy` — three resources, two systems, evaluated in two places. Cilium's "one resource, one datapath" isn't merely tidier; it removes the class of bug where the CNI policy and the mesh policy *disagree* and you spend an afternoon figuring out which layer dropped the packet. That said, the single-resource model also means the `CiliumNetworkPolicy` carries more responsibility, and getting it wrong fails more things at once — power and blast radius are the same coin here, as everywhere.

### 1.4 The eBPF datapath, narrated

To make eBPF concrete rather than buzzword, walk a single `cart`→`inventory` packet through Cilium's L4 path:

1. `cart`'s application writes bytes to a socket destined for the `inventory` Service ClusterIP. There is **no sidecar** intercepting this — the app talks to the kernel directly.
2. An eBPF program attached at the socket/connect hook recognizes the Service IP, looks up the backend endpoints in an eBPF map (a kernel data structure Cilium keeps in sync with Kubernetes Endpoints), and performs the **load-balancing decision in the kernel** — picking a healthy `inventory` pod. This is the work `kube-proxy` used to do with iptables, now done in eBPF (which is why you can run Cilium with `kubeProxyReplacement=true`).
3. Cilium's eBPF programs enforce **network policy** at this point: is `cart` allowed to reach `inventory`? The identity-based policy (your `CiliumNetworkPolicy`) is evaluated in the kernel against the source and destination *identities* (not just IPs).
4. With mutual authentication enabled, the connection is established as an **authenticated, encrypted** channel between the two nodes' Cilium agents — the identity machinery (SPIFFE-based) confirms each side, again without a per-pod proxy.
5. If — and only if — an **L7 policy** applies (an HTTP method/path rule), the traffic is steered to the **per-node embedded Envoy**, which enforces the L7 rule. Otherwise it never touches userspace.

The thing to internalize: for the common L4 case, the packet's whole journey — load balancing, policy, identity — happens **in the kernel**, where the packet already is. There's no copy up to a userspace proxy and back. That elision is the entire efficiency argument, and it's why the proxy-memory column for Cilium's L4 path reads "none."

```bash
# The eBPF programs and maps are inspectable. The Cilium agent shows them:
kubectl exec -n kube-system ds/cilium -- cilium bpf lb list      # the LB map (kernel load balancing)
kubectl exec -n kube-system ds/cilium -- cilium endpoint list    # identities + policy state per endpoint
hubble observe --to-label app=inventory                          # the flows, observed via eBPF
```

> **What this constrains.** The kernel datapath needs a kernel that supports the eBPF features Cilium uses — a non-issue on modern distros, a real check on legacy ones. And because policy and identity live in Cilium's model, you're committing to Cilium's way of thinking about networking, not layering a mesh onto an existing mental model. That coupling is the price of the efficiency.

---

## Part 2 — The empirical comparison

### 2.1 What to measure and why

You will benchmark the *same* `cart`→`inventory` gRPC workload on all three meshes plus a no-mesh baseline, measuring:

- **p50 and p99 latency** — the headline cost. p50 tells you the typical tax; **p99 tells you the tail**, which is what users actually feel and what a sidecar's extra hops most affect.
- **Proxy memory** — per-pod for Istio (sidecar) and Linkerd (micro-proxy); per-node for Cilium (embedded Envoy only when L7 is used; otherwise near-zero proxy memory). This is where the architectural differences become a number.
- **(Stretch) CPU** — under sustained load, because eBPF's efficiency is partly a CPU story.

### 2.2 The honesty a benchmark requires

A local Kind benchmark is a **relative** instrument, not an absolute one. Internalize three caveats and put them in your writeup:

1. **It shows relative overhead, not production numbers.** Your laptop's p99 is not a datacenter's p99. What's trustworthy is the *ordering and rough ratio* — "Cilium's L4 path added less p99 than the Istio sidecar on this workload" — not the absolute milliseconds.
2. **Warm-up and noise matter.** Run long enough (30–60 s), discard the warm-up, and run each mesh more than once. A single cold run is noise. If a number isn't reproducible, discard it — don't cite it.
3. **You're measuring one workload shape.** gRPC unary at modest QPS stresses a mesh differently than large payloads, streaming, or very high QPS. Your conclusion is "for this workload"; say so. The skill is qualifying the claim, not pretending the benchmark is universal.

### 2.3 The shape you'll find (and how to read it)

Run honestly and you'll typically see something like:

```
MESH        p50(ms)   p99(ms)   proxy-mem/pod   notes
no-mesh       1.8       6.1        -             direct gRPC baseline
istio         2.4       9.3       ~55 MB         sidecar — most features, most cost
linkerd       2.1       7.4       ~12 MB         tiny Rust micro-proxy
cilium        1.9       6.8        -             eBPF L4, no per-pod proxy
```

How to interpret, not just report:

- **All three add measurable overhead** — there is no free mesh. The question is whether the overhead is worth what the mesh buys (uniform mTLS, telemetry, policy you'd otherwise build by hand).
- **The proxy-memory column is the architecture made visible.** Istio's general-purpose Envoy is the heaviest per pod; Linkerd's purpose-built micro-proxy is a fraction of it; Cilium's L4 path has *no* per-pod proxy at all. At 1000 pods, that column is a multi-gigabyte difference.
- **The p99 (tail) differences are the user-facing ones.** A sidecar's two extra hops show up most at the tail. Cilium's kernel L4 path and Linkerd's tight proxy tend to a tighter tail than a full Envoy sidecar — *on an L4-ish workload*. Add heavy L7 and the picture shifts.

The number alone doesn't decide anything. "Cilium was fastest on this bench" does **not** mean "adopt Cilium" — because if your org needs Istio's L7 richness or can't change its CNI, the latency win is irrelevant. The benchmark is *one* axis. The ADR weighs all of them.

### 2.4 Observability: Hubble vs Kiali vs linkerd viz

Each mesh's observability layer reflects its architecture, and it's a real day-to-day differentiator the benchmark doesn't capture:

- **Cilium → Hubble.** Because Cilium sees every packet in the eBPF datapath, **Hubble** can show you *flows* — every connection, allowed or dropped, with source/destination identity and the L7 verb when applicable — at the network layer, with very low overhead (it's reading data the kernel already has). `hubble observe --to-label app=inventory` streams exactly which flows reached inventory and which were dropped by policy. For debugging "why can't A talk to B," Hubble's DROPPED lines name the policy that blocked it.
- **Istio → Kiali.** A rich service-graph UI built on the sidecars' telemetry, with config validation baked in. Powerful, but it's a separate stack to run.
- **Linkerd → `linkerd viz`.** Golden signals and edges from the CLI or a light dashboard, the simplest to stand up.

```bash
# Cilium: see allowed vs dropped flows, with the deciding policy:
hubble observe --to-label app=inventory --verdict DROPPED
# frontend -> inventory  DROPPED (Policy denied)   <-- names WHY it was dropped

# the same question on Linkerd:
linkerd viz edges deploy -n shop          # who talks to whom + mTLS status
```

The point for your comparison: "how do I see what's happening" has a different answer and a different cost in each mesh, and an org that lives in its observability tooling should weight this. Hubble's flow-level visibility is a genuine Cilium strength that the latency benchmark won't show you.

### 2.5 The multi-cluster axis

The benchmark is single-cluster, but real orgs eventually go multi-cluster, and the three meshes differ sharply here — enough that it can flip a decision:

- **Cilium ClusterMesh** is eBPF-native: it connects clusters' eBPF datapaths so a Service in cluster A can transparently reach endpoints in cluster B, with policy and identity spanning both. Because it's built into the CNI layer, it's one of Cilium's strongest features — cross-cluster service discovery and policy feel like one big cluster.
- **Linkerd multi-cluster** uses a **gateway** model: traffic to a remote cluster goes through a mirror gateway. Competent and simple, but every cross-cluster hop traverses the gateway, which is a different performance and topology shape than Cilium's flat model.
- **Istio multi-cluster** supports several topologies (shared control plane, replicated control plane, multi-primary) — the most *flexible*, also the most to operate.

If an org is single-cluster today but multi-cluster on its roadmap, this axis belongs in the ADR even though your benchmark can't measure it — and it's the kind of forward-looking consideration that separates a real decision record from a snapshot.

---

## Part 3 — The decision axes and the ADR

### 3.1 The six axes that actually drive a mesh choice

Real orgs don't choose a mesh on latency alone. They weigh:

| Axis | Istio | Linkerd | Cilium |
|---|---|---|---|
| **Cost (latency/memory)** | Highest (sidecar; ambient lowers it) | Low (tiny sidecar) | Lowest for L4 (kernel, no per-pod proxy) |
| **Operational complexity** | Highest (rich, many knobs) | Lowest (few parts, `linkerd check`) | Medium-high (it's also your CNI; eBPF mental model) |
| **L7 feature depth** | Deepest (full Envoy ecosystem) | Moderate (the essentials) | Growing (per-node Envoy, younger) |
| **mTLS model** | istiod CA + Envoy; available-not-enforced by default | Automatic, on-by-default | eBPF/SPIFFE, no per-pod proxy |
| **Multi-cluster** | Mature, several topologies | Gateway model, competent | ClusterMesh, eBPF-native, strong |
| **Maturity/ecosystem** | Largest ecosystem | Very mature, focused | Mature as CNI, mesh features newer |

The art is *weighting* these for a specific org. A latency-sensitive, L4-dominant, greenfield platform team weights cost and Cilium's kernel path heavily. A team that wants a mesh to disappear into the background and never page them weights Linkerd's simplicity. A team with rich L7 needs, an existing CNI, and the staff to operate complexity weights Istio's depth. Same three meshes, different weights, different right answer.

### 3.2 When the right answer is no mesh

The most senior thing you can write in a mesh ADR is sometimes "don't." A mesh — *any* of these three — is only justified when the value of uniform east-west mTLS, telemetry, and policy *applied without per-team effort* exceeds the cost of running a mesh. For a 6-service, 2-team shop (the Week 7 Org A), that value is small: you can get mTLS with a shared library and telemetry with OpenTelemetry, and a mesh's control plane is a new thing to operate for little gain. The Week 7 gateway-plus-library approach is the right answer, and the ADR should say so plainly. Adopting a mesh because "everyone has one" is cargo-culting, and naming that temptation is part of a good ADR.

The useful skill is naming the **crossover** — the point at which "no mesh" stops being the right answer. It's not a single number, but it has clear drivers:

- **Team count.** At 2–3 teams, a shared mTLS library is auditable by hand — one person can verify every service uses it. Past ~10–15 teams, no single person can verify every hop's encryption, and the *uniformity* a mesh provides (encryption applied identically, by the platform, not by each team) becomes worth its operating cost. This is the most common crossover driver.
- **A compliance mandate.** "Prove all internal traffic is encrypted" is far easier to demonstrate with a mesh enforcing it uniformly than with N teams each (claimed to be) using a library correctly. A hard mandate can justify a mesh well below the team-count crossover.
- **Polyglot sprawl.** A shared mTLS library has to exist *in every language* your services use. At one or two languages, that's maintainable; at five, you're maintaining five libraries and the mesh's "language-agnostic, in the data plane" model wins.
- **Operational maturity to run a mesh.** Below a certain platform-team size, you *can't* operate a mesh well — and a badly-operated mesh (stale certs, an un-upgraded control plane) is worse than a shared library. This can push the crossover *up*: a small team might be better off without a mesh even past the point where one would otherwise help.

So the no-mesh case isn't "small = no mesh" — it's "the mesh's value (uniformity, especially for mTLS and telemetry) hasn't yet exceeded its operating cost *for this org's team count, language spread, compliance posture, and platform maturity*." Stating *where* that crossover is for the specific org — "we'd reach for a mesh at ~15 teams or the moment we take on a SOC 2 encryption requirement" — is what turns "no mesh, for now" from a punt into a defensible, dated decision with a trigger. That's the most cost-effective ADR you can write, and writing it well is as much a skill as choosing among the three meshes.

### 3.3 The ADR format

An Architectural Decision Record is a short, durable document with a fixed shape:

1. **Title** — "ADR-007: Service mesh selection for the platform."
2. **Status** — proposed / accepted / superseded.
3. **Context** — the situation forcing the decision: scale, team count, security requirements, existing infra (CNI!), the problem the mesh would solve. *Specific*, not generic.
4. **Options considered** — Istio, Linkerd, Cilium, and "no mesh." For each, the relevant pros/cons *for this org*, ideally with your benchmark numbers.
5. **Decision** — the choice, in one clear sentence, with the *primary* reasons.
6. **Consequences** — what this commits you to (operational burden, the CNI coupling if Cilium, the migration if you're already meshed), good and bad.
7. **Reversal conditions** — what would make you revisit. "If our L7 routing needs grow past X, we'd reconsider Istio." This is the line that separates a decision from a dogma.

The ADR is the staff-engineer artifact. It turns "I like Linkerd" into "we chose Linkerd for this org because A, B, C; here's what it costs us; here's when we'd change our mind." The homework has you write exactly this for a 200-engineer org, and the challenge has you *defend* it against objections — because in a real design review, the ADR is the start of the conversation, not the end.

> **The discipline:** an ADR that doesn't commit to a choice is useless, and an ADR that can't name what would change its mind is dogma. A good one does both — it picks, it justifies *for the specific org*, and it states its own reversal conditions. That intellectual honesty — "here's my answer AND here's what would make it wrong" — is the staff-engineer move.

### 3.4 A worked ADR excerpt

To make the format concrete, here is the spine of a real-shaped ADR for a hypothetical org — the kind you'll write in the homework. Notice how each section is *specific* and how the benchmark feeds the decision:

> **ADR-007: Service mesh selection for the Platform group**
> **Status:** Proposed.
> **Context.** We run ~120 services across 25 teams in a single EKS cluster, currently on the AWS VPC CNI, no mesh today. A SOC 2 commitment requires encryption of all internal service-to-service traffic by Q3. Implementing mTLS per-service across 25 teams is infeasible to verify; we need it applied uniformly by the platform. Traffic is ~80% L4-shaped gRPC; L7 routing needs are modest (a handful of canary deploys). Our platform team is 6 engineers.
> **Options considered.**
> - *No mesh + shared mTLS library.* Rejected: cannot prove uniform encryption across 25 teams for the audit; every team is a chance to skip it.
> - *Istio (sidecar).* Meets the requirement; deepest L7. But our benchmark shows ~55 MiB/pod proxy memory — at our ~900-pod count, ~50 GiB of pure proxy memory — and the operational surface is heavy for a 6-person platform team.
> - *Istio (ambient).* Lowers the per-pod cost substantially (L4 via ztunnel); strong fit given our L4-dominant traffic; adds waypoints only where the few L7 canaries need them.
> - *Linkerd.* Lightest sidecar (~12 MiB/pod in our bench), simplest to operate, automatic mTLS. Meets the requirement cleanly; L7 is modest but so are our needs.
> - *Cilium.* Lowest L4 cost (no per-pod proxy), but adopting it means migrating off the VPC CNI — a large, risky change we don't want coupled to a compliance deadline.
> **Decision.** Adopt **Linkerd**, primarily for the lowest operational burden on a small platform team, automatic-mTLS that satisfies the audit with minimal config, and a per-pod cost our benchmark shows is acceptable. (Istio ambient is the close runner-up.)
> **Consequences.** We accept a still-per-pod (if tiny) proxy and Linkerd's narrower L7. We commit to rotating the Linkerd issuer cert and alerting on `linkerd check`. We do *not* take on a CNI migration.
> **Reversal conditions.** If L7-routing needs spread past ~5 teams, or multi-cluster becomes a hard requirement, we revisit Istio (ambient) or Cilium ClusterMesh.

Read how the **compliance requirement** is the spine (it justifies *a* mesh), the **benchmark** discriminates among the options (memory at scale), the **CNI constraint** demotes Cilium for *this* org, and the **team size** tips it toward simplicity. A different org — say, one already on Cilium's CNI, with heavy L7 needs and a 30-person platform team — would weight the same axes differently and land on a different mesh. That's not the ADR being wishy-washy; that's the ADR being *correct for its context*. Your job in the homework is to produce one this specific and this committed.

### 3.5 The migration cost: choosing a mesh is choosing a migration

An ADR that picks a mesh and stops there has skipped the hardest part: *getting from here to there*. Each mesh implies a different migration shape, and that shape is often the deciding consequence.

- **Onto Istio (sidecar).** Label namespaces incrementally, ride **PERMISSIVE** mTLS while clients are mixed (meshed and un-meshed coexist), mesh everything, *then* flip STRICT (Week 8 §3.2). The permissive bridge is what makes this safe — you're never forced to cut over a whole namespace at once. The cost is the per-pod sidecar tax landing on every workload you mesh.
- **Onto Istio (ambient).** Even gentler at the L4 floor — labeling a namespace `ambient` adds mTLS with no per-pod restart (no sidecar to inject), so the disruption is minimal. You add waypoints only where L7 policy is needed, which can be a later, smaller step.
- **Onto Linkerd.** Inject namespace by namespace; mTLS is automatic between meshed pods, so the "meshed talks plaintext to un-meshed" window is handled by Linkerd's permissive-ish default during rollout. The migration is mostly "annotate and re-deploy," which is why teams cite it as low-friction.
- **Onto Cilium (as mesh).** This is the big one: because Cilium *is* the CNI, adopting it as a mesh on an existing cluster means **replacing the CNI** — a cluster-wide networking change, often done by draining and rebuilding nodes or a careful CNI migration. On a *new* cluster it's clean; on an *existing* one it's a project with its own risk and its own change window. This is why the worked ADR above demoted Cilium for an org on the VPC CNI with a compliance deadline: you don't want a CNI migration coupled to an audit date.

The honest framing for the ADR's consequences section: **"adopt mesh X" is shorthand for "run migration Y."** Naming the migration — incremental sidecar injection vs an ambient relabel vs a CNI replacement — is what turns the decision from a logo choice into an executable plan a platform team can schedule. The mesh you can migrate to safely this quarter may beat the mesh that's marginally better on paper but requires a CNI swap you can't safely do until next year.

### 3.6 Putting it all together: the decision, narrated

When you sit down to choose, the order of operations that produces a defensible ADR:

1. **State the context precisely** — scale, teams, traffic shape (L4 vs L7), the forcing requirement (compliance? telemetry? canary?), and the existing infra (CNI above all).
2. **Ask "mesh at all?"** first. If a shared library + OTel covers the requirement at this scale, the answer may be no mesh, and that's the most cost-effective ADR you can write.
3. **If a mesh, run the benchmark** — get *your* numbers on *your* workload, because the cost axis is where general advice fails specific orgs.
4. **Weight the six axes** for this org. Let the forcing requirement and the hard constraints (CNI, team size, multi-cluster roadmap) do most of the discriminating.
5. **Name the migration** the choice implies, and fold its cost into the decision.
6. **Commit, and state reversal conditions.** The decision is a snapshot of a context; say what context-change would flip it.

That sequence is the entire intellectual content of the week, compressed. Everything before it — installing three meshes, measuring them, understanding sidecar vs eBPF — exists so that this decision is grounded in evidence and experience rather than preference and marketing.

### 3.7 Benchmark pitfalls that invalidate a comparison

Because your ADR leans on the benchmark, it's worth cataloguing the mistakes that silently make a comparison *unfair* — each of which a reviewer will (rightly) use to dismiss your numbers:

- **Different load between meshes.** If you ran Istio at 200 QPS and Linkerd at 150 because "the cluster felt slow," the comparison is meaningless. Same QPS, concurrency, duration, payload, and method on every mesh — full stop.
- **No warm-up skip.** The first seconds include connection setup and cold caches; a p99 measured across the warm-up is dominated by startup, not steady-state. Skip a warm-up window (the Exercise-3 driver does).
- **One run per mesh.** A single run is a sample of one. Run each mesh ≥3 times and report the median (and note the spread). A number that doesn't reproduce within a stated tolerance gets re-run or discarded.
- **Meshes coexisting.** Two meshes on one cluster fight over the data path and corrupt both readings. Fresh cluster per mesh.
- **Comparing absolute ms across hardware.** Your laptop's numbers are not a datacenter's. The trustworthy output is the *ordering and ratio* (Cilium lighter than the Istio sidecar by roughly X), not "p99 is 9.3 ms" as a universal fact.
- **Ignoring the workload shape.** gRPC unary at modest QPS is one shape. Large payloads, streaming, or very high QPS can reorder the meshes. Qualify every claim to the workload you measured.

The meta-point: a benchmark's *credibility* comes from its methodology, not its numbers. An ADR that says "we measured carefully, here's the method, here are the caveats, here's the ordering" survives scrutiny; one that drops a table of milliseconds with no methodology gets thrown out the moment someone asks "how did you measure that." In the homework you'll deliberately produce a *bad* run and identify why it's bad — because recognizing an untrustworthy number is as important as producing a trustworthy one.

### 3.8 Where the three meshes are heading

A 2026-current note for your ADR's forward-looking sections, because you're choosing a mesh you'll live with for years:

- **Istio** is investing heavily in **ambient** — the sidecar-less mode is where its "lower the cost" energy is going, and it's the answer to the years of "the sidecar tax is too high" criticism. An Istio adoption today should seriously weight ambient, not just classic sidecars.
- **Linkerd** continues to bet on **simplicity and the Rust proxy**, adopting upstream standards (Gateway API) rather than growing its own surface. Its trajectory is "stay small and excellent at the core mesh job," not "match Istio feature-for-feature."
- **Cilium** is riding the broader **eBPF wave** — its mesh features mature alongside its dominant position as a CNI, and ClusterMesh keeps it strong for multi-cluster. Its trajectory is "the network and the mesh converge into one eBPF layer."

The honest takeaway: all three are healthy, well-funded CNCF projects going in coherent (and different) directions. You are not picking a winner that will orphan the losers; you're picking the philosophy that fits your org. That framing — three good answers to the same question, choose the one whose trade-offs match you — is the mature way to hold the whole comparison, and it's the note your ADR should close on.

### 3.9 The three philosophies, one last time

If you take nothing else from this week, take the shape of the three bets, because it's the lens that makes every future mesh conversation legible:

- **Istio bets on power.** Whatever you might need, Istio can do — at the cost of the most surface to learn and operate. It's converging on ambient to address the cost, but its identity remains "the mesh that does everything." The org that fits: large, with the platform staff to wield the power and the L7 needs to justify it.
- **Linkerd bets on simplicity.** Do the core mesh job — mTLS, golden signals, retries, simple traffic shifting — superbly, with the smallest proxy and the fewest concepts, and decline to do the rest. The org that fits: one that wants the mesh's benefits with the least operational drama, whose needs sit inside Linkerd's deliberate opinions (a large population).
- **Cilium bets on the kernel.** Dissolve the mesh into the network via eBPF, so L4 and mTLS cost no per-pod proxy and the CNI and mesh become one layer. The org that fits: one that's leaning into eBPF, wants maximum L4 efficiency at scale, and can adopt (or already runs) Cilium as its CNI.

Notice these aren't points on a single "better–worse" line — they're *different answers to a genuinely open question* about where a mesh's complexity should live (in a powerful proxy, in a tiny one, or in the kernel). That's why the decision is hard and why it's worth a real ADR rather than a default. The engineer who can hold all three philosophies in mind, weigh them against a specific org, and commit — *that* engineer is the one a staff interview is looking for, and this week's bakeoff-and-ADR is the rehearsal. Everything you did — three installs, one benchmark, one decision record — exists to make you that engineer.

### 3.10 A quick-reference decision flow

For the homework and the challenge, a compressed flow you can apply to any org — walk it top to bottom and stop at the first decisive node:

```
Does the org need uniform east-west mTLS / telemetry / policy
that a shared library can't verify across its teams?
│
├─ No  → NO MESH. Use the Week 7 gateway + a shared mTLS library + OTel.
│        (Revisit at ~15 teams or a compliance mandate.)
│
└─ Yes ↓

Is the org already on Cilium's CNI, or willing to migrate to it?
│
├─ Yes, and traffic is L4-dominant / efficiency matters at scale
│        → CILIUM. Kernel L4 + mTLS, no per-pod proxy; ClusterMesh for multi-cluster.
│
└─ No (existing non-Cilium CNI, don't want a CNI migration) ↓

Does the org need rich L7 (heavy routing/policy/filters) on most hops,
AND have the platform staff to operate a large mesh?
│
├─ Yes → ISTIO (strongly consider ambient for the L4 floor + waypoints for L7).
│
└─ No (modest L7, small platform team, wants least operational drama)
         → LINKERD. Tiny proxy, automatic mTLS, simplest to operate.
```

This is a *starting* heuristic, not a verdict — your benchmark numbers and the org's specific constraints (multi-cluster roadmap, compliance deadline, kernel version) refine it. But it captures the dominant drivers: the CNI question gates Cilium, the L7-depth-and-staffing question separates Istio from Linkerd, and the "mesh at all?" question sits above everything. Run an org through this flow, then *defend* the landing spot with your numbers — that's the homework ADR in two steps.

---

## 4. Recap

You should now be able to:

- Explain Cilium's eBPF mesh: L4 + mTLS in the kernel with no per-pod proxy, L7 via a per-node embedded Envoy, and what eBPF buys (kernel-datapath efficiency) and constrains (CNI coupling, younger L7, kernel requirements).
- Benchmark Istio, Linkerd, and Cilium on an identical workload and interpret the numbers honestly — relative not absolute, qualified to the workload, reproducible or discarded.
- Compare the three on the six adoption axes (cost, ops complexity, L7 depth, mTLS model, multi-cluster, maturity) and weight them for a specific org.
- Recognize when no mesh is the right answer (small/simple systems; the gateway-plus-library approach).
- Write an ADR with context, options, decision, consequences, and reversal conditions — and defend it.

Next: the exercises put all three meshes on your cart topology and produce the numbers your ADR is built on. Continue to [the exercises](../03-exercises/00-overview.md).

---

## References

- *Cilium — Service Mesh overview*: <https://docs.cilium.io/en/stable/network/servicemesh/>
- *Cilium — Mutual authentication*: <https://docs.cilium.io/en/stable/network/servicemesh/mutual-authentication/mutual-authentication/>
- *Cilium — eBPF datapath*: <https://docs.cilium.io/en/stable/network/ebpf/>
- *What is eBPF?*: <https://ebpf.io/what-is-ebpf/>
- *ADR format (Michael Nygard)*: <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>
- *Istio ambient (the third data-plane model)*: <https://istio.io/latest/docs/ambient/overview/>
