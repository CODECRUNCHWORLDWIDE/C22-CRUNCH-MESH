# Week 19 — Resources

Every resource here is **free** and **open**. Postgres is open-source with openly published docs; the Kubernetes, CoreDNS, and DR-pattern material is vendor-documentation or public engineering writing. The cloud providers' DR whitepapers are referenced for their *frameworks* (RTO/RPO definitions, the failover patterns) even though the lab runs entirely on local Kind — the concepts are vendor-neutral and the math is the same whether the second region is across the room or across an ocean.

This week targets **Postgres 16+** (logical replication is mature; `pg_stat_replication` and the publication/subscription model are stable) and **Kind 0.24+** with two clusters. When a link is to `latest`, the concepts are stable; only occasional flag names move.

## Required reading (work it into your week)

- **AWS — Disaster recovery options in the cloud** — the canonical taxonomy: backup-and-restore, pilot light, warm standby, active-active (multi-site). Read it Monday for the RTO/RPO framework even if you never touch AWS:
  <https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html>
- **PostgreSQL — Logical replication** — publications, subscriptions, the replication model you'll run across regions:
  <https://www.postgresql.org/docs/current/logical-replication.html>
- **PostgreSQL — High availability, load balancing, and replication** — the chapter that frames synchronous vs asynchronous and what each buys:
  <https://www.postgresql.org/docs/current/high-availability.html>
- **Google SRE Book — Managing critical state (distributed consensus)** — why quorum across regions costs a round-trip and why an even member count is a trap:
  <https://sre.google/sre-book/managing-critical-state/>
- **Brendan Burns / Kubernetes — multi-cluster patterns** — the routed-control-plane idea you simulate with two Kind clusters:
  <https://kubernetes.io/docs/concepts/cluster-administration/networking/>

## The replication pieces (skim, then refer back)

- **PostgreSQL — `pg_stat_replication`** — the view that gives you replication lag, the number that *is* your RPO at failover:
  <https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW>
- **PostgreSQL — `synchronous_commit`** — the knob that trades write latency for RPO (`off`/`local`/`remote_write`/`remote_apply`):
  <https://www.postgresql.org/docs/current/runtime-config-wal.html#GUC-SYNCHRONOUS-COMMIT>
- **PostgreSQL — Promoting a standby (`pg_ctl promote` / `pg_promote()`)** — the failover primitive:
  <https://www.postgresql.org/docs/current/warm-standby.html#STANDBY-SERVER-OPERATION>
- **Patroni** — the production HA/failover controller for Postgres; read it for *how* automated failover fences the old primary:
  <https://patroni.readthedocs.io/en/latest/>

## Geo-routing and DNS

- **CoreDNS** — the DNS server you'll run in the lab to simulate GeoDNS/health-checked records:
  <https://coredns.io/manual/toc/>
- **AWS Route 53 — routing policies** — read for the *taxonomy* (latency-based, geolocation, failover, weighted) even if you don't use it:
  <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html>
- **Cloudflare — what is anycast** — the one-IP-many-locations model and how the network routes to the nearest:
  <https://www.cloudflare.com/learning/cdn/glossary/anycast-network/>
- **The DNS TTL and failover tax** — any authoritative DNS doc: a record cached for TTL means clients hit the dead region for up to TTL after cutover. Keep this in mind when you set TTLs on failover-critical records.

## Data gravity and residency

- **GDPR — data localization / cross-border transfer (overview)** — why some data legally *cannot* leave a region, turning geography into a correctness constraint:
  <https://gdpr.eu/data-transfers/>
- **"Data gravity" (Dave McCrory's original framing)** — why data attracts services and is the hardest thing to move; search for the original blog posts and the follow-on writing.
- **Designing Data-Intensive Applications (Kleppmann), Ch. 5 (Replication) & Ch. 9 (Consistency and Consensus)** — the canonical treatment of leader-based replication, replication lag, and the consensus that quorum-across-regions requires. The book is widely available; read these two chapters this week.

## Failover and the operational story

- **Google SRE Workbook — Implementing SLOs / Canarying releases** — the error-budget framing that RTO/RPO are the multi-region expression of:
  <https://sre.google/workbook/implementing-slos/>
- **The "fail-back is harder than fail-over" lesson** — most DR writeups bury it: bringing the recovered region back as a *replica* first (re-sync), then handing writes back, is where split-brain hides. The challenge this week is exactly this.

## Tools you'll use this week

- **`kind`** — two clusters (`kind create cluster --name region-a` / `--name region-b`) standing in for two regions; you'll add a simulated cross-region latency.
- **`kubectl`** — with two contexts (`kubectl config use-context kind-region-a`), apply manifests to each region, read pod status, drive the failover.
- **`psql`** — create publications/subscriptions, read `pg_stat_replication`, promote a replica.
- **CoreDNS** (or a tiny resolver) — simulate health-checked geo-routing and the TTL tax.
- **`tc` / a latency-injection sidecar** — add the cross-region delay so the speed-of-light floor is visible in your numbers.
- **A small Python load driver** (exercise 3) — drives writes during failover and computes the measured RTO/RPO.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Active-active** | Multiple regions accept writes simultaneously; buys capacity + low write-RTO, costs a conflict-resolution problem. |
| **Active-passive** | One region writes (active), others stand by (passive) and take over on failover; simpler, but standby is idle and there's a cutover step. |
| **RTO** | Recovery Time Objective — how long until service is restored after a failure. Lower = more expensive. |
| **RPO** | Recovery Point Objective — how much data you can afford to lose, measured as the age of the last replicated write. RPO≈0 needs synchronous replication. |
| **Synchronous replication** | The primary waits for the replica to acknowledge before the write commits. RPO≈0, but pays the cross-region round-trip on every commit. |
| **Asynchronous replication** | The primary commits locally and ships the change after. Fast writes, but RPO = the replication lag at the moment of failure. |
| **Replication lag** | How far behind the replica is; at failover, this is the data you lose. Your RPO *is* your lag. |
| **Quorum** | A majority of voting members must agree to commit; across regions this costs an inter-region round-trip per commit. |
| **Split-brain** | Two regions both believe they're primary and both accept writes — the failure mode fencing prevents. |
| **Fencing** | Making the old primary unable to accept writes after you've promoted a new one — the split-brain guard. |
| **Geo-routing** | Directing clients to a region by geography/latency/health, via DNS (GeoDNS), anycast, or GSLB. |
| **Anycast** | One IP announced from many locations; the network routes each client to the nearest. |
| **DNS TTL tax** | Clients cache a DNS record for TTL seconds, so they keep hitting a dead region for up to TTL after failover — a direct term in effective RTO. |
| **Data gravity** | Data attracts the services that use it and resists being moved; the reason multi-region is a *data* problem, not a compute one. |
| **Data residency** | A legal requirement that certain data stay in certain regions (e.g. EU data in the EU) — geography as a correctness constraint. |
| **Read-local/write-primary** | The pragmatic default: serve reads from the local region's replica, send all writes to the single primary region. |

---

*If a link 404s, please open an issue so we can replace it.*
