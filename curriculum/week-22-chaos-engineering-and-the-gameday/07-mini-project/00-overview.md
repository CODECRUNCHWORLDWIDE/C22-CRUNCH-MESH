# Mini-Project — `marketplace-gameday`: A Full Gameday Harness, Run for Real

> Build the gameday harness for your capstone Polyglot Marketplace Backbone: the six experiments as committed chaos-as-code, a written runbook with hypotheses and abort conditions, a 90-minute live drill with a scribe's timeline, and a blameless postmortem for every non-trivial finding — including the two that *become* capstone Drills A (region failover) and B (broker loss / exactly-once).

This is the artifact that turns "I read about chaos engineering" into "I ran a gameday and have the postmortems to prove it." After this week, chaos is a *repeatable drill* you can run against your system on demand: a metric-judged, blast-radius-bounded, abort-protected exercise that finds the gap between designed and actual resilience — and a postmortem corpus that turns each finding into a fix. When a capstone reviewer asks "how do you know your exactly-once actually holds under broker loss?", you answer with an audit and a postmortem, not a claim.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This `marketplace-gameday` is the chaos-drill foundation of your **capstone**. The syllabus mandates *two* chaos-drill postmortems (Drill A — region failover, Drill B — Kafka broker loss); two of this week's experiments + postmortems *are* those drills, run as a rehearsal. Build them cleanly now and Week 24 is revision, not invention. The runbook, the steady-state metrics, and the abort conditions all transfer directly to the capstone's two-region deployment.

---

## What you will build

A repo `marketplace-gameday` with five deliverables:

