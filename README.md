# C22 · Crunch Mesh — Microservices & Distributed Systems

Crunch Mesh is the Code Crunch Labs tier course for engineers who have shipped backend systems and now need to design the platforms those systems live on. Twenty-four weeks of distributed-systems theory, polyglot service design, service mesh, event streaming, multi-region data, observability, and chaos engineering, taught entirely on open-source infrastructure. You graduate able to lead a backend platform team, defend an architecture under cross-examination, and pass a staff-engineer system-design loop on technique rather than buzzwords.

The Mesh sub-brand is lagoon-blue (`#0EA5E9`). The editorial voice is restrained and technical. The bias is open-source-first: Kubernetes, Istio, Linkerd, Envoy, Postgres, Debezium, Kafka, Redpanda, NATS, Temporal, gRPC, OpenTelemetry, Prometheus, Thanos, Grafana, Tempo, Loki, Trino, Iceberg, OPA, SPIFFE/SPIRE.

---

## Who this course is for

- **Senior backend engineers leveling to staff.** You ship features, you own services, you mentor — but you have not yet been the person in the room who decides whether the system is correct under partition. This course closes that gap.
- **SREs bridging into architecture.** You run the platform and you know where it bleeds. Crunch Mesh gives you the design vocabulary, the consensus-and-replication theory, and the contract design skills to drive architecture forward rather than only catch its mistakes.
- **Cloud platform engineers wanting deep distributed knowledge.** You know how to wire managed services together. Now you need to know why each one behaves the way it does — and what to do when you are the one building the equivalent on bare Kubernetes.
- **New grads targeting principal-track companies.** If your goal is staff-track at a FAANG-scale or hyper-scale backend, you need this material before the interview loop, not after.

This is not an introductory course. If you do not have production backend experience, take C16 (Crunch Pro Backend) first.

---

## What you can do at the end

By graduation week 24 you can:

1. Decompose a monolithic backend into bounded contexts without creating a distributed monolith.
2. Design a polyglot service topology (Go, Python, Rust) with a single, typed contract surface in Protobuf and gRPC.
3. Choose between Kafka, NATS JetStream, and Redpanda based on retention, throughput, and operational profile — and defend the choice.
4. Implement exactly-once event processing with idempotency keys, outbox tables, and consumer offsets you understand from first principles.
5. Operate a service mesh (Istio or Linkerd) in production: mTLS everywhere, traffic shifting, canary, and progressive delivery.
6. Run Temporal workflows for long-running orchestrations and explain when orchestration beats choreography for sagas.
7. Build a Debezium CDC pipeline from Postgres into Kafka and consume it into both an OLTP read model and an Iceberg-on-Trino lakehouse.
8. Instrument a polyglot system end-to-end with OpenTelemetry: traces with proper context propagation, RED metrics, structured logs, and exemplars linking them.
9. Define SLIs and SLOs that mean something, manage error budgets, and run a real on-call rotation.
10. Apply CAP, PACELC, FLP, and the consensus literature to architectural decisions rather than recite them as trivia.
11. Design and operate an active-active multi-region deployment with quorum-aware writes, conflict-resolved CRDT state, and geo-routing.
12. Stand up a zero-trust service network with SPIFFE/SPIRE identities and OPA policy.
13. Run a gameday: inject region-loss, broker-loss, and dependency-latency failures with chaos-mesh and write the postmortem.
14. Lead a staff-engineer-level system design conversation — drawing the diagram, naming the tradeoffs, and committing to a position with evidence.

---

## Prerequisites

Required:

- **C1 Crunch Convos** or equivalent fluency in at least one production backend language.
- **C15 Crunch DevOps** — comfortable with Docker, Kubernetes basics, CI/CD pipelines, Terraform.
- **C16 Crunch Pro Backend** — you have built and operated a non-trivial REST/gRPC service in production.
- OR: two or more years of professional backend experience in a production system that you personally were on-call for.

Helpful but not required:

