# C22 · Crunch Mesh — Syllabus

**Length:** 24 weeks · **Estimated effort:** ~864 hours full-time-equivalent · **Cohort cadence:** semester · **Tier:** Crunch Labs · **License:** GPL-3.0

This syllabus is the contract between the cohort and the curriculum. Every week lists its topics, primary lecture, hands-on lab, and the named skills a graduate earns. Weeks are not interchangeable. The ordering — theory before code, single-service before multi-service, multi-service before multi-region — is intentional and is defended in `CHARTER.md`.

---

## Phase 1 · Theory and single-service production (weeks 1–6)

The first six weeks deliberately resist the urge to write a service. Distributed-systems engineering is dominated by reasoning errors more than coding errors, and the corrective is reading. By week 7 you will have a single hardened service in production, but you will have arrived there with the conceptual scaffolding to know why each decision was made.

### Week 1 — The literature: CAP, PACELC, and FLP

- **Topics:** CAP theorem; PACELC; FLP impossibility result; what "consistency" actually means (linearizable, sequential, causal, eventual); the difference between safety and liveness properties.
- **Lecture:** "What Brewer said and what Brewer meant." Close reading of the original CAP paper and Daniel Abadi's PACELC reformulation.
- **Hands-on lab:** Build a two-node toy register in Go with a simulated network partition. Demonstrate the three CAP regimes (CP, AP, and the impossibility of CA under partition) experimentally.
- **Skills earned:** Reading distributed-systems literature critically; articulating consistency models without conflating them; experimentally exhibiting CAP regimes.

### Week 2 — Time, order, and consensus

- **Topics:** Physical vs logical clocks; Lamport timestamps; vector clocks; happens-before relation; leases and fencing tokens; Raft (deeply); Paxos (overview); ZooKeeper, etcd, and Consul as Raft consumers.
- **Lecture:** "Time is a flat lie." Lamport 1978, Raft (Ongaro & Ousterhout), and the fencing-token chapter from *Designing Data-Intensive Applications*.
- **Hands-on lab:** Implement vector clocks and a Lamport-timestamped chat log in Python. Then deploy a 3-node etcd cluster on Kind and exercise leader election by killing nodes.
- **Skills earned:** Reasoning about event ordering without wall-clocks; operating a Raft-backed coordination service; recognizing fencing-token bugs in lock APIs.

### Week 3 — CRDTs, eventual consistency, and conflict resolution

- **Topics:** State-based vs operation-based CRDTs; G-counter, PN-counter, OR-set, LWW-register; Riak, Redis CRDTs, AntidoteDB; the "convergent" guarantee; when CRDTs are the right answer and when they are not.
- **Lecture:** "What 'eventually' should mean." Shapiro et al. on CRDTs; the Bayou paper; case study of Riak in production at Bet365.
- **Hands-on lab:** Implement an OR-set CRDT for a shopping cart in Rust. Demonstrate convergence after a simulated 3-way partition heal. Measure metadata growth.
- **Skills earned:** Designing CRDT-backed state; reasoning about metadata cost; knowing when LWW is a footgun.

### Week 4 — Microservice fundamentals and decomposition

- **Topics:** Bounded contexts (DDD); Conway's law and the inverse Conway maneuver; service decomposition heuristics (verb-vs-noun, transaction boundaries, change-frequency clustering); anti-patterns (distributed monolith, shared database, the chatty mesh, the entity service).
- **Lecture:** "How to draw the lines." Sam Newman on decomposition; Eric Evans on bounded contexts; the Amazon two-pizza-team origin story re-examined.
- **Hands-on lab:** Decompose a provided 40 kLOC monolithic e-commerce Django app into a candidate service topology. Produce a written decomposition memo with three rejected alternatives.
- **Skills earned:** Drawing service boundaries with discipline; writing an architecture memo; recognizing distributed-monolith smell in code review.

### Week 5 — API contracts: gRPC, Protobuf, and the typed surface

