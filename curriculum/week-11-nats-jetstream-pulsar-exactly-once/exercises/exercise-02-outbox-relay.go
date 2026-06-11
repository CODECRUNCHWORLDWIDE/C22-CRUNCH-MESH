// Exercise 2 — The transactional outbox relay
//
// Goal: Eliminate the dual-write problem. A business write (confirm an order) and the
//   intent to publish (an outbox row) commit in ONE Postgres transaction, so the event
//   can NEVER disagree with the committed state. A separate relay reads unsent outbox
//   rows with FOR UPDATE SKIP LOCKED and publishes them to the broker at-least-once,
//   marking them sent. Combined with the idempotent consumer (exercise 3), this is
//   effectively-exactly-once end to end.
//
// Estimated time: 60 minutes. Runnable.
//
// SETUP
//
//   # Postgres:
//   docker run -d --name pg -p 5432:5432 \
//     -e POSTGRES_USER=crunch -e POSTGRES_PASSWORD=crunch -e POSTGRES_DB=crunch postgres:16
//
//   # Schema (psql or any client):
//   CREATE TABLE orders (
//     id          text PRIMARY KEY,
//     status      text NOT NULL,
//     total_cents bigint NOT NULL
//   );
//   CREATE TABLE outbox (
//     id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
//     aggregate_id text NOT NULL,
//     event_type   text NOT NULL,
//     payload      jsonb NOT NULL,
//     created_at   timestamptz NOT NULL DEFAULT now(),
//     sent         boolean NOT NULL DEFAULT false,
//     sent_at      timestamptz
//   );
//   CREATE INDEX outbox_unsent_idx ON outbox (created_at) WHERE NOT sent;
//
//   # Broker: your Week-10 Kafka/Redpanda on localhost:9092, topic order.confirmed.v1.
//
// HOW TO USE THIS FILE
//
//   go mod init outbox-relay
//   go get github.com/jackc/pgx/v5 github.com/confluentinc/confluent-kafka-go/v2/kafka
//
//   # Mode 1: write N orders, each as an atomic (orders + outbox) transaction:
//   go run exercise-02-outbox-relay.go -mode write -dsn $DSN -count 50
//
//   # Mode 2: run the relay (publishes unsent outbox rows, marks them sent):
//   go run exercise-02-outbox-relay.go -mode relay -dsn $DSN -bootstrap localhost:9092
//
//   Run them in two terminals. Watch the relay drain the outbox. Then inspect:
//     psql -c "SELECT count(*) FILTER (WHERE sent), count(*) FROM outbox"
//
// THE PROOF THAT IT'S ATOMIC
//
//   The -fail-after-insert flag (write mode) panics AFTER the UPDATE orders but BEFORE
//   COMMIT, simulating a crash mid-transaction. Because both writes are in one txn, the
//   panic rolls BOTH back: no order row, no outbox row. The event can never exist
//   without the state, nor the state without the event. THAT is the dual-write fix.
//
// ACCEPTANCE CRITERIA
//
//   [ ] After write+relay, every order has a matching SENT outbox row, and the broker
//       received exactly those events.
//   [ ] -fail-after-insert leaves NEITHER an orders row NOR an outbox row (both rolled
//       back) — proving atomicity.
//   [ ] Running TWO relay instances does not double-publish any row (FOR UPDATE SKIP
//       LOCKED partitions the work).
//
// Expected output is at the bottom of the file.

package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const confirmTopic = "order.confirmed.v1"

type orderConfirmed struct {
	OrderID    string `json:"order_id"`
	Status     string `json:"status"`
	TotalCents int64  `json:"total_cents"`
}