- **C18 Crunch GCP** or **C19 Crunch AWS** — cloud fluency makes the multi-region phase faster.
- **C17 Pro Python Advanced** or comparable depth in Go.
- Linear algebra and probability at the level of an undergraduate CS curriculum (helpful for queuing theory and the Universal Scalability Law).

If you are unsure, take the placement quiz in `assessment/placement.md` before week one.

---

## Program at a glance (4 phases · 24 weeks)

### Phase 1 · Theory & single-service production (weeks 1–6)
The literature first. CAP, PACELC, FLP, consensus, vector clocks, CRDTs, leases. Then microservice fundamentals: bounded contexts, Conway's law, decomposition heuristics, anti-patterns. Then your first hardened single service in Go and Python, with typed gRPC contracts, structured logging, and OpenTelemetry.

### Phase 2 · Service mesh & eventing (weeks 7–12)
Multiple services. Service-to-service communication. API gateways and BFFs. Istio and Linkerd in depth. Kafka and NATS JetStream. Exactly-once semantics. Temporal for workflows. The outbox pattern and sagas — orchestration versus choreography.

### Phase 3 · Data & reliability (weeks 13–18)
Postgres logical replication. Debezium CDC. CQRS and event sourcing. The modern lakehouse (Iceberg + Trino). Redis, Memcached, and Dragonfly. SLI/SLO/SLA discipline. Circuit breakers, bulkheads, timeouts, retries with jitter. Backpressure, load shedding, autoscaling with HPA + KEDA. Tail latency and the Universal Scalability Law.

### Phase 4 · Production & capstone (weeks 19–24)
Multi-region active-active. CRDT-based conflict resolution. Geo-routing. Zero-trust networking with SPIFFE/SPIRE and OPA. Chaos engineering with chaos-mesh. Contract testing with Pact. Capstone: the Polyglot Marketplace Backbone, built and run for the final four weeks, with two chaos drills and a published architecture review.

---

## Weekly cadence

Each week is a self-contained module:

- **Monday:** lecture and reading list (2 h) — paper or canonical chapter, then a 60-minute live walkthrough.
- **Tuesday–Thursday:** hands-on lab (12–15 h). Labs run on Kind, k3d, or minikube locally where possible.
- **Friday:** code review and architecture critique (2 h). Pull request review with the cohort.
- **Saturday:** quiz (30 min) and reflective writeup (1 h).
- **Sunday:** rest, or capstone work in the final phase.

Approximate total: 32–36 hours per week. Full-time equivalent: 864 hours across 24 weeks.

---

## Hardware and cloud expectations

Most labs run locally. Recommended baseline:

- 16 GB RAM, 8 cores, 100 GB free disk. 32 GB RAM strongly preferred from week 12 onward.
- Linux or macOS host. Windows via WSL2 is supported but tested less often.
- Local Kubernetes: Kind, k3d, or minikube. Examples are written for Kind.
- Container runtime: Docker or Podman.

Cloud labs run on GCP or AWS free tier where local capacity is exceeded:

- Phase 4 multi-region labs assume you can spin up two GKE Autopilot or EKS clusters in different regions for 4–8 hours at a time. Budget approximately USD 40–80 across phases 3 and 4.
- Capstone deployment can stay local if you accept simulated multi-region (two Kind clusters with a routed control plane), or run cloud for a more realistic week-23 gameday.

No proprietary tooling is required. Every commercial vendor referenced in lectures has a graded comparison against its open-source equivalent.

---

## Recommended pre and post tracks

**Feeder paths:**

- C1 → C15 → C16 → **C22**. The canonical path for an engineer who wants the full Crunch backend ladder.
- C18 or C19 → **C22**. Cloud-first engineers who already operate distributed systems but want the theory and the open-source mesh.
- C15 → **C22**. SREs who want to grow into architecture.

**Successor tracks:**

- C5 Crunch AI & Data Science — once you can move events reliably, you can serve them to a feature store.
- C6 Cybersecurity Crunch — zero-trust and mesh security become the natural next specialization.
- C13 Hack the Interview — used as the interview prep capstone for the staff-track loop.

---

## License and maintainers

GPL-3.0. See `LICENSE` for the canonical text. All lab code, lecture slides, diagrams, and assessment rubrics are released under the same license.

