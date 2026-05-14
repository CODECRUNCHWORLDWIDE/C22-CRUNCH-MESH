# C22 · Crunch Mesh — Charter

This document explains the editorial decisions behind Crunch Mesh. The syllabus describes what the course teaches; this charter explains why the course exists and why it is shaped the way it is. The parent charter at `../CRUNCH-LABS-CHARTER.md` governs the Crunch Labs tier as a whole; the present document covers Mesh-specific commitments.

---

## Why distributed systems, as a discipline

There is a gap in industry hiring that has widened over the last decade. Senior backend engineers can build a service. Many of them can build an API that handles meaningful traffic, runs on Kubernetes, and serves a real product. Far fewer can build a platform — a set of services that compose into a coherent system, survive a region outage, keep their contracts honest across teams, and remain debuggable at 3 AM during an incident with a partial network partition.

The difference between those two engineers is not seniority. It is exposure to a body of knowledge — consistency models, consensus, replication, mesh networking, event-driven design, observability, chaos engineering — that is rarely taught in any single coherent place. It is learned by lucky engineers at the few companies where the platform team writes internal documentation worth reading, and by unlucky engineers in postmortems.

Crunch Mesh exists to teach that body of knowledge intentionally, in 24 weeks, on open infrastructure, with the same rigor that a graduate seminar in operating systems would apply to its subject. Distributed systems is a discipline. We treat it as one.

---

## Why 24 weeks

A twelve-week course in this subject is dishonest. The theory alone — CAP, PACELC, FLP, the consensus literature, CRDTs, vector clocks, leases — takes four focused weeks. After that comes a six-week phase on service mesh and eventing, because Istio, Kafka, NATS, and Temporal each demand a week of their own to operate competently rather than merely demo. The data and reliability phase needs another six weeks because CDC, CQRS, the lakehouse, caching, observability, and SLO discipline are individually deep. And the final phase, multi-region and chaos and capstone, needs six more weeks of running a real system across two regions through real drills.

We considered every shorter format. They each forced one of two compromises: cut the theory phase (producing engineers who can wire tools but cannot defend a design under cross-examination), or cut the operate-it-for-real phase (producing engineers who can pass a whiteboard interview but have never failed a chaos drill). Neither is acceptable for a Crunch Labs tier course aimed at staff-track outcomes.

Twenty-four weeks is the smallest container that holds the work honestly.

---

## Topic ordering — and why most courses get it backwards

The order is: **theory → single-service production → multi-service → multi-region.**

Most short courses invert this. They start with `docker-compose up kafka` and patch theory in by reference. Students learn the shapes of the tools and never the constraints those tools were designed to navigate.

Our order is defended by the structure of distributed systems itself. CAP and PACELC tell you what a single service can promise; you cannot reason about consistency in a service-to-service interaction until you can reason about it in one node. Conway's law and bounded contexts tell you where to draw service lines; you cannot draw a service mesh until you know what each service is for. Event-driven design assumes a working understanding of idempotency and replay semantics; those require the consensus and replication literature first. Multi-region active-active is the integration test of every earlier topic, which is why it sits at the end.

This ordering also matches the way the discipline actually developed. Lamport's 1978 paper preceded Kafka by 33 years. We honor the literature's chronology because it captures a real dependency graph.

---

## Open-source-first

Every tool taught in Crunch Mesh is open source under a recognized license. Kubernetes, Istio, Linkerd, Envoy, Postgres, Debezium, Kafka, Redpanda, NATS, Temporal, gRPC, OpenTelemetry, Prometheus, Thanos, Grafana, Tempo, Loki, Trino, Iceberg, OPA, SPIFFE/SPIRE. We do not teach proprietary substitutes. We do compare them — engineers should know what AWS App Mesh, MSK, EventBridge, and DynamoDB do and how they relate to the OSS originals — but the curriculum is built on the open versions, because:

1. Service mesh, eventing, and observability are OSS-first ecosystems. The reference implementations and the canonical documentation are open.
2. A graduate with deep Istio + Kafka + Postgres + OpenTelemetry fluency can pick up the managed equivalent in a week. The reverse is not true.
3. Open infrastructure means students can run real systems on their laptops and small cloud bills, not on credits that expire.
4. Open licenses are durable. A course built on a vendor's free tier is a course with a half-life.

---

## Relationship to other Crunch tracks

- **C16 Pro Backend** is the direct feeder. C16 teaches students to build and operate a single backend service to production standards. Crunch Mesh assumes that work is done. A graduate of C16 who took the C22 placement quiz should pass cleanly.
- **C15 Crunch DevOps** is the second feeder. We assume Docker, Kubernetes basics, CI/CD, and Terraform are not new. Students missing this background should take C15 first or pick it up in parallel; we do not re-teach it.
- **C18 Crunch GCP** and **C19 Crunch AWS** are complementary. A cloud-fluent engineer arriving from C18 or C19 will find the multi-region phase faster. A graduate of C22 who then takes C18 or C19 will treat managed services as a vocabulary translation rather than a new mental model.
- **C13 Hack the Interview** is the recommended successor for graduates targeting staff-track loops. The career pack in C22 prepares the technical rounds; C13 covers the rest of the loop.
- **C5 Crunch AI & Data Science** and **C6 Cybersecurity Crunch** are common follow-ons. Crunch Mesh graduates are well-placed for both: the data side because they already operate event streams and a lakehouse, the security side because they already operate zero-trust networking and policy-as-code.

---

## Our position on LLM-branded "AI architecture"

We do not teach ChatGPT, Copilot Workspace, or any vendor-branded "AI architecture" as part of this track. This is a considered position, not an oversight.

Distributed systems theory predates the LLM era by half a century. CAP, FLP, Raft, Paxos, CRDTs, vector clocks, and consensus are invariant to whether the workload is serving an LLM, a payment ledger, or a video feed. An engineer who has internalized the theory will design correctly for an LLM-serving system without being taught LLM-serving as a separate genre. An engineer who has only learned "LLM architecture" patterns will reproduce well-known anti-patterns when the workload changes.

Crunch Mesh graduates routinely build LLM-serving backends in their first six months on the job. They do it well because they understand backpressure, queueing, autoscaling on token-per-second SLIs, idempotent retries on streaming completions, and tail-latency discipline. None of those topics requires a brand name. The course teaches the substrate; the brand-name layer is a one-week intern project on top of it.

We may add a focused module on LLM-serving infrastructure (vLLM, Triton, KServe, Ray Serve) in a future revision. If we do, it will be framed as an application of distributed-systems theory, not as an exception to it.

---

## License and signature

This charter is released under GPL-3.0, identical to the rest of the C22 materials. It is owned by the Code Crunch Labs Crunch Mesh track and is binding on instructors, contributors, and cohort operators.

Signed,
*The Code Crunch Labs editorial team — Mesh track*
