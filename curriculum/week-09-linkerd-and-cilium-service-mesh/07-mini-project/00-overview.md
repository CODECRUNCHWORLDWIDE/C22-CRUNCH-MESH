# Mini-Project — `mesh-bakeoff`: Three Meshes, One Topology, One Defensible ADR

> Put the cart topology on all three meshes — Istio (your Week 8 baseline), Linkerd, and Cilium — reach the same security posture (mTLS + least-privilege cart→inventory) on each, benchmark them identically, and write the Architectural Decision Record that recommends one (or none) for a specific 200-engineer org and defends it with your own numbers.

This is the artifact that turns "I've used three meshes" into "I can choose one and defend the choice to a staff panel." After this week, a mesh recommendation from you comes with a benchmark, a trade-off analysis, and a reversal condition — the difference between an opinion and a decision. This is the capstone of Phase 2 and the template for the midterm architecture-review essay.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** The ADR you write here is the model for the **midterm architecture-review essay** (end of Week 12) and rehearsal for the **mock staff system-design interview** (Week 23). The mesh your ADR recommends is the one you'll defend at the **Phase 2 review** and, if you choose it, run in the **capstone**. Build the benchmark cleanly and write the ADR honestly; both are reused.

---

## What you will build

A repo `mesh-bakeoff` with four deliverables:

1. **`deploy/`** — the cart/inventory topology and its manifests, mesh-agnostic, so the *same* workload deploys onto each mesh with only the mesh-specific overlay changing.
2. **`meshes/`** — the per-mesh setup: `istio/` (your Week 8 posture), `linkerd/` (install + inject + the `Server`/`AuthorizationPolicy` for least privilege), `cilium/` (install + the `CiliumNetworkPolicy` with mutual auth + L7). Each reaches the *same* posture: mTLS on, only cart→inventory allowed.
3. **`bench/`** — the reproducible benchmark (Exercise 3's driver) run across all four configurations, with `RESULTS.md` holding the table and the methodology notes (load params, caveats, what's relative vs absolute).
4. **`ADR.md`** — the decision record: context (the 200-engineer org), options (all three + no-mesh), the decision, consequences, and reversal conditions, with your benchmark as the evidence section.

By the end you have a public repo that is, in miniature, exactly the kind of comparative analysis a platform team produces before a mesh adoption — and a written ADR good enough to put in a portfolio.

---

## Why a bakeoff and not "read the comparison blogs"

You could read three vendor comparison pages and pick. Don't — that's how orgs adopt the wrong mesh. A hands-on bakeoff gives you:

- **Numbers from your own workload**, not a vendor's benchmark on a vendor's hardware. "We measured X on our gRPC topology" beats "the docs say Y" in every review.
- **The same posture three ways**, which surfaces the *config-volume* and *operational* differences you can't feel by reading — how much YAML each mTLS-plus-authz setup took, how each diagnoses a problem (`istioctl analyze` vs `linkerd check` vs `cilium status`).
- **The honesty a real decision needs.** Running all three forces you to confront that each one *works* and each one *costs*, which is the whole reason the decision is hard and the ADR is valuable.

The point isn't to crown a winner. It's to be the person in the room who actually ran them and can say what each is like to live with.

---

## Repo layout

```
mesh-bakeoff/
├── README.md
├── ADR.md                       # the decision record (the headline deliverable)
├── deploy/
│   └── cart-inventory.yaml      # the mesh-agnostic topology
├── meshes/
│   ├── istio/                   # Week 8 posture (PeerAuthentication STRICT + AuthorizationPolicy)
│   ├── linkerd/                 # install + inject + Server/AuthorizationPolicy
│   └── cilium/                  # install + CiliumNetworkPolicy (mutual auth + L7)
├── bench/
│   ├── run.sh                   # drives exercise-03 across all four configs
│   ├── bench-results.json       # accumulated rows
│   └── RESULTS.md               # the table + methodology + caveats
└── audit/
    └── verify_posture.sh        # asserts the SAME posture on each mesh (mTLS + cart-only)
```

---

## Deliverable 1 — `deploy/` (the constant)

The cart/inventory workload, identical across all three meshes. The discipline: the *only* thing that changes between meshes is the mesh overlay (injection annotation, network policy CRD). The app, the ports, the load are constant — that's what makes the benchmark a fair comparison. Document the port naming (it matters for L7 in all three) and `appProtocol: grpc`.

> **Why the constant matters.** The single most common way a mesh comparison goes wrong is letting *something other than the mesh* vary between runs — a different image, a different replica count, a different node. The `deploy/` directory is your control: it pins everything that isn't the mesh. If a reviewer can look at it and confirm "the only difference between the Istio run and the Linkerd run is which mesh was installed," your benchmark is credible. If they can't, every number is suspect. Treat the constancy of this layer as a first-class deliverable, not a detail — it's what gives your whole ADR its evidentiary weight.

---

## Deliverable 2 — `meshes/` (the same posture, three ways)

