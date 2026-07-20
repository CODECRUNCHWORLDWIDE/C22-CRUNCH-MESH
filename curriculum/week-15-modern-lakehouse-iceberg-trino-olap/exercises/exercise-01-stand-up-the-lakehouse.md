# Exercise 1 — Stand Up the Lakehouse

**Goal:** Bring up a complete, working lakehouse from scratch — MinIO as S3-compatible object storage, an Iceberg REST catalog, and Trino as the query engine — then create your first Iceberg table, write and query data, and *see the Iceberg metadata tree on disk*. You will train the foundational habit of the week: knowing that an Iceberg table is a tree of metadata files pointing at Parquet data files, because you'll look at the actual files in the bucket.

**Estimated time:** 55 minutes. Guided.

---

## Setup

Save this as `compose.yml`. It wires together MinIO, the Iceberg REST catalog, and Trino on one network.

```yaml
services:
  minio:
    image: minio/minio:latest
    command: ["server", "/data", "--console-address", ":9001"]
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio12345
    ports: ["9000:9000", "9001:9001"]

  # Create the warehouse bucket on startup.
  minio-init:
    image: minio/mc:latest
    depends_on: [minio]
    entrypoint: >
      /bin/sh -c "
      until mc alias set local http://minio:9000 minio minio12345; do sleep 1; done;
      mc mb --ignore-existing local/warehouse;
      echo 'bucket ready';
      "

  iceberg-rest:
    image: tabulario/iceberg-rest:latest
    depends_on: [minio]
    environment:
      AWS_ACCESS_KEY_ID: minio
      AWS_SECRET_ACCESS_KEY: minio12345
      AWS_REGION: us-east-1
      CATALOG_WAREHOUSE: s3://warehouse/
      CATALOG_IO__IMPL: org.apache.iceberg.aws.s3.S3FileIO
      CATALOG_S3_ENDPOINT: http://minio:9000
      CATALOG_S3_PATH__STYLE__ACCESS: "true"
    ports: ["8181:8181"]

  trino:
    image: trinodb/trino:latest
    depends_on: [iceberg-rest, minio]
    ports: ["8080:8080"]
    volumes:
      - ./trino/catalog:/etc/trino/catalog
```

Create the Trino Iceberg connector config at `trino/catalog/iceberg.properties`:

```properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=http://iceberg-rest:8181
iceberg.rest-catalog.warehouse=s3://warehouse/
fs.native-s3.enabled=true
s3.endpoint=http://minio:9000
s3.path-style-access=true
s3.aws-access-key=minio
s3.aws-secret-key=minio12345
s3.region=us-east-1
```

```bash
docker compose up -d
# Wait for Trino to be ready (it takes ~30s):
until docker compose exec -T trino trino --execute "SELECT 1" >/dev/null 2>&1; do
  echo "waiting for trino..."; sleep 3;
done
echo "lakehouse up"
```

---

## Step 1 — Create a schema and a table

Open the Trino CLI:

```bash
docker compose exec trino trino --catalog iceberg
```

Create a schema (an Iceberg namespace) and a table, partitioned by `month(created_at)` using **hidden partitioning** (Lecture 1 §4.3):

```sql
CREATE SCHEMA IF NOT EXISTS iceberg.shop;

CREATE TABLE iceberg.shop.orders (
    order_id    bigint,
    customer_id bigint,
    status      varchar,
    total_cents bigint,
    created_at  timestamp(6)
) WITH (
    partitioning = ARRAY['month(created_at)']
);
```

That `CREATE TABLE` just wrote a table-metadata file and a catalog pointer — but **no data files yet**, because the table is empty. You'll see that on disk in Step 4.

---

## Step 2 — Insert and query

```sql
INSERT INTO iceberg.shop.orders VALUES
    (1, 42, 'SHIPPED',   1999, TIMESTAMP '2026-03-01 10:00:00'),
    (2, 7,  'PLACED',     500, TIMESTAMP '2026-03-01 11:30:00'),
    (3, 42, 'DELIVERED', 8200, TIMESTAMP '2026-04-02 09:15:00');

SELECT status, count(*) AS n, sum(total_cents) AS cents
FROM iceberg.shop.orders
GROUP BY status
ORDER BY status;
```

```
  status   | n | cents
-----------+---+-------
 DELIVERED | 1 |  8200
 PLACED    | 1 |   500
 SHIPPED   | 1 |  1999
```

