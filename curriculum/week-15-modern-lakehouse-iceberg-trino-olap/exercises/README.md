# Week 15 — Exercises

Three focused drills that build and query a working lakehouse. Each takes 45–60 minutes. Do them in order — exercise 2's queries need the table exercise 1 stands up, and exercise 3 lands your change stream into that same table. Run everything against the Docker stack from exercise 1 (MinIO + Iceberg REST catalog + Trino), plus the Week 14 CDC pipeline for exercise 3.

## Index

1. **[Exercise 1 — Stand up the lakehouse](exercise-01-stand-up-the-lakehouse.md)** — bring up MinIO, an Iceberg REST catalog, and Trino with `docker compose`; create your first Iceberg table; insert and query; inspect the metadata MinIO holds. (~55 min, guided)
2. **[Exercise 2 — Analytical SQL against Iceberg](exercise-02-analytical-queries.sql)** — aggregations, window functions, time-travel, and a federated Iceberg↔Postgres join, all in Trino. (~45 min, runnable SQL)
3. **[Exercise 3 — Land the change stream in Iceberg](exercise-03-land-the-stream.py)** — consume the `orders` change stream and append each event into an Iceberg table with PyIceberg, then query it in Trino. (~50 min, runnable Python)

## How to work the exercises

- Have Docker (or Kind) and ~10 GB free disk. The stack is MinIO + a catalog + Trino; exercise 3 also needs the Week 14 Kafka/Debezium pipeline (a fallback generator is provided).
- Use the `trino` CLI (or any JDBC client) to run queries: `docker compose exec trino trino`.
- **Inspect the metadata, don't just trust it.** After you create a table, look at what landed in MinIO (`mc ls`) — the metadata JSON, the manifest, the Parquet files. Seeing the Iceberg tree on disk is half the lesson.
- When a query "can't see the table," check the *catalog* first — Trino and PyIceberg must point at the **same** catalog or they see different worlds (Lecture 2 §1).
- Each runnable exercise ends with an **expected output** block. If your output doesn't match the *shape*, you're not done.

## Running the SQL and Python exercises

The SQL file runs in the Trino CLI:

```bash
docker compose exec -T trino trino --catalog iceberg --schema shop < exercise-02-analytical-queries.sql
```

The Python file needs PyIceberg and a Kafka client:

```bash
python3 -m pip install "pyiceberg[s3fs,pyarrow]>=0.6" "confluent-kafka>=2.3"
python3 exercise-03-land-the-stream.py \
    --catalog-uri http://localhost:8181 \
    --bootstrap localhost:9092 --topic shop.public.orders
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-15` to compare.