For each mesh, reach the **identical** security posture: mTLS between cart and inventory, and an authorization rule that allows *only* cart→inventory (deny-by-default for everything else). Capture:

- **istio/** — your Week 8 `PeerAuthentication` (STRICT) + `AuthorizationPolicy`.
- **linkerd/** — `linkerd inject` + `Server` + `AuthorizationPolicy` (Linkerd's primitives). Note that mTLS is *already on* without a policy — only the authz needs writing.
- **cilium/** — `CiliumNetworkPolicy` with `authentication.mode: required` + the L7 HTTP rule. Note there's no per-pod proxy.

> **The rule the audit enforces:** all three must reach the *same* posture — mTLS on, only cart→inventory allowed, everything else denied. A mesh that's "set up" but permissive, or that allows more than cart→inventory, fails the audit. The comparison is only fair if the posture is constant.

Record, for each, **how much config it took** and **how you diagnosed it** — these are data for the ADR's operational-complexity axis.

What "the same posture" looks like per mesh, as a checklist you can confirm:

| Capability | Istio | Linkerd | Cilium |
|---|---|---|---|
| mTLS on for cart↔inventory | `PeerAuthentication` STRICT | automatic (no CRD) | `authentication.mode: required` |
| only cart→inventory allowed | `AuthorizationPolicy` | `Server` + `AuthorizationPolicy` | `CiliumNetworkPolicy` |
| everything else denied | deny-by-default policy | default-deny `Server` | `default-deny-ingress` |
| verify command | `istioctl x describe` | `linkerd viz edges` | `hubble observe` |

Filling this table in for your own run — and confirming every cell — is what proves the three meshes are genuinely at the same security bar before you trust their benchmark numbers. If any cell is blank or weaker on one mesh, your comparison is unfair and the audit will (and should) catch it.

---

## Deliverable 3 — `bench/` (the evidence)

Run Exercise 3's driver across no-mesh, Istio, Linkerd, and Cilium with identical load. `RESULTS.md` must contain:

- The comparison table (p50, p99, proxy memory per mesh).
- The **methodology**: load params (QPS, concurrency, duration), warm-up handling, how many runs you averaged.
- The **caveats**: that this is a Kind benchmark (relative, not absolute), the workload shape (gRPC unary at fixed QPS), and any number you discarded as unreproducible.

The benchmark must be **reproducible from `bench/run.sh`** — a reviewer should be able to re-run it. A number you can't reproduce doesn't go in the table.

A checklist to keep the benchmark fair and credible:

- [ ] Identical load (QPS, concurrency, duration, method, payload) on every mesh.
- [ ] A warm-up window skipped on every run.
- [ ] Each mesh measured ≥3 times; the median reported with the spread noted.
- [ ] A fresh cluster per mesh (no two meshes coexisting).
- [ ] Per-pod proxy memory captured for Istio and Linkerd; "N/A" recorded for Cilium L4.
- [ ] Any run with an error rate over ~1% discarded and re-run, not cited.
- [ ] The claim qualified to the workload shape ("gRPC unary at N QPS").

If you can check every box, your `RESULTS.md` will survive the kind of scrutiny the Challenge-1 panel applies — and that survivability is exactly what makes the numbers usable as the evidence section of your ADR. A benchmark that can't pass this checklist is worse than no benchmark, because it lends false confidence to a decision.

---

## Deliverable 4 — `ADR.md` (the headline deliverable)

The decision record for a hypothetical **200-engineer org** (state its specifics: service count, team count, L4-vs-L7 mix, compliance requirements, existing CNI). It must follow the ADR format:

1. **Title & status.**
2. **Context** — the org's situation and the problem a mesh would (or wouldn't) solve. Specific.
3. **Options considered** — Istio, Linkerd, Cilium, *and no mesh*, each with the relevant pros/cons **for this org**, citing your benchmark.
4. **Decision** — the choice, in one sentence, with the primary reasons.
5. **Consequences** — what it commits the org to (ops burden, CNI coupling if Cilium, migration if already meshed), good and bad.
6. **Reversal conditions** — the specific, observable triggers that would make you revisit.

The ADR must **commit to a position** and **state what would change it**. An ADR that hedges ("it depends") fails; an ADR that can't name a reversal condition is dogma.

> **How the grader reads your ADR.** The 25 points for "ADR — analysis" and 20 for "ADR — decision discipline" are looking for specific things, so target them deliberately. Analysis points come from weighing *all four* options (including no-mesh) *for your specific org* and citing your *own* benchmark numbers — not from a generic feature comparison you could have written without running anything. Decision-discipline points come from committing to one choice, stating its consequences honestly (including the bad ones), and naming reversal conditions that are concrete and observable ("if L7 routing spreads past N teams," not "if our needs change"). The fastest way to lose points is to hedge: an ADR that lists pros and cons and then declines to choose has done the easy 80% and skipped the 20% that's actually hard and actually valuable. Commit. The whole point of the artifact — and of the week — is that you can make the call and defend it.

---

## Deliverable (audit) — `verify_posture.sh`

A script that asserts the same posture on whichever mesh is currently installed: mTLS is on for cart→inventory, and a non-cart caller is denied. Exits non-zero if the posture isn't met. This keeps the comparison honest — every mesh in the bakeoff is verified to the same security bar before its benchmark counts.

---

## Rules

- **You may** read all three projects' docs, the lecture notes, and the ADR-format reference.
- **You must not** compare meshes at different postures. All three reach mTLS-on + cart-only-allowed; the audit enforces it. An unfair comparison is worse than no comparison.
- **You must not** report a benchmark number you can't reproduce from `bench/run.sh`.
- **You must not** write an ADR that hedges. Commit to a recommendation (which may be "no mesh") and state reversal conditions.
- **You must not** run two meshes on one cluster — use a fresh Kind cluster per mesh.
- Istio 1.24+, Linkerd 2.16+, Cilium 1.16+, Kind. Everything runs locally.
- The audit must exit non-zero on a posture mismatch so the comparison stays fair.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-09-mesh-bakeoff-<yourhandle>`.
- [ ] The same cart/inventory topology runs on all three meshes, each reaching mTLS-on + only-cart→inventory-allowed (verified by `verify_posture.sh`).
- [ ] `bench/RESULTS.md` has a reproducible four-row table (no-mesh, Istio, Linkerd, Cilium) with p50/p99/memory, plus methodology and caveats.
- [ ] The benchmark reflects the architecture: Istio sidecar heaviest per pod, Linkerd micro-proxy much lighter, Cilium no per-pod proxy.
- [ ] `ADR.md` follows the full format, commits to a recommendation for the stated org (citing your numbers), and names concrete reversal conditions.
- [ ] You recorded, per mesh, the config volume and diagnostic experience (data for the ops-complexity axis).
- [ ] A `README.md` tying it together, with the comparison table and a one-paragraph summary of the decision.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Same posture, three ways** | 20 | mTLS + cart-only on all three, verified; the comparison is genuinely fair. |
| **Benchmark quality** | 25 | Reproducible; identical load; honest caveats; numbers reflect the architecture; unreproducible rows discarded. |
| **ADR — analysis** | 25 | All four options (incl. no-mesh) weighed *for the specific org* with the benchmark cited; the six axes addressed. |
| **ADR — decision discipline** | 20 | Commits to a recommendation; states consequences; names reversal conditions; intellectually honest. |
| **Operational comparison** | 5 | Config-volume and diagnostic experience captured per mesh. |
| **Docs & hygiene** | 5 | Clear README, sensible commits, no secrets/build artifacts, fresh-cluster-per-mesh discipline evident. |

**90+** is portfolio-grade and is the template for your Week 12 midterm essay. **70–89** has a working bakeoff but an ADR that hedges or a benchmark that's hard to reproduce. **Below 70** usually means the meshes were compared at different postures (unfair) or the ADR didn't commit — fix those first; they're the two things this project exists to teach.

---

## Stretch goals

- **Multi-cluster axis.** Add a two-cluster experiment for Linkerd (gateway) and Cilium (ClusterMesh) and write a paragraph on how differently each models cross-cluster traffic — a major real-world differentiator your ADR should at least mention.
- **The counter-ADR.** Write the best case for your *second* choice. If your ADR recommends Linkerd, write the strongest Istio argument. This is the Challenge-1 and Week-23 skill.
- **CPU axis.** Extend the benchmark to CPU under sustained load. eBPF's efficiency claim is partly a CPU story; put a number on it.
- **No-mesh baseline as a real option.** For the 200-engineer org, seriously cost out the gateway-plus-library alternative (Week 7) and argue whether a mesh is justified *at all* — the most senior ADRs sometimes recommend "not yet."

---

## How this connects to the rest of C22

- **Weeks 7–8** built the gateway and the Istio mesh; this week's bakeoff puts them in context against the alternatives, so you know what you chose and what you didn't.
- **Week 10 (eventing)** turns from the synchronous mesh to the asynchronous log (Kafka/Redpanda) — the other half of inter-service communication the capstone needs.
- **Week 12 (midterm)** is a written architecture review of a public distributed system — exactly the ADR muscle you build here.
- **Week 23 (mock staff interview)** is this defense, live, with an external reviewer — and the Challenge-1 objection drill is its direct rehearsal.
- **Phase 4 (capstone)** runs whichever mesh your ADR recommends as the real east-west layer of the Polyglot Marketplace Backbone, behind the Week 7 `cart-edge` gateway.

This mini-project closes Phase 2's service-mesh arc. You arrived in Week 7 with one service and a network you treated as a detail; you leave with a gateway, three meshes run and measured, and the judgment to choose among them — or to choose none — and defend it. That judgment is the deliverable; the repo is just its evidence.

Keep this repo. The midterm essay reuses its ADR as a model, the Week 23 interview reuses its defense, and the capstone reuses its recommended mesh. Few artifacts in this course compound forward as directly.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
