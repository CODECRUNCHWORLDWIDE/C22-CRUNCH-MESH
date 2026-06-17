# Week 24 — Resources

Every resource here is **free** and **open**. This is a delivery-and-defense week: the references are the C4 diagramming model, the architecture-review and postmortem templates, and the tooling to record a demo and drive the two chaos drills — all open or freely published. No paywalled material is required. The technology docs you need (Istio, Kafka, Temporal, OpenTelemetry, etc.) are the ones you've been using since Phase 2; this page collects the *delivery* references.

## Required reading (work it into your week)

- **The C4 model (Simon Brown)** — system context, container, component, code. The diagramming approach the architecture document uses. Read it Monday:
  <https://c4model.com/>
- **Google SRE — Postmortem culture: learning from failure** — the blameless postmortem the two chaos drills require:
  <https://sre.google/sre-book/postmortem-culture/>
- **Google SRE — Example postmortem** — the structure (summary, impact, timeline, root cause, action items) to copy:
  <https://sre.google/sre-book/example-postmortem/>
- **Google SRE Workbook — On-call and incident response** — the operational vocabulary for the runbook's five failure modes:
  <https://sre.google/workbook/incident-response/>

## The architecture review and the C4 document

- **C4 model — Diagrams** — what each of the four levels shows and how much detail belongs at each:
  <https://c4model.com/diagrams>
- **Structurizr / Mermaid C4** — render C4 diagrams as code that diffs in git. Mermaid has native `C4Context`/`C4Container` support:
  <https://mermaid.js.org/syntax/c4.html>
- **arc42 architecture documentation template** — a fuller template if you want headings for the 2,000-word doc:
  <https://arc42.org/>
- **Architecture Decision Records (ADRs)** — the format for recording *why* (you wrote these in Week 9); the architecture doc references them:
  <https://adr.github.io/>

## Postmortems and chaos drills

- **Google SRE — Postmortem culture** — blameless, timeline-driven, action-item-closing:
  <https://sre.google/sre-book/postmortem-culture/>
- **PagerDuty — Postmortem documentation (open guide)** — a practical template and the "five whys without blame" framing:
  <https://postmortems.pagerduty.com/>
- **Principles of Chaos Engineering** — the four principles you applied in Week 22, the basis for the two drills:
  <https://principlesofchaos.org/>
- **chaos-mesh docs** — the fault-injection tool from Week 22, used here to drive the broker-loss and region-failover faults:
  <https://chaos-mesh.org/docs/>

## The demo recording

- **OBS Studio** — free, open-source screen recording for the 12-minute demo:
  <https://obsproject.com/>
- **asciinema** — record and embed terminal sessions (good for the trace-an-order walk):
  <https://asciinema.org/>
- **otel-cli** — drive and fetch traces from the command line for the demo's trace waterfall:
  <https://github.com/equinix-labs/otel-cli>

## Load and verification

- **k6** — the load generator for the 1k-RPS region-failover drill:
  <https://k6.io/docs/>
- **fortio** — the bundled load generator (from the Istio samples) for the canary and failover:
  <https://github.com/fortio/fortio>
- **grpcurl** — call any gRPC method through the mesh to demonstrate a hop live:
  <https://github.com/fullstorydev/grpcurl>

## Tools you'll use this week

- **`kubectl` + two Kind clusters** — the two-region active-active topology; `kubectl --context` to drive each region.
- **`istioctl`** — prove mTLS strict and drive the canary weights (or let Flagger do it).
- **`k6` / `fortio`** — generate the 1k-RPS load the region-failover drill runs under.
- **`chaos-mesh`** — inject the region-loss (pod-kill / network-partition) and broker-loss faults.
- **`otel-cli` + Grafana/Tempo/Loki** — pull the trace waterfall and do the trace-to-log jump on camera.
- **`pact-broker` CLI** — show the broker green and `can-i-deploy` passing as a live capstone artifact.
- **OBS Studio** — record the 12-minute demo.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **C4 model** | A four-level diagramming approach: Context (the system in its world), Container (the deployable units), Component (the pieces inside a container), Code. |
| **Architecture review** | A structured hour where reviewers search for the risks in a design before production does. |
| **Blast radius** | What else fails when one component fails — the scope of an outage. |
| **Failure domain** | A set of things that fail together (a region, a broker, a Postgres primary). Good design isolates them. |
| **RTO** | Recovery Time Objective: how long until service is restored after a failure (the failover drill's headline number). |
| **RPO** | Recovery Point Objective: how much data you can lose (for the capstone, the target is zero). |
| **Blameless postmortem** | An incident writeup that fixes the *system*, not the person — timeline, root cause, action items, no blame. |
| **Five whys** | Asking "why" repeatedly to reach a root cause rather than a proximate symptom. |
| **Active-active** | Both regions serve traffic simultaneously (vs active-passive, where one is standby). |
| **Exactly-once** | The consumer processes each message's *effect* once, despite at-least-once delivery — via idempotency keys + outbox. |
| **Outbox pattern** | Writing events to a DB table in the same transaction as the state change, then relaying them — so the event and the state can't disagree. |
| **Trace-to-log jump** | Clicking from a span in a trace to the exact log lines that span emitted — the observability move that wins a review. |
| **Weighted canary** | Shifting a fraction of traffic to a new version (10/90 → 50/50 → 100/0), rolling back on an SLO breach. |
| **Capstone defense** | The live architecture review in front of the cohort and two external reviewers — the course's final assessment. |

---

*If a link 404s, please open an issue so we can replace it.*