1. **`experiments/`** — the six experiments as committed Chaos Mesh CRDs (the Exercise-2 library, adapted to *your* services' labels), each in its own file, each scoped (`selector`/`mode`) and time-boxed (`duration`). Chaos-as-code: the gameday is reproducible from `git`.
2. **`runbook.md`** — the gameday runbook: a table with one row per experiment — hypothesis (with the *reason*), steady-state SLI (as a Prometheus query), abort condition (a concrete number), roles (commander/scribe/observer), and rollback. Plus the 90-minute timeline structure.
3. **`drills/`** — the two capstone drills written up in full: **Drill A — region failover** (the partition experiment + a primary-region kill under load) and **Drill B — broker loss / exactly-once** (the broker-loss `PodChaos` + the idempotency audit from Exercise 3). Each with its own postmortem.
4. **`postmortems/`** — one blameless postmortem per non-trivial finding, in the SRE structure (summary, quantified impact, timeline, contributing factors, "where we got lucky," owned+typed action items). At minimum the two drill postmortems; ideally one per refuted hypothesis.
5. **`audit/verify_gameday.sh`** — a script that proves the gameday is real and clean: it asserts the steady-state metrics exist and are queryable, that every experiment file is scoped+bounded (no `mode: all` without a `duration`), that the EOS audit ran and reported a verdict, and — critically — that **no chaos resources are left running** in any namespace. Exits non-zero if any check fails.

By the end you have a public repo of chaos-as-code + a runbook + a live-drill timeline + publishable postmortems + an audit script that gates the whole thing.

---

## Why this and not "just run chaos-mesh once"

You could `kubectl apply` a `PodChaos`, watch a pod die, and call it chaos engineering. Don't stop there — that's the gap this whole week is about. A defensible gameday harness gives you:

- **Experiments judged by a metric**, not by vibes. Every experiment has a steady-state SLI and a pre-committed verdict criterion, so a refutation is unambiguous and a finding is real.
- **A bounded, abortable drill**, not a self-inflicted outage. Every experiment is scoped and time-boxed with an abort condition, so "break your own system" is a professional practice.
- **Exactly-once proven, not claimed.** Drill B's audit demonstrates that redelivery happened *and* was absorbed — the difference between a green dashboard and a correct system.
- **Postmortems good enough to publish**, so each finding becomes a permanent fix with an owner, not a thing you rediscover at 3 a.m.

Progressive-delivery and continuous-chaos tooling will eventually run much of this for you. Building the gameday by hand first is what lets you trust what they automate — the senior-shop convention in 2026.

---

## Repo layout

```
marketplace-gameday/
├── README.md
├── runbook.md                    # the gameday runbook + 90-min structure + roles
├── experiments/
│   ├── 01-cart-pod-kill.yaml
│   ├── 02-region-partition.yaml
│   ├── 03-inventory-degrade.yaml
│   ├── 04-order-cpu-stress.yaml
│   ├── 05-kafka-io-latency.yaml
│   └── 06-kafka-broker-loss.yaml
├── drills/
│   ├── drill-a-region-failover.md     # capstone Drill A: kill primary region under load
│   └── drill-b-broker-loss-eos.md     # capstone Drill B: broker loss + EOS audit
├── postmortems/
│   ├── pm-2026-06-12-<finding-slug>.md
│   └── ...                            # one per non-trivial finding
├── audit/
│   ├── eos_audit.py               # the Exercise-3 idempotency audit
│   └── verify_gameday.sh          # asserts metrics exist, experiments bounded, no chaos left
└── timeline.md                    # the scribe's live record from the Friday drill
```

---

## Deliverable 1 — `experiments/` (chaos-as-code)

The six experiments, adapted to your services' real labels and namespaces. Each file is ONE experiment. Each must have a `selector` (scoped targets), a `mode` (bounded count), and a `duration` (time-boxed) — the blast-radius discipline. Document at the top of each file the hypothesis, the steady-state SLI query, and the abort condition (mirroring `runbook.md`). These are committed so the gameday is reproducible: a teammate clones the repo and runs the *exact* drill you ran.

> **The rule the audit enforces:** no experiment may have an unbounded blast radius. `mode: all` is allowed only with a tight `selector` and a `duration`; an experiment with no `duration` (a fault that never ends on its own) fails the audit.

---

## Deliverable 2 — `runbook.md` (the gameday plan)

The runbook table (one row per experiment) plus the 90-minute structure and roles. Every hypothesis states the *reason* you believe it. Every abort condition is a concrete number ("error > 5% for 60 s"), decided in advance. Name the roles even if you're running it solo — and in the timeline, note which hat you wore when. This is the document you read out at minute 0 of the drill, before anyone injects anything.

---

## Deliverable 3 — `drills/` (the two capstone drills)

The two mandatory capstone drills, written up so Week 24 is revision:

- **`drill-a-region-failover.md`** — kill the primary region during a sustained load test (the partition experiment, escalated to a full region kill). Document the RTO (target: the syllabus's failover window), the data-loss window, the recovery, and the lessons. This is the capstone's Drill A.
- **`drill-b-broker-loss-eos.md`** — lose a Kafka broker mid-traffic; run the Exercise-3 audit to prove the exactly-once consumers do not double-process and the outbox guarantees integrity. The verdict is the audit (side-effect count == business-event count, with redelivery observed), not the dashboard. This is the capstone's Drill B.

---

## Deliverable 4 — `postmortems/` (the writeups)

One blameless postmortem per non-trivial finding, in the SRE structure (Lecture 2 §3.1). At minimum, the two drill postmortems — note that a drill whose hypothesis *held* still gets a postmortem (document the redelivery you absorbed, the recovery time, where you got lucky). Each postmortem must:

- Quantify impact and extrapolate to production scale.
- List contributing factors (plural), not a single root cause.
- Include a "where we got lucky" section.
- End with action items, each with an owner and a type (prevent/detect/mitigate).
- Read as blameless — analyzing systems and decisions-with-information-available, never people.

---

## Deliverable 5 — `audit/verify_gameday.sh`

A script that makes the gameday *verifiable*, not claimed. It must:

1. Assert every `experiments/*.yaml` is **bounded**: has a `selector`, a `mode`, and a `duration` (no unbounded blast radius).
2. Assert each experiment's **steady-state SLI query** is present and returns data from Prometheus (the metric exists and is live).
3. Assert the **EOS audit** ran and emitted a verdict for Drill B (`EXACTLY-ONCE HELD` or a recorded finding).
4. Assert **no chaos resources are left running** — `kubectl get podchaos,networkchaos,stresschaos,iochaos -A` is empty. A gameday that leaves chaos running is a self-inflicted outage.
5. Exit **0** when every assertion passes; exit **non-zero** naming the first failure.

Sketch:

```bash
#!/usr/bin/env bash
set -euo pipefail
fail() { echo "GAMEDAY AUDIT FAIL: $1" >&2; exit 1; }

# 1. every experiment is bounded (selector + mode + duration present)
for f in experiments/*.yaml; do
  grep -q "selector:" "$f"  || fail "$f has no selector (unbounded targets)"
  grep -q "mode:" "$f"      || fail "$f has no mode (unbounded count)"
  grep -q "duration:" "$f"  || fail "$f has no duration (fault never ends)"
done

# 2. no chaos left running anywhere (the cardinal cleanup rule)
left=$(kubectl get podchaos,networkchaos,stresschaos,iochaos -A --no-headers 2>/dev/null | wc -l)
[ "$left" -eq 0 ] || fail "$left chaos resource(s) still running — clean up before declaring done"

# 3. the EOS audit produced a verdict
grep -q "VERDICT:" postmortems/*broker-loss* drills/drill-b* 2>/dev/null \
  || fail "Drill B has no recorded exactly-once verdict"

echo "GAMEDAY AUDIT PASS: experiments bounded, no chaos left running, EOS verdict recorded."
```

---

## Rules

- **You may** read the Chaos Mesh / Litmus docs, the lecture notes, and the Google SRE postmortem chapter.
- **You must not** run an experiment without a written hypothesis, a steady-state metric, and an abort condition decided *first*.
- **You must not** leave any chaos resource running. The audit enforces this; a gameday that outages your own cluster is a fail.
- **You must not** declare exactly-once "held" without the audit (redelivery observed + zero double-processing). A green dashboard is not the verdict.
- **You must not** "fix" a refuted hypothesis by loosening the SLO, the abort condition, or deleting the experiment (see the challenge).
- Chaos Mesh 2.6+, Kind, Prometheus + Grafana, `k6`. Everything runs locally on your two-region setup.
- The audit must exit non-zero on any failed assertion so it can gate the capstone's drill deliverable.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-22-marketplace-gameday-<yourhandle>`.
- [ ] `experiments/` has the six experiments as committed chaos-as-code, each scoped + time-boxed.
- [ ] `runbook.md` has one row per experiment with a reasoned hypothesis, an SLI query, and a concrete abort condition, plus the 90-minute structure and roles.
- [ ] You ran a live 90-minute gameday; `timeline.md` is the scribe's record (inject → peak → recover timestamps).
- [ ] `drills/drill-a-region-failover.md` and `drills/drill-b-broker-loss-eos.md` are complete, with Drill B's exactly-once audit verdict.
- [ ] `postmortems/` has at least the two drill postmortems (blameless, quantified, contributing factors plural, owned+typed action items) — ideally one per refuted hypothesis.
- [ ] `audit/verify_gameday.sh` exits **0** for a clean, bounded, chaos-free gameday and **non-zero** when an experiment is unbounded or chaos is left running — demonstrated in the README.
- [ ] A `README.md` with the runbook summary, the findings list, and a paragraph on what the gameday changed about the system.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Experiment design** | 20 | Six experiments, each scoped + time-boxed; a reasoned hypothesis + SLI + abort per experiment, written before injecting. |
| **The live gameday** | 15 | A real 90-minute drill with a scribe's timeline; experiments run one at a time with recovery confirmed between them. |
| **Drill B — exactly-once** | 20 | Redelivery observed AND absorbed, proven by the idempotency audit; the verdict is the audit, not the dashboard. |
| **Drill A — region failover** | 15 | Failover under load with RTO + data-loss window documented; the partition/region-kill run as a real drill. |
| **Postmortems** | 20 | Blameless, quantified + extrapolated, contributing factors (plural), owned + typed action items, a "where we got lucky" section. |
| **Auditability & hygiene** | 10 | `verify_gameday.sh` enforces boundedness + cleanup; no chaos left running; clear README; sensible commits. |

**90+** is portfolio-grade and ready to be the capstone's chaos-drill deliverable. **70–89** works but likely claims exactly-once without the audit, or writes single-root-cause postmortems. **Below 70** usually means an experiment ran unbounded, chaos was left running, or a refuted hypothesis was waved off — fix that first; it's the one thing this week exists to prevent.

---

## Stretch goals

- **Continuous chaos.** Add a `Schedule` so a small, safe experiment fires every hour, and run it for a day. Find a regression automatically — the posture mature orgs run in production.
- **Chained workflow.** Build a Chaos Mesh `Workflow` (or Litmus chaos workflow) that scripts a multi-stage drill: partition → heal → assert convergence → broker loss → assert exactly-once. A replayable gameday.
- **Automatic abort.** Wire a Prometheus alert that *halts* an experiment when its steady-state SLI breaches — chaos with a real dead-man's switch, the safety property production chaos demands.
- **CI gate.** A GitHub Actions workflow that boots a Kind-in-a-container, applies the experiments against a toy topology, and runs `verify_gameday.sh`. Green check on every push.

---

## How this connects to the rest of C22

- **Weeks 10–11 (Kafka + exactly-once)** built the outbox + idempotent consumer that Drill B proves under broker loss.
- **Weeks 19–20 (multi-region + CRDTs)** built the active-active cart that Drill A's partition tests for convergence.
- **Week 17 (observability)** built the steady-state metrics that judge every experiment — the hard prerequisite for the whole week.
- **Week 18 (SLI/SLO)** defined the SLOs that *are* the abort conditions.
- **Week 24 (capstone)** requires Drills A and B with postmortems; the two you write here are their drafts.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