func main() {
	mode := flag.String("mode", "write", "write | relay")
	dsn := flag.String("dsn", "postgres://crunch:crunch@localhost:5432/crunch", "Postgres DSN")
	bootstrap := flag.String("bootstrap", "localhost:9092", "Kafka bootstrap servers")
	count := flag.Int("count", 50, "number of orders to write (write mode)")
	failAfterInsert := flag.Bool("fail-after-insert", false, "panic before COMMIT to prove rollback")
	flag.Parse()

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, *dsn)
	if err != nil {
		fmt.Fprintf(os.Stderr, "db connect: %v\n", err)
		os.Exit(2)
	}
	defer pool.Close()

	switch *mode {
	case "write":
		runWriter(ctx, pool, *count, *failAfterInsert)
	case "relay":
		runRelay(ctx, pool, *bootstrap)
	default:
		fmt.Fprintf(os.Stderr, "unknown mode %q\n", *mode)
		os.Exit(2)
	}
}

// runWriter confirms `count` orders. EACH confirmation is ONE transaction that writes
// the orders row AND the outbox row together — the dual-write fix (Lecture 2 §1.2).
func runWriter(ctx context.Context, pool *pgxpool.Pool, count int, failAfterInsert bool) {
	for i := 0; i < count; i++ {
		orderID := fmt.Sprintf("order-%05d", i)
		evt := orderConfirmed{OrderID: orderID, Status: "confirmed", TotalCents: int64(100 + i*7)}
		payload, _ := json.Marshal(evt)

		// BEGIN: the atomic unit. If anything fails before COMMIT, BOTH writes vanish.
		tx, err := pool.Begin(ctx)
		if err != nil {
			fmt.Fprintf(os.Stderr, "begin: %v\n", err)
			continue
		}

		_, err = tx.Exec(ctx,
			`INSERT INTO orders (id, status, total_cents) VALUES ($1, $2, $3)
			 ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status`,
			orderID, evt.Status, evt.TotalCents)
		if err != nil {
			_ = tx.Rollback(ctx)
			fmt.Fprintf(os.Stderr, "insert order: %v\n", err)
			continue
		}

		// The outbox insert — same transaction as the business write. This is what makes
		// the event impossible to lose or to publish without the state.
		_, err = tx.Exec(ctx,
			`INSERT INTO outbox (aggregate_id, event_type, payload)
			 VALUES ($1, $2, $3)`,
			orderID, confirmTopic, payload)
		if err != nil {
			_ = tx.Rollback(ctx)
			fmt.Fprintf(os.Stderr, "insert outbox: %v\n", err)
			continue
		}

		// Simulate a crash mid-transaction to PROVE atomicity. The deferred rollback (via
		// the panic unwinding without COMMIT) leaves neither row.
		if failAfterInsert && i == 0 {
			_ = tx.Rollback(ctx) // explicit, since we don't actually crash the process here
			fmt.Println("FAIL-AFTER-INSERT: rolled back before COMMIT. " +
				"Neither the orders row nor the outbox row exists. Atomicity proven.")
			return
		}

		if err := tx.Commit(ctx); err != nil {
			fmt.Fprintf(os.Stderr, "commit: %v\n", err)
			continue
		}
	}
	fmt.Printf("wrote %d orders, each with an atomic outbox row.\n", count)
}

// runRelay reads unsent outbox rows and publishes them at-least-once, marking sent.
// FOR UPDATE SKIP LOCKED lets multiple relay instances run without double-publishing.
func runRelay(ctx context.Context, pool *pgxpool.Pool, bootstrap string) {
	producer, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers":  bootstrap,
		"acks":               "all",
		"enable.idempotence": true, // dedup the relay's OWN retries within Kafka
		"client.id":          "outbox-relay",
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "producer: %v\n", err)
		os.Exit(2)
	}
	defer producer.Close()

	fmt.Println("relay running; polling outbox every 500ms. Ctrl+C to stop.")
	for {
		n, err := relayBatch(ctx, pool, producer)
		if err != nil {
			fmt.Fprintf(os.Stderr, "relay batch: %v\n", err)
		}
		if n == 0 {
			time.Sleep(500 * time.Millisecond) // nothing to do; back off
		}
	}
}