- **Course owner:** Code Crunch Labs — Crunch Mesh track
- **Track maintainer:** the Mesh sub-brand editorial team
- **Charter:** see `CHARTER.md` and the parent `../CRUNCH-LABS-CHARTER.md`

Contributions follow the parent org's `CONTRIBUTING.md`. Issues and PRs welcome on the cohort repository. We accept curriculum patches, lab improvements, and translated lecture material.


---

<!-- CCWW:AUTO-INDEX:START — generated by scripts/restructure_course_repos.py; edit ABOVE this marker -->

## Course at a glance

| Section | Count |
| --- | --- |
| Curriculum entries | 25 |
| Projects | 0 |
| Past sessions | 0 |

## Curriculum

- [SYLLABUS](curriculum/SYLLABUS.md)
- [week 01 cap pacelc and flp](curriculum/week-01-cap-pacelc-and-flp/README.md)
- [week 02 time order and consensus](curriculum/week-02-time-order-and-consensus/README.md)
- [week 03 crdts eventual consistency conflict resolution](curriculum/week-03-crdts-eventual-consistency-conflict-resolution/README.md)
- [week 04 microservice fundamentals and decomposition](curriculum/week-04-microservice-fundamentals-and-decomposition/README.md)
- [week 05 api contracts grpc protobuf](curriculum/week-05-api-contracts-grpc-protobuf/README.md)
- [week 06 the single hardened service](curriculum/week-06-the-single-hardened-service/README.md)
- [week 07 service to service bffs gateways envoy](curriculum/week-07-service-to-service-bffs-gateways-envoy/README.md)
- [week 08 istio in production](curriculum/week-08-istio-in-production/README.md)
- [week 09 linkerd and cilium service mesh](curriculum/week-09-linkerd-and-cilium-service-mesh/README.md)
- [week 10 eventing kafka and redpanda](curriculum/week-10-eventing-kafka-and-redpanda/README.md)
- [week 11 nats jetstream pulsar exactly once](curriculum/week-11-nats-jetstream-pulsar-exactly-once/README.md)
- [week 12 temporal and workflow orchestration](curriculum/week-12-temporal-and-workflow-orchestration/README.md)
- [week 13 postgres at scale replication partitioning](curriculum/week-13-postgres-at-scale-replication-partitioning/README.md)
- [week 14 change data capture cqrs event sourcing](curriculum/week-14-change-data-capture-cqrs-event-sourcing/README.md)
- [week 15 modern lakehouse iceberg trino olap](curriculum/week-15-modern-lakehouse-iceberg-trino-olap/README.md)
- [week 16 caching redis memcached dragonfly](curriculum/week-16-caching-redis-memcached-dragonfly/README.md)
- [week 17 observability opentelemetry prometheus thanos tempo loki](curriculum/week-17-observability-opentelemetry-prometheus-thanos-tempo-loki/README.md)
- [week 18 reliability sli slo error budgets](curriculum/week-18-reliability-sli-slo-error-budgets/README.md)
- [week 19 multi region active active active passive](curriculum/week-19-multi-region-active-active-active-passive/README.md)
- [week 20 crdts in production](curriculum/week-20-crdts-in-production/README.md)
- [week 21 zero trust networking spiffe spire opa](curriculum/week-21-zero-trust-networking-spiffe-spire-opa/README.md)
- [week 22 chaos engineering and the gameday](curriculum/week-22-chaos-engineering-and-the-gameday/README.md)
- [week 23 contract testing property based testing capacity planning](curriculum/week-23-contract-testing-property-based-testing-capacity-planning/README.md)
- [week 24 capstone integration architecture review demo](curriculum/week-24-capstone-integration-architecture-review-demo/README.md)

## In this course

- **Community** — [community/](community/)
- **Curriculum** — [curriculum/](curriculum/)
- **Projects** — [projects/](projects/)
- **Resources** — [resources/](resources/)
- **Past sessions** — [past-sessions/](past-sessions/)

<!-- CCWW:AUTO-INDEX:END -->