- **Topics:** Protobuf wire format and schema evolution rules; gRPC unary, streaming, bidi; gRPC-Web for browser clients; gRPC interceptors; reflective vs static stubs; comparing to REST, GraphQL (and Federation), and AsyncAPI for events.
- **Lecture:** "Why a typed contract is a moral position." The Protobuf style guide; gRPC's HTTP/2 substrate; the cost of REST drift.
- **Hands-on lab:** Define a `cart.v1` Protobuf contract. Generate Go and Python stubs. Build a Go server and a Python client. Add streaming endpoints. Wire gRPC reflection and use `grpcurl`.
- **Skills earned:** Authoring Protobuf with backward and forward compatibility; running polyglot gRPC; choosing between REST, gRPC, and GraphQL with evidence.

### Week 6 — The single hardened service

- **Topics:** Twelve-factor reviewed for service authors; structured logging; graceful shutdown; readiness vs liveness probes; configuration hierarchy; secrets via environment vs SPIFFE; baseline OpenTelemetry instrumentation; the runbook as a deliverable.
- **Lecture:** "Production readiness is a checklist, not a vibe." Walking the Crunch Mesh production-readiness review.
- **Hands-on lab:** Take last week's `cart` service from skeleton to production-ready: structured JSON logs, OpenTelemetry traces and metrics, k8s manifests with probes, a Helm chart, and a runbook covering five named failure modes.
- **Skills earned:** Passing a production-readiness review; writing a runbook other engineers can use; baseline observability instrumentation.

---

## Phase 2 · Service mesh and eventing (weeks 7–12)

Now there is more than one service. Phase 2 is about the network — the substrate that connects services and the events that flow through them.

### Week 7 — Service-to-service: BFFs, gateways, and Envoy

- **Topics:** API gateway vs service mesh ingress; Envoy architecture (filters, listeners, clusters, EDS/CDS/LDS/RDS); Kong and Tyk briefly; the BFF (backend-for-frontend) pattern; gRPC-Web vs Connect; rate limiting and quota.
- **Lecture:** "Envoy is the load balancer for the next twenty years." A close read of the Envoy threading model.
- **Hands-on lab:** Stand up Envoy as an ingress in front of two services. Configure rate limiting, retries with hedging, and a per-route circuit breaker. Add a BFF in Go for a mobile client.
- **Skills earned:** Configuring Envoy at the YAML and CRD level; designing a BFF; recognizing when a gateway is enough and a mesh is overkill.

### Week 8 — Istio in production

- **Topics:** Istio architecture (istiod, sidecar injection, ambient mode); mTLS by default; AuthorizationPolicy and PeerAuthentication; VirtualService and DestinationRule; traffic shifting and weighted canary; fault injection at the mesh layer.
- **Lecture:** "Istio in anger." What the docs don't tell you. The cost of sidecars. Ambient mesh and why it exists.
- **Hands-on lab:** Install Istio on a Kind cluster. Migrate the cart and inventory services into the mesh. Enable mTLS strict. Roll out a v2 of cart with 10/90 weighted traffic, then 50/50, then 100/0. Inject a 200 ms latency fault and observe in Kiali.
- **Skills earned:** Operating Istio; performing a mesh-driven canary; debugging sidecar surprises.

### Week 9 — Linkerd and Cilium service mesh — the alternatives

- **Topics:** Linkerd architecture and the Rust-based linkerd2-proxy; sidecar vs sidecar-less debate; Cilium service mesh on eBPF; cost and complexity comparisons; when each one wins.
- **Lecture:** "Three meshes, three philosophies." Honest comparison against Istio.
- **Hands-on lab:** Reinstall the cart topology on Linkerd. Measure p50/p99 latency overhead vs Istio. Repeat on Cilium service mesh. Write a 1-page decision memo recommending one of the three to a hypothetical 200-engineer org.
- **Skills earned:** Comparing meshes empirically; writing an architectural decision record (ADR) that defends a position.

### Week 10 — Eventing: Kafka and Redpanda

