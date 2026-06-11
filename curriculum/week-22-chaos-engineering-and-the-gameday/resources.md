# Week 22 — Resources

Every resource here is **free** and **open**. Chaos Mesh and LitmusChaos are CNCF projects with openly published docs. The chaos-engineering principles are published free by Netflix and the *Chaos Engineering* authors. The postmortem corpus is community-maintained and open. No paywalled books are linked.

Chaos Mesh versions its CRD APIs per release. This week targets **Chaos Mesh 2.6+** (the line where `chaos-mesh.org/v1alpha1` is stable and the dashboard ships with RBAC). When a link is to `latest`, pin it to your installed version if a CRD field differs; the *concepts* — selector, mode, duration, the per-fault kind — are stable.

## Required reading (work it into your week)

- **Principles of Chaos Engineering** — the canonical statement of the four principles. Read it Monday, first:
  <https://principlesofchaos.org/>
- **Chaos Mesh — Overview / Architecture** — the controller manager, the chaos daemon, how injection works. Read it Monday and again Friday:
  <https://chaos-mesh.org/docs/>
- **Google SRE — Postmortem Culture: Learning from Failure** — the blameless postmortem, stated by the people who institutionalized it:
  <https://sre.google/sre-book/postmortem-culture/>
- **Google SRE — Example Postmortem** — the structure you will copy: timeline, impact, root-causes-plural, action items:
  <https://sre.google/sre-book/example-postmortem/>
- **Chaos Mesh — Run a Chaos Experiment** — the apply/observe/delete loop for a `PodChaos`:
  <https://chaos-mesh.org/docs/run-a-chaos-experiment/>

## The fault types (skim, then refer back)

- **Chaos Mesh — PodChaos** — pod-kill, pod-failure, container-kill:
  <https://chaos-mesh.org/docs/simulate-pod-chaos-on-kubernetes/>
- **Chaos Mesh — NetworkChaos** — partition, loss, delay, duplicate, corrupt, bandwidth:
  <https://chaos-mesh.org/docs/simulate-network-chaos-on-kubernetes/>
- **Chaos Mesh — StressChaos** — CPU and memory pressure via stress-ng:
  <https://chaos-mesh.org/docs/simulate-heavy-stress-on-kubernetes/>
- **Chaos Mesh — IOChaos** — filesystem latency, fault, and attribute override:
  <https://chaos-mesh.org/docs/simulate-io-chaos-on-kubernetes/>

## Orchestration and scheduling

- **Chaos Mesh — Schedule** — run an experiment on a cron (continuous chaos):
  <https://chaos-mesh.org/docs/define-scheduling-rules/>
- **Chaos Mesh — Workflow** — chain faults into a multi-stage experiment:
  <https://chaos-mesh.org/docs/create-chaos-mesh-workflow/>

## The alternatives (the honest comparison)

- **LitmusChaos — Documentation** — the CNCF experiment-hub + chaos-workflow model:
  <https://docs.litmuschaos.io/>
- **LitmusChaos — ChaosHub** — the catalog of pre-built experiments:
  <https://hub.litmuschaos.io/>
- **Gremlin — what the commercial SaaS adds** — the "when you'd pay for it" reference (status-checks, blast-radius UI, SaaS control plane). Read it to know what you *aren't* getting for free:
  <https://www.gremlin.com/community/tutorials/>

## Gameday and postmortem practice

- **Google SRE Workbook — On-Call** and **Incident Response** — the roles (commander, scribe, ops) the gameday borrows:
  <https://sre.google/workbook/incident-response/>
- **PagerDuty — Incident Response / Postmortem docs** — an openly published, practical postmortem process:
  <https://response.pagerduty.com/after/post_mortem_process/>
- **The "Five Whys is harmful" critique** — search for the systems-thinking argument against single-root-cause analysis (Allspaw, "Each necessary, but only jointly sufficient"); the basis for contributing-factors analysis:
  <https://www.kitchensoap.com/2012/02/10/each-necessary-but-only-jointly-sufficient/>
- **The morgue / public postmortem collections** — read real postmortems to calibrate; the `danluu/post-mortems` collection is the canonical open corpus:
  <https://github.com/danluu/post-mortems>

## Talks worth your time (free, no signup)

- **"Chaos Engineering" — the Netflix origin talks** — the Simian Army, Chaos Monkey, and the why; posted free on YouTube/InfoQ.
- **Chaos Mesh / LitmusChaos maintainer sessions** — KubeCon + CloudNativeCon talks on the CNCF channel:
  <https://www.youtube.com/c/cloudnativefdn>
- **"Gamedays on the Network Edge" and the AWS/Stripe gameday writeups** — how mature orgs run drills; search the engineering blogs.

## Tools you'll use this week

- **Chaos Mesh** — install via Helm (`helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh`); author `*Chaos` CRDs; watch the dashboard (`chaos-dashboard`).
- **`kubectl`** — apply/delete chaos CRDs, label target pods for the `selector`, read pod events and the experiment status.
- **Prometheus + Grafana** (from Week 17) — the steady-state SLI you watch during every experiment. No metric, no experiment.
- **`k6`** (or `fortio`) — hold the system at a steady load so a fault is something a user would feel.
- **Strimzi / `kafka-consumer-groups.sh`** — for the broker-loss drill: inspect ISR, consumer-group offsets, and lag to prove no double-process.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Chaos engineering** | The disciplined practice of injecting controlled failure to find resilience gaps before an incident does. |
| **Steady-state hypothesis** | A claim about a measurable system property ("error rate stays below 1%") you expect to *hold* during the fault. |
| **Blast radius** | How much of the system an experiment can affect. You minimize it deliberately — the smallest experiment that tests the hypothesis. |
| **Abort condition** | The pre-agreed signal (usually an SLO breach) that stops the experiment immediately. The dead-man's switch. |
| **Gameday** | A scheduled, time-boxed drill where you inject failures against hypotheses with named roles and a runbook. |
| **Game master** | The person who knows the injected fault; the "responders" diagnose it blind. |
| **Chaos Mesh** | CNCF, CRD-driven chaos platform: a `*Chaos` resource per fault, a per-node daemon that injects it. |
| **LitmusChaos** | CNCF chaos platform built around an experiment hub and chaos workflows. |
| **`PodChaos` / `NetworkChaos` / `StressChaos` / `IOChaos`** | Chaos Mesh CRDs for pod, network, resource, and filesystem faults. |
| **`selector` / `mode`** | How a chaos CRD picks targets (labels/namespaces) and how many (`one`, `fixed`, `percent`, `all`). |
| **Blameless postmortem** | An incident writeup that analyzes systems and decisions, never blames a person; built to be published and learned from. |
| **Contributing factors** | The plural causes of an incident — the honest replacement for a single "root cause." |
| **Five whys** | A root-cause technique; critiqued here because real incidents rarely have one linear cause. |
| **Exactly-once (EOS)** | The invariant the broker-loss drill tests: a message is processed once and only once despite failure + redelivery. |

---

*If a link 404s, please open an issue so we can replace it.*
