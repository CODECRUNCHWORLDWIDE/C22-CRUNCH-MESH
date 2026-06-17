# Week 9 Homework

Six problems that revisit the week's topics and force the comparative-architecture literacy into your fingers. The full set should take about **5 hours**. Work in your Week 9 Git repository (the same workspace as the exercises and the `mesh-bakeoff` mini-project) so every problem produces at least one commit you can point to at the Phase 2 architecture review in Week 12.

The headline deliverable is **Problem 4 — the 200-engineer-org mesh ADR**, the artifact called out in the syllabus skills ("writing an architectural decision record (ADR) that defends a position"). Treat it as the document a CTO reads before funding a mesh adoption.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

Have **Linkerd** and **Cilium** installable, your **Week 8 Istio baseline** in hand, and the **`cart`/`inventory`** topology deployable. Problems 1, 2, 3, and 5 run against live meshes (fresh cluster per mesh).

---

## Problem 1 — The three-way comparison table

**Problem statement.** Build the definitive comparison table for your own bakeoff. In `notes/week-09/comparison.md`, produce a table with the three meshes as columns and these rows: p50 overhead, p99 overhead, per-pod (or per-node) proxy memory, config volume to reach mTLS+authz (lines of YAML), the diagnostic command you used, mTLS-default behavior, and one-line "best fit." Fill it from your *own* measurements and experience, not from blogs.

**Acceptance criteria.**

- `notes/week-09/comparison.md` has a complete table, all three meshes, every row filled from your own runs.
- The latency rows are your measured numbers (against your no-mesh baseline), and you note they're relative-not-absolute.
- The config-volume row is an actual line count of the mTLS+authz YAML each took.
- Committed.

**Hint.** The config-volume row is more revealing than people expect: Linkerd's automatic mTLS means you write *zero* lines for encryption (only authz), while Istio needs a `PeerAuthentication` plus the `AuthorizationPolicy`. Cilium folds both into the `CiliumNetworkPolicy`. Count honestly.

**Estimated time.** 45 minutes.

---

## Problem 2 — Reproduce the benchmark and prove it's stable

**Problem statement.** A benchmark you can't reproduce is worthless. Run your Exercise-3 benchmark on **one** mesh (your choice) **three times**, and show the p50/p99 are stable across runs (within a tolerance you state). Then deliberately produce an *unstable* run (e.g., benchmark during pod startup, or with too-short a duration) and show how it differs — so you can recognize a number to discard.

**Acceptance criteria.**

- `notes/week-09/benchmark-stability.md` shows three clean runs of the same mesh with p50/p99 within your stated tolerance.
- It shows one deliberately-bad run (cold, or too short) and identifies *why* its numbers are untrustworthy.
- You state the rule you'll apply: a number that doesn't reproduce within tolerance gets re-run or discarded, never cited.
- Committed.

**Hint.** Warm-up is the usual culprit. Your first few seconds include connection setup, JIT-ish cache warming, and cold caches; the Exercise-3 driver skips a warm-up window for exactly this reason. A run with no warm-up skip, or only 5 seconds of load, will show a wild p99 — that's the bad run to demonstrate.

**Estimated time.** 40 minutes.

---

## Problem 3 — Same posture, prove it three ways

**Problem statement.** Demonstrate that you reached the *same* security posture (mTLS on + only cart→inventory allowed) on all three meshes — because an unfair comparison is worse than none. For each mesh, capture: (a) proof mTLS is on (the mesh's own verification command), and (b) proof a non-cart caller is denied.

**Acceptance criteria.**

- `notes/week-09/same-posture.md` has, per mesh, the mTLS-on evidence (Istio `connection_security_policy=mutual_tls`; Linkerd `edges ... SECURED`; Cilium auth-required + hubble FORWARDED) and the denial evidence (an unauthorized caller blocked).
- You explicitly confirm all three are at the SAME bar, so your benchmark comparison is fair.
- Committed.

**Hint.** The verification command differs per mesh — that's part of the lesson. Istio: `istioctl x describe` + the telemetry label. Linkerd: `linkerd viz edges`. Cilium: `cilium status` + `hubble observe` showing FORWARDED vs DROPPED. Capturing all three side by side is itself a comparison data point (which mesh made "prove mTLS is on" easiest?).

**Estimated time.** 50 minutes.

---

## Problem 4 — The 200-engineer-org mesh ADR (headline deliverable)

**Problem statement.** This is the syllabus deliverable. Write the Architectural Decision Record at `notes/week-09/mesh-adr.md` recommending a mesh (or no mesh) for a specific 200-engineer org. Define the org concretely: ~120 services, ~25 teams, a mix of gRPC and HTTP, a compliance mandate for mTLS on every internal hop, currently on a standard CNI (not Cilium), no mesh today. Follow the full ADR format:

1. **Title & status.**
2. **Context** — the org's situation; the problem a mesh solves here (uniform mTLS across 25 teams that compliance requires); the constraints (existing CNI, team skill, operational budget).
3. **Options considered** — Istio (sidecar and ambient), Linkerd, Cilium, and no-mesh — each with pros/cons *for this org*, citing your benchmark numbers.
4. **Decision** — the choice, one sentence, primary reasons.
5. **Consequences** — operational burden, the CNI-migration cost if you pick Cilium, the sidecar tax if Istio, the L7 ceiling if Linkerd; good and bad.
6. **Reversal conditions** — the specific triggers that would make you revisit (e.g., "if L7-routing needs spread past N teams" or "if the sidecar memory bill exceeds budget X").

**Acceptance criteria.**

- `notes/week-09/mesh-adr.md` follows all six headings and fits in roughly 800–1200 words.
- The decision is **specific to this org** (its compliance mandate, its existing CNI, its scale), not generic.
- The options section cites your **own benchmark numbers** and extrapolates the cost to ~120 services / the org's pod count.
- It **commits** to a recommendation and names at least two concrete **reversal conditions**.
- The CNI constraint is addressed (it materially affects the Cilium option).
- Committed.

**Hint.** The compliance mandate ("mTLS on every hop") is the load-bearing context — it's what justifies a mesh *at all* for this org (you can't easily prove uniform mTLS across 25 teams with a shared library). That points toward *a* mesh; the choice between the three then turns on cost (your benchmark), the CNI constraint (Cilium means a CNI migration here), and operational budget (Istio's depth vs Linkerd's simplicity). The strongest ADRs make the compliance requirement the spine and let the benchmark + constraints pick among the meshes.