- **Topics:** Kafka log abstraction; partitions, offsets, consumer groups; ISR and the replication protocol; Redpanda's C++ rewrite and the Raft-per-partition model; retention strategies; compaction; key design.
- **Lecture:** "The log is the truth." A re-read of Jay Kreps's "The Log" essay alongside the Kafka Improvement Proposals.
- **Hands-on lab:** Deploy a 3-broker Kafka cluster on Kind via Strimzi. Build a Go producer and a Python consumer for `order.placed.v1`. Repeat on Redpanda. Benchmark throughput. Demonstrate offset reset and the dual-consumer-group fan-out pattern.
- **Skills earned:** Operating Kafka and Redpanda; choosing partition keys; reasoning about retention; debugging consumer lag.

### Week 11 — NATS JetStream, Pulsar, and exactly-once semantics

- **Topics:** NATS core vs JetStream; subject hierarchies; Pulsar's tiered storage; idempotency keys; transactional outbox vs Kafka transactions; the impossibility (and pragmatic possibility) of exactly-once.
- **Lecture:** "Exactly-once is a contract, not a primitive." How Kafka EOS, NATS JetStream, and Temporal each model it.
- **Hands-on lab:** Implement the outbox pattern in Postgres for the cart service. Stream changes via Debezium to Kafka. Build an idempotent consumer in Rust that survives duplicate delivery. Verify with chaos: kill the consumer mid-batch, restart, re-process. Show zero double-charge.
- **Skills earned:** Authoring outbox patterns; building idempotent consumers; reasoning about EOS vs at-least-once vs at-most-once.

### Week 12 — Temporal and workflow orchestration

- **Topics:** Temporal architecture (frontend, history, matching, worker); workflow vs activity; deterministic replay; signals, queries, child workflows; orchestration vs choreography for sagas; AWS Step Functions and Azure Durable Functions critiques; Cadence as Temporal's ancestor.
- **Lecture:** "When orchestration wins." Why a centralized workflow engine is sometimes the simpler answer.
- **Hands-on lab:** Replace the cart-checkout choreography (built last week) with a Temporal workflow in Go. Implement a saga with compensation: reserve inventory, charge payment, ship; with compensation on any failure. Demonstrate worker restart mid-workflow with zero state loss.
- **Skills earned:** Authoring Temporal workflows; designing sagas; explaining when orchestration is the right tool.

---

## Phase 3 · Data and reliability (weeks 13–18)

Services without data discipline drift into chaos. Phase 3 is about the storage tier, the read-path, and the operational discipline that keeps the system honest under load.

### Week 13 — Postgres at scale: replication and partitioning

- **Topics:** Postgres logical vs physical replication; partitioning (declarative range/list/hash); HOT updates and bloat; pg_stat_statements; pgBouncer in transaction vs session pooling mode; Citus and CockroachDB as horizontal alternatives.
- **Lecture:** "Postgres can take you further than you think." When to shard, when not to.
- **Hands-on lab:** Build a Postgres primary with two logical replicas. Partition the `orders` table by month. Generate 50 M synthetic rows. Tune `pgBouncer`. Measure query latency before and after partitioning.
- **Skills earned:** Operating Postgres replication; choosing partition strategies; tuning connection pools.

### Week 14 — Change data capture, CQRS, and event sourcing

- **Topics:** Debezium connectors; CDC vs dual-write; CQRS in earnest (command model + read model); event sourcing (and its costs); materialized views; the difference between an event-sourced aggregate and an event-driven service.
- **Lecture:** "CDC is the gateway drug to event-driven architecture." Why Debezium changed the conversation.
- **Hands-on lab:** Wire Debezium to the Postgres primary. Stream `orders` changes to Kafka. Build a read-model service in Rust that maintains a denormalized search view in Elasticsearch. Build a second consumer that writes the same events to an Iceberg table.
- **Skills earned:** Operating Debezium; designing CQRS read models; distinguishing event-sourcing from event-driven.

### Week 15 — The modern lakehouse: Iceberg, Trino, and OLAP