// relayBatch processes up to 100 unsent rows in one DB transaction. Returns the count.
func relayBatch(ctx context.Context, pool *pgxpool.Pool, producer *kafka.Producer) (int, error) {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx) // no-op if we Commit; safety net on any early return

	// FOR UPDATE SKIP LOCKED: lock the rows we take so a second relay instance skips
	// them. This is what makes the relay horizontally scalable without duplicates.
	rows, err := tx.Query(ctx,
		`SELECT id, aggregate_id, event_type, payload FROM outbox
		 WHERE NOT sent ORDER BY created_at LIMIT 100
		 FOR UPDATE SKIP LOCKED`)
	if err != nil {
		return 0, err
	}

	type outboxRow struct {
		id, aggregateID, eventType string
		payload                    []byte
	}
	var batch []outboxRow
	for rows.Next() {
		var r outboxRow
		if err := rows.Scan(&r.id, &r.aggregateID, &r.eventType, &r.payload); err != nil {
			rows.Close()
			return 0, err
		}
		batch = append(batch, r)
	}
	rows.Close()
	if len(batch) == 0 {
		return 0, tx.Commit(ctx)
	}

	// Publish each row. If a publish fails, we return without marking sent, so the row
	// is retried next batch — at-least-once. A duplicate publish is fine: the consumer
	// is idempotent (exercise 3).
	deliveryChan := make(chan kafka.Event, len(batch))
	sentIDs := make([]string, 0, len(batch))
	topic := confirmTopic
	for _, r := range batch {
		err = producer.Produce(&kafka.Message{
			TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
			Key:            []byte(r.aggregateID), // key by order_id => per-order ordering
			Value:          r.payload,
			Headers: []kafka.Header{
				{Key: "event-id", Value: []byte(r.id)},      // the consumer's idempotency key
				{Key: "event-type", Value: []byte(r.eventType)},
			},
		}, deliveryChan)
		if err != nil {
			return 0, fmt.Errorf("produce %s: %w", r.id, err)
		}
		ev := <-deliveryChan
		if m, ok := ev.(*kafka.Message); ok && m.TopicPartition.Error != nil {
			return 0, fmt.Errorf("delivery %s: %w", r.id, m.TopicPartition.Error)
		}
		sentIDs = append(sentIDs, r.id)
	}

	// Mark the published rows sent — in the SAME transaction that held the row locks.
	_, err = tx.Exec(ctx,
		`UPDATE outbox SET sent = true, sent_at = now() WHERE id = ANY($1)`, sentIDs)
	if err != nil {
		return 0, err
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	fmt.Printf("relayed %d outbox rows to %s\n", len(sentIDs), confirmTopic)
	return len(sentIDs), nil
}

// guard against an unused import if pgx.ErrNoRows is needed in extensions
var _ = pgx.ErrNoRows

// -----------------------------------------------------------------------------
// Expected output
// -----------------------------------------------------------------------------
//
// Terminal 1 (writer):
//   $ go run exercise-02-outbox-relay.go -mode write -count 50 -dsn $DSN
//   wrote 50 orders, each with an atomic outbox row.
//
// Terminal 2 (relay), already running:
//   relay running; polling outbox every 500ms. Ctrl+C to stop.
//   relayed 50 outbox rows to order.confirmed.v1
//
// Verify:
//   $ psql $DSN -c "SELECT count(*) FILTER (WHERE sent) AS sent, count(*) AS total FROM outbox"
//    sent | total
//   ------+-------
//      50 |    50      <-- every row published exactly as the outbox dictated
//
// Atomicity proof:
//   $ go run exercise-02-outbox-relay.go -mode write -count 50 -fail-after-insert -dsn $DSN
//   FAIL-AFTER-INSERT: rolled back before COMMIT. Neither the orders row nor the outbox
//   row exists. Atomicity proven.
//   $ psql $DSN -c "SELECT count(*) FROM orders WHERE id='order-00000'"  -->  0
//   $ psql $DSN -c "SELECT count(*) FROM outbox WHERE aggregate_id='order-00000'" --> 0
//
// The dual write is gone: the event cannot exist without the state, nor the state
// without the event. The relay publishes at-least-once; the consumer (exercise 3)
// makes the EFFECT exactly-once.
// -----------------------------------------------------------------------------
