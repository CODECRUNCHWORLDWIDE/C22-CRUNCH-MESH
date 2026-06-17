# Week 15 — Challenges

The exercises drill the mechanics. **The challenge makes you the data architect.** You're handed six real analytical queries and you have to place each one correctly on the OLTP/OLAP boundary — Postgres, lakehouse, or federate — with *evidence*, and defend each call the way you'd defend it to a staff engineer who disagrees.

## Index

1. **[Challenge 1 — Place six queries on the boundary](./challenge-01-place-six-queries.md)** — six queries spanning the spectrum from point lookup to two-year cohort analysis. For each, decide where it runs (Postgres / lakehouse / federate / dbt rollup), back the call with the four-axis framework and a measurement, and identify the two queries that are *traps* — the one that looks like OLAP but belongs in Postgres, and the one that looks like a Postgres query but will quietly destroy your primary. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the Phase 3 architecture review, where you defend your data-tier topology to a reviewer. Do it. The skill — looking at a query and placing it on the right tier with reasons, not reflexes — is exactly what separates an engineer who's "set up Trino once" from one who can design a data platform that keeps the hot path fast and the analysts happy at the same time.