- **Topics:** Row-store vs column-store; OLAP vs OLTP boundaries; Apache Iceberg table format; Trino as a federated query engine; the role of dbt; when to push compute to the lakehouse and when to stay in Postgres.
- **Lecture:** "The lakehouse is a contract, not a product." Iceberg's spec over Delta's marketing.
- **Hands-on lab:** Stand up MinIO as S3-compatible storage. Configure Iceberg via Nessie catalog. Query the orders-events stream with Trino. Build a dbt model that produces a daily revenue rollup. Demonstrate time-travel queries on Iceberg.
- **Skills earned:** Operating Iceberg + Trino; writing analytical SQL against event streams; reasoning about OLTP/OLAP boundaries.

### Week 16 — Caching: Redis, Memcached, Dragonfly

- **Topics:** Cache patterns (look-aside, read-through, write-through, write-back); stampede protection (request coalescing, probabilistic early expiration); invalidation strategies; Redis vs Memcached vs Dragonfly (and the licensing change saga); Redis Cluster's hash slots.
- **Lecture:** "Cache invalidation is hard because the abstraction is leaky." The two hardest problems revisited.
- **Hands-on lab:** Add a Redis cache to the cart-read path. Implement look-aside with request coalescing. Induce a stampede with `k6`; show the fix. Migrate to Dragonfly; benchmark.
- **Skills earned:** Designing cache layers that survive failure; benchmarking caches; reasoning about invalidation.

### Week 17 — Observability: OpenTelemetry, Prometheus, Thanos, Tempo, Loki

- **Topics:** OpenTelemetry SDKs in Go, Python, Rust; context propagation across HTTP, gRPC, Kafka; semantic conventions; metrics (counters, gauges, histograms); exemplars linking metrics to traces; Prometheus + Thanos for long-term metric storage; Tempo for traces; Loki for logs; Grafana as the single pane.
- **Lecture:** "The three pillars, correlated." Why exemplars matter.
- **Hands-on lab:** Instrument the entire cart topology in OpenTelemetry. Stand up Prometheus + Thanos, Tempo, Loki, Grafana. Build a Grafana dashboard showing RED metrics with exemplars that jump to traces. Verify trace continuity across a Kafka boundary.
- **Skills earned:** End-to-end OpenTelemetry instrumentation; building exemplar-linked dashboards; debugging via correlated traces.

### Week 18 — Reliability: SLI/SLO, error budgets, and the patterns

- **Topics:** Defining SLIs that mean something; SLOs and error budgets; the Google SRE workbook patterns; circuit breakers (resilience4j, Polly, sony/gobreaker); bulkheads; timeouts; retries with jitter and budget; backpressure; load shedding; admission control; autoscaling (HPA, KEDA on Kafka lag); the Universal Scalability Law and Little's law; tail-latency (p99 vs p99.9 vs p99.99).
- **Lecture:** "SLOs are a negotiation tool, not a ceiling." How to defend an error budget against product pressure.
- **Hands-on lab:** Define three SLIs and SLOs for the cart system. Implement a circuit breaker in Go around the payment dependency. Add KEDA autoscaling on Kafka consumer lag. Load test with `k6` to find the saturation point. Measure p99 vs p99.9 with HDR histograms.
- **Skills earned:** Authoring SLOs; implementing the named reliability patterns; finding and naming the saturation point of a system.

---

## Phase 4 · Production and capstone (weeks 19–24)

The final phase compresses everything into a single running system that lives across regions, defends itself, and submits to chaos drills with a postmortem.

### Week 19 — Multi-region: active-active, active-passive, and the choices

- **Topics:** Active-active vs active-passive; quorum across regions; cross-region replication latency budgets; geo-routing (DNS, anycast, GeoDNS, GSLB); session affinity considerations; the data-gravity problem.
- **Lecture:** "Two regions is harder than one region twice." The hidden costs of active-active.
- **Hands-on lab:** Run two Kind clusters representing two regions. Connect via a routed control plane. Replicate Postgres logically across regions. Route reads locally, writes to primary. Demonstrate failover with a 60-second RTO target.
- **Skills earned:** Standing up a two-region topology; measuring replication lag; performing a controlled failover.

### Week 20 — CRDTs in production and conflict resolution