**Estimated time.** 1 hour 10 minutes.

---

## Problem 5 — Linkerd vs Istio config volume

**Problem statement.** Quantify the "simplicity" claim. Reach the *identical* least-privilege posture (cart→inventory only) on Linkerd and Istio, and compare the total config it took — lines of YAML, number of CRDs, and number of distinct concepts you had to understand. Write up which was simpler and whether that simplicity is a real operational win for the 200-engineer org.

**Acceptance criteria.**

- `notes/week-09/config-volume.md` shows the Linkerd YAML (`Server` + `AuthorizationPolicy`) and the Istio YAML (`PeerAuthentication` + `AuthorizationPolicy`) side by side, with line counts.
- You count the distinct concepts each required (e.g., Istio: PeerAuthentication mode + principal + selector; Linkerd: Server + authentication ref).
- You state, in two-to-three sentences, whether the config-volume difference is decisive for the org or marginal.
- Committed.

**Hint.** Remember Linkerd needs *zero* config for the mTLS itself (it's automatic), so the comparison is really "Istio's PeerAuthentication+AuthorizationPolicy" vs "Linkerd's Server+AuthorizationPolicy" — and Istio's permissive-vs-strict mode is one more concept to get right. But don't overweight YAML lines; the real question is operational cognitive load, which you should judge from having done both.

**Estimated time.** 35 minutes.

---

## Problem 6 — When no mesh wins

**Problem statement.** Write a short counter-case: for a *different*, smaller org (8 services, 3 teams, one cluster, no hard compliance mandate), argue that **none** of the three meshes is the right answer, and that the Week 7 gateway-plus-library approach is. Make the case as rigorously as you made the pro-mesh ADR in Problem 4.

**Acceptance criteria.**

- `notes/week-09/no-mesh.md` argues, for the smaller org, that no mesh is justified, with specific reasons (the mesh's value doesn't exceed its operating cost at this scale; mTLS via a shared library + OTel telemetry suffices; a control plane is a new thing to operate for little gain).
- It addresses the obvious counter ("but everyone uses a mesh") and refutes it for this org.
- It states what would change the answer (the scale/team-count/compliance trigger at which a mesh *would* be justified).
- Committed.

**Hint.** The strongest version names the *specific* threshold: "at ~8 services and 3 teams, a shared mTLS library is auditable by hand; the mesh's value kicks in around the point where no single person can verify every hop's encryption — call it 15+ teams or a compliance mandate." Naming the crossover point is what makes this a real architectural position and not just "small = no mesh."

**Estimated time.** 40 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 — Three-way comparison table | 45 min |
| 2 — Reproduce + stabilize the benchmark | 40 min |
| 3 — Same posture, three ways | 50 min |
| 4 — 200-engineer-org ADR (headline) | 1 h 10 min |
| 5 — Linkerd vs Istio config volume | 35 min |
| 6 — When no mesh wins | 40 min |
| **Total** | **~5 h 0 min** |

When you've finished all six, push your repo and make sure the `mesh-bakeoff` [mini-project](./07-mini-project/00-overview.md) is in the same workspace — the ADR is the template for your Week 12 midterm essay. Then take the [quiz](./05-quiz.md) with your notes closed. This closes Phase 2's service-mesh arc; Week 10 turns to eventing.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Comparison table (P1)** | 15 | All three meshes, every row from your own runs; relative-not-absolute noted. |
| **Benchmark stability (P2)** | 15 | Three reproducible runs within tolerance; a bad run identified; the discard rule stated. |
| **Same posture (P3)** | 15 | mTLS-on + denial proven on all three at the same bar; comparison confirmed fair. |
| **The ADR (P4)** | 30 | Full format; org-specific; benchmark cited + extrapolated; commits to a choice; reversal conditions; CNI constraint addressed. |
| **Config volume (P5)** | 15 | Side-by-side YAML + concept counts; honest verdict on whether simplicity is decisive. |
| **No-mesh case (P6)** | 10 | Rigorous; addresses the counter; names the crossover threshold. |

**90+** is portfolio-grade and ready to be your Week 12 midterm template. **70–89** is solid but the ADR likely hedges or skips the benchmark extrapolation. **Below 70** usually means Problem 4 was written as a generic "it depends" instead of a committed, org-specific decision — which is the one skill this whole phase has been building toward.