That `INSERT` created a new snapshot: it wrote Parquet data file(s) into the two month-partitions (March and April), a manifest listing them, a manifest list, and a new metadata file — then atomically swapped the catalog pointer (Lecture 1 §4.2).

---

## Step 3 — Prove hidden partitioning prunes

Query with a **natural predicate** on `created_at` — no `month` column in sight — and Iceberg prunes to the right partition:

```sql
-- Iceberg figures out this only touches the March partition.
SELECT count(*) FROM iceberg.shop.orders
WHERE created_at >= TIMESTAMP '2026-03-01' AND created_at < TIMESTAMP '2026-04-01';
```

```
 _col0
-------
     2
```

You wrote a predicate on `created_at` and Iceberg pruned by `month(created_at)` *for you*. That's hidden partitioning — the partition transform never leaked into your SQL.

Inspect the partitions Iceberg created via the metadata table:

```sql
SELECT partition, record_count, file_count
FROM iceberg.shop."orders$partitions";
```

You'll see one row per month-partition with its record and file counts.

---

## Step 4 — See the Iceberg metadata tree on disk

This is the half of the lesson you can't skip. Look at what's actually in MinIO:

```bash
docker compose exec minio-init mc ls -r local/warehouse/shop/orders/
```

```
.../metadata/00000-....metadata.json      # table metadata (the empty CREATE)
.../metadata/00001-....metadata.json      # table metadata (after the INSERT)
.../metadata/snap-....-....avro           # the manifest list (one per snapshot)
.../metadata/....-m0.avro                 # a manifest file
.../data/created_at_month=2026-03/....parquet   # data files, in month-partitions!
.../data/created_at_month=2026-04/....parquet
```

Read that listing against the Lecture 1 §4.1 tree: the `metadata/*.json` are table-metadata files (one per commit), the `snap-*.avro` is a manifest list, the `*-m0.avro` is a manifest, and the `data/*/*.parquet` are the columnar data files — laid out under `created_at_month=...` directories by the hidden partition transform. **This pile of files, described by that metadata, IS the table.** Any Iceberg-capable engine can read it.

---

## Step 5 — Snapshots and time-travel

Every commit made a snapshot. List them:

```sql
SELECT snapshot_id, committed_at, operation
FROM iceberg.shop."orders$snapshots"
ORDER BY committed_at;
```

Note the snapshot ID from *before* the insert (the one with `operation = 'append'` is the insert; the first metadata had no data). Now insert more rows, then time-travel back:

```sql
INSERT INTO iceberg.shop.orders VALUES
    (4, 7, 'PLACED', 3300, TIMESTAMP '2026-04-05 14:00:00');

-- current count:
SELECT count(*) FROM iceberg.shop.orders;                       -- 4

-- the count AS OF the earlier snapshot (paste the snapshot_id from above):
SELECT count(*) FROM iceberg.shop.orders FOR VERSION AS OF <earlier_snapshot_id>;   -- 3
```

**Different counts from the same table at different snapshots.** That is the time-travel promise from the week README — a consistent, queryable history, for free, from the snapshot design.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `docker compose up` brings up MinIO, the Iceberg REST catalog, and Trino, and `SELECT 1` works in the Trino CLI.
- [ ] You created `iceberg.shop.orders` with `month(created_at)` hidden partitioning, inserted rows, and got correct aggregation results.
- [ ] A `WHERE created_at >= ... AND < ...` query prunes to the right month-partition (you can show the partition metadata table).
- [ ] You listed the actual files in MinIO and can point to the metadata file, the manifest list, a manifest, and the partitioned Parquet data files.
- [ ] A `FOR VERSION AS OF` time-travel query returns a *different* (earlier) row count than the current table.

---

## Stretch

- **Engine portability — the thesis, proven.** Install DuckDB (`pip install duckdb`), and read your Iceberg table from it (`SELECT * FROM iceberg_scan('s3://warehouse/shop/orders', ...)` with the MinIO credentials). Same data, different engine, no copy. That single query is the entire point of the lakehouse.
- **Schema evolution, cheap.** `ALTER TABLE iceberg.shop.orders ADD COLUMN note varchar;` then query — old rows return `null` for `note`, no data was rewritten. Inspect MinIO: no new data files, just a new metadata file.
- **Snapshot expiry.** Run several inserts to accumulate snapshots, then call the `expire_snapshots` procedure and confirm old snapshots (and their now-unreferenced data files) are removed — the cost side of time-travel.

---

When the lakehouse is up and you've seen the metadata tree, move to [Exercise 2 — Analytical SQL against Iceberg](exercise-02-analytical-queries.sql).