- **Topics:** Production-grade CRDT stacks; bringing week 3 theory to bear; choosing between LWW and merge semantics for cart, inventory, and counters; vector-clock-driven conflict resolution at the application layer.
- **Lecture:** "When eventual consistency is the right consistency." Picking the right CRDT for the right field.
- **Hands-on lab:** Promote the cart service to active-active across both Kind regions using an OR-set CRDT. Partition the regions for 5 minutes. Heal. Verify convergence.
- **Skills earned:** Running a CRDT-backed service across regions; reasoning about per-field consistency models.

### Week 21 — Zero-trust networking: SPIFFE, SPIRE, OPA

- **Topics:** SPIFFE workload identities; SPIRE deployment; SVID issuance; rotating mTLS without service downtime; OPA / Gatekeeper for policy-as-code at admission; Kyverno alternatives.
- **Lecture:** "Identity is the new perimeter." Why SPIFFE is the right primitive.
- **Hands-on lab:** Deploy SPIRE in both clusters. Issue SVIDs to every cart/inventory/payment service. Wire mTLS via Istio with SPIFFE identities. Write OPA policies enforcing namespace-level access. Verify with a deliberate violation.
- **Skills earned:** Operating SPIFFE/SPIRE; writing OPA policy; closing the zero-trust loop.

### Week 22 — Chaos engineering and the gameday

