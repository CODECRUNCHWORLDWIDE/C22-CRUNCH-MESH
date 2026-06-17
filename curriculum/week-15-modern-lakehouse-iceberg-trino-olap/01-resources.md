# Week 15 — Resources

Every resource here is **free** and pinned to current stable versions. The Apache Iceberg specification and the Trino documentation are both open and excellent — the Iceberg *spec* in particular is the source of truth this whole week defers to, over any vendor's marketing. dbt Core, MinIO, and Nessie all publish full docs openly. No paywalled material is required.

When a link is versioned, the current stable URL is given. Iceberg's spec and Trino's connectors evolve; if a property name or function signature differs in your version, the project's own docs are authoritative.

## Required reading (work it into your week)

- **Apache Iceberg — table spec** — the contract. Read the "Overview" and "Table Metadata" sections Monday, the rest as reference:
  <https://iceberg.apache.org/spec/>
- **Apache Iceberg — docs home** (concepts, partitioning, evolution, time-travel):
  <https://iceberg.apache.org/docs/latest/>
- **Trino — Iceberg connector** — how Trino reads/writes Iceberg, plus the time-travel and metadata-table syntax:
  <https://trino.io/docs/current/connector/iceberg.html>
- **Trino — overview & concepts** (coordinator/worker, connectors, federation):
  <https://trino.io/docs/current/overview/concepts.html>
- **dbt — "What is dbt?"** and the model/materialization concepts:
  <https://docs.getdbt.com/docs/introduction>

## The deeper references (skim now, return when you need them)

- **Iceberg — partitioning & hidden partitioning** — why partition values don't leak into queries:
  <https://iceberg.apache.org/docs/latest/partitioning/>
- **Iceberg — schema evolution** — add/drop/rename columns without rewriting data:
  <https://iceberg.apache.org/docs/latest/evolution/>
- **Parquet — file format** — the columnar substrate (row groups, column chunks, encodings):
  <https://parquet.apache.org/docs/file-format/>
- **Trino — Iceberg time travel & metadata tables** (`$snapshots`, `$history`, `$files`):
  <https://trino.io/docs/current/connector/iceberg.html#metadata-tables>
- **Project Nessie — git-like catalog** (branches, tags, merges for data):
  <https://projectnessie.org/>
- **Iceberg REST catalog spec** — the open catalog API Trino and others speak:
  <https://github.com/apache/iceberg/blob/main/open-api/rest-catalog-open-api.yaml>

## API & engine references (the ones you'll have open all week)

- **Trino SQL — aggregate functions**: <https://trino.io/docs/current/functions/aggregate.html>
- **Trino SQL — window functions**: <https://trino.io/docs/current/functions/window.html>
- **Trino — Postgres connector** (for federation): <https://trino.io/docs/current/connector/postgresql.html>
- **Trino — Kafka connector**: <https://trino.io/docs/current/connector/kafka.html>
- **PyIceberg** — the Python library to write Iceberg tables without Spark (the exercise uses it):
  <https://py.iceberg.apache.org/>
- **DuckDB Iceberg extension** — query Iceberg from your laptop, proving engine-portability:
  <https://duckdb.org/docs/extensions/iceberg.html>

## dbt and the transformation layer

- **dbt — materializations** (view / table / incremental / ephemeral):
  <https://docs.getdbt.com/docs/build/materializations>
- **dbt — incremental models** (the rollup pattern that doesn't reprocess all history):
  <https://docs.getdbt.com/docs/build/incremental-models>
- **dbt — tests** (schema and data tests that gate a model):
  <https://docs.getdbt.com/docs/build/data-tests>
- **dbt-trino adapter** — running dbt against a Trino+Iceberg lakehouse:
  <https://github.com/starburstdata/dbt-trino>

## Background — the "why" reading

- **"What is a lakehouse?"** (the CIDR paper that named the pattern) — the academic framing:
  <https://www.cidrdb.org/cidr2021/papers/cidr2021_paper17.pdf>
- **Kleppmann — Designing Data-Intensive Applications, ch. 3** — column-oriented storage, the clearest explanation of why columns win for analytics (chapter is referenced throughout this week).
- **"Iceberg vs Delta vs Hudi"** — read a *neutral* comparison (the table-format wars); search the Iceberg and Trino blogs for the honest engineering write-ups, not vendor pages.

## Tools you'll use this week

- **MinIO** — S3-compatible object storage you run locally (`minio/minio` image). The `mc` client to inspect buckets.
- **Trino** — `trinodb/trino` image; the `trino` CLI to query. Catalogs configured under `etc/catalog/`.
- **An Iceberg REST catalog** — `tabulario/iceberg-rest` is the simplest; Nessie (`projectnessie/nessie`) for the git-like option.
- **PyIceberg** — `pip install "pyiceberg[s3fs,pyarrow]"` to write Iceberg tables from Python.
- **dbt-core + dbt-trino** — `pip install dbt-trino` for the transformation models.
- **DuckDB** — `pip install duckdb` or the CLI, for the engine-portability proof.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **OLTP** | Online Transaction Processing — many small, low-latency reads/writes of current state. Postgres's home turf. |
| **OLAP** | Online Analytical Processing — few large scans and aggregations over lots of (often historical) data. The lakehouse's turf. |
| **Row-store** | Stores all columns of a row together. Great for "give me this whole row"; bad for "aggregate one column over millions of rows." |
| **Column-store** | Stores each column together. Great for analytics (read only the columns you need); the basis of Parquet. |
| **Parquet** | The open columnar file format every lakehouse table sits on. Row groups, column chunks, compression, column stats. |
| **Lakehouse** | Open table format + columnar files on object storage, queryable by any engine. Warehouse semantics, data-lake openness. |
| **Apache Iceberg** | An open **table format**: a spec for schema, snapshots, partitions, and file manifests over object-store files. |
| **Snapshot** | An immutable, point-in-time version of an Iceberg table. The basis of time-travel and ACID. |
| **Hidden partitioning** | Iceberg partitions by a transform of a column without that partition value appearing in your query — no `WHERE part_col = ...`. |
| **Catalog** | The atomic pointer to "the current table metadata." REST catalog, Nessie, or Hive Metastore. |
| **Trino** | A distributed SQL query engine (coordinator + workers) that queries many sources via connectors. |
| **Federation** | Querying multiple data sources (Iceberg + Postgres + Kafka) in one SQL statement through Trino. |
| **Time travel** | Querying a table as of an earlier snapshot (`FOR VERSION AS OF` / `FOR TIMESTAMP AS OF`). |
| **dbt** | A tool for transformations-as-code: version-controlled, tested SQL models that build derived tables. |

---

*If a link 404s, please open an issue so we can replace it.*