- **Topics:** Chaos engineering principles (Netflix's 4 principles); chaos-mesh, Litmus, gremlin (briefly); building a gameday playbook; blameless postmortems; the "five whys" debate.
- **Lecture:** "Chaos is a discipline of curiosity." Running a real gameday.
- **Hands-on lab:** Install chaos-mesh on both clusters. Author six experiments: pod kill, network partition, packet loss, CPU stress, disk fill, broker loss. Run a 90-minute gameday. Write a blameless postmortem for each non-trivial finding.
- **Skills earned:** Authoring chaos experiments; running a gameday; writing a publishable postmortem.

### Week 23 — Contract testing, property-based testing, and capacity planning

- **Topics:** Contract testing with Pact (consumer-driven contracts); property-based testing (Hypothesis in Python, gopter in Go, proptest in Rust); fault-injection testing at the unit level; capacity planning (USL, Little's Law, queueing); cost-aware design.
- **Lecture:** "The tests that matter are the ones at the boundary." Why contract tests close the polyglot gap.
- **Hands-on lab:** Add a Pact contract test suite covering cart ↔ inventory and cart ↔ payment. Publish to a Pact broker. Add property-based tests around the CRDT merge. Run a capacity-planning exercise and produce a one-page memo.
- **Skills earned:** Authoring Pact contracts; writing property-based tests; defending a capacity model on paper.

### Week 24 — Capstone integration, architecture review, and demo

- **Topics:** Final integration; architecture review (mock staff design review); demo recording; postmortem publication.
- **Lecture:** "How to defend an architecture." The staff-engineer review format.
- **Hands-on lab:** Final week is capstone-only. Capstone defense on Friday in front of the cohort and two external reviewers.
- **Skills earned:** Defending a system you built; presenting at staff-engineer level; closing the course.

---

## Assessment matrix

| Component | Weight | Cadence | Format |
|---|---|---|---|
| Weekly quizzes | 10% | 24 quizzes, 30 minutes each | Multiple-choice + short answer; auto-graded |
| Weekly labs | 30% | 23 labs (week 24 is capstone-only) | Rubric-graded by TA; PR-style review |
| Midterm architecture-review essay | 10% | End of week 12 | 2,500-word written architecture review of a public open-source distributed system (Mastodon, Discourse, Sentry self-hosted, etc.) |
| Gameday drill | 10% | Week 22 | Live 90-minute drill; postmortem grades the writeup |
| Mock staff system-design interview | 10% | Week 23 | 60-minute oral interview with an external reviewer; scored on rubric |
| Capstone | 30% | Weeks 21–24 | Single polyglot system; see below |

Passing requires ≥ 70% overall and ≥ 60% on each capstone deliverable.

---

## Capstone — Polyglot Marketplace Backbone

**Brief.** Build and operate the backend platform for a fictional online marketplace, designed and run as a real system across two regions for the final four weeks of the course.

**Required services and their languages.**

- **`cart-service` (Rust):** OR-set CRDT shopping cart, multi-region active-active.
- **`inventory-service` (Go):** authoritative stock counts, single-writer-per-SKU with leases.
- **`payment-service` (Go):** Temporal workflow for charge / refund / reversal, with idempotency.
- **`order-service` (Python):** orchestrator that pulls cart, reserves inventory, drives payment, and emits `order.placed.v1`.
- **`search-service` (Python):** read-model fed by Debezium CDC into Elasticsearch.
- **`analytics-service` (Python/dbt):** Iceberg-on-Trino daily and hourly rollups.
- **`bff-web` (Go) and `bff-mobile` (Go):** thin BFFs over the gRPC backbone.

**Required substrate.**

- gRPC + Protobuf everywhere, with `cart.v1`, `inventory.v1`, `payment.v1`, `order.v1` packages versioned independently.
- Kafka event spine with exactly-once consumers via outbox + idempotency keys.
- Temporal cluster for long-running workflows.
- Postgres primary per region with logical replication and Debezium CDC.
- Istio service mesh with mTLS strict, SPIFFE identities via SPIRE, OPA admission policy.
- Progressive delivery: weighted canary, automatic rollback on SLO breach.
- Two-region active-active deployment (Kind locally or two GKE/EKS clusters).
- Full OpenTelemetry pipeline: traces to Tempo, metrics to Prometheus + Thanos, logs to Loki, Grafana dashboards with exemplars.
- Published Pact contract test suite, with the broker running in-cluster.

**Required deliverables.**

1. The running system (two-region active-active) with all services healthy at demo time.
2. A 2,000-word architecture document with C4-style diagrams (system context, container, component for two key services).
3. A 12-minute recorded demo video covering: architecture walkthrough, a live deploy with weighted canary, a Grafana dashboard tour ending in a trace-to-log jump, and the cart-CRDT convergence demo across a simulated partition.
4. **Two chaos-drill postmortems** (mandatory):
   - **Drill A — Region failover.** Kill the primary region during a 1k-RPS load test. Document the impact, the recovery, and the lessons.
   - **Drill B — Kafka broker loss.** Lose a Kafka broker mid-traffic. Demonstrate that the exactly-once consumers do not double-process, and that the outbox guarantees integrity.
5. A 6-page runbook covering five named failure modes (region loss, broker loss, Postgres primary failure, Temporal worker outage, certificate expiry).
6. A published Pact broker URL with green contracts.

**Grading rubric.** Functional correctness (25%), architectural defensibility (25%), observability quality (15%), chaos-drill postmortems (15%), runbook (10%), demo and writeup (10%).

---

## Career engineering pack

Crunch Mesh graduates leave with a curated career package targeted at the staff-track loop.

- **Staff-track interview prep.** Twelve mock system-design problems at FAANG scale: news feed, ride-hailing dispatch, payments ledger, ad auction, real-time gaming presence, etc. Each comes with a worked solution and a rubric. Two live mocks with external reviewers are included.
- **Distributed-systems oral quizzing.** A 40-question oral quiz bank (CAP, PACELC, FLP, Raft, Paxos, CRDTs, vector clocks, sagas, EOS, OpenTelemetry semantics). Used as flashcards during weeks 20–24.
- **On-call narrative.** Three written narratives in STAR format from your gameday and capstone work. Reviewed for use in behavioral rounds.
- **Production runbook.** Your capstone runbook is graded and revised into a portfolio-quality artifact.
- **Portfolio.** GitHub repository for the capstone with a polished README, architecture diagrams, demo video, and postmortems. Linked from `codecrunchworldwide.vercel.app/portfolio`.
- **References.** Cohort instructors will provide one written technical reference for graduates who score ≥ 85% overall.

---

## License

GPL-3.0. See `LICENSE`. All material here — slides, labs, rubrics, capstone spec — is released under the same license. Forks and remixes are welcome; attribution is required.
