// Exercise 2 — The order producer (idempotent, keyed, acks=all)
//
// Goal: Build a CORRECT Kafka producer in Go for order.placed.v1. Correct means:
//   * idempotent (enable.idempotence=true) so a network retry never double-appends,
//   * keyed by order_id so all events for one order share a partition and stay ordered,
//   * acks=all with the cluster's min.insync.replicas=2 so an acked write survives a
//     broker loss (the durable trio, Lecture 1 §4.2),
//   * delivery reports actually READ, so you know each record's final partition/offset
//     instead of fire-and-forgetting,
//   * a flush-and-close that does not drop in-flight records on exit.
//
// Estimated time: 60 minutes. Runnable.
//
// HOW TO USE THIS FILE
//
//   go mod init order-producer
//   go get github.com/confluentinc/confluent-kafka-go/v2/kafka
//   go run exercise-02-order-producer.go -bootstrap localhost:9092 -count 100
//
// It produces -count synthetic orders to order.placed.v1, keyed by a generated
// order_id, reads every delivery report, and prints a per-partition tally so you can
// SEE the murmur2(key) % 12 spread. It exits non-zero if ANY record failed to deliver.
//
// Then verify on the cluster (the "the offset advanced" promise):
//   kafka-consumer-groups.sh ... --describe --group <your consumer group, from ex 3>
//   or, before any consumer exists, check the log-end offsets climbed:
//   kafka-run-class.sh kafka.tools.GetOffsetShell --bootstrap-server localhost:9092 \
//       --topic order.placed.v1
//
// ACCEPTANCE CRITERIA
//
//   [ ] All -count records report "Delivered" (0 failures); program exits 0.
//   [ ] The per-partition tally shows records spread across multiple partitions
//       (not all on one) — proof the key has cardinality.
//   [ ] Producing the SAME order_id twice lands both on the SAME partition — proof
//       the partitioner is deterministic on the key. (Run with -count 1 -fixed-key A
//       twice and compare the partition.)
//   [ ] Flipping -acks 1 and killing a broker mid-run can lose a record; -acks all
//       with min.insync.replicas=2 cannot. (Stretch — do it deliberately.)
//
// Expected output is at the bottom of the file.

package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math/rand"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

const topic = "order.placed.v1"

// OrderPlaced is the payload of order.placed.v1. In the capstone this is a Protobuf
// message (order.v1); here we use JSON so the exercise has no codegen step. The
// SHAPE is what matters: an aggregate id we key on, plus the facts of the event.
type OrderPlaced struct {
	OrderID    string `json:"order_id"`
	CustomerID string `json:"customer_id"`
	TotalCents int64  `json:"total_cents"`
	Currency   string `json:"currency"`
	PlacedAt   string `json:"placed_at"` // RFC3339
}

func main() {
	bootstrap := flag.String("bootstrap", "localhost:9092", "Kafka bootstrap servers")
	count := flag.Int("count", 100, "number of orders to produce")
	acks := flag.String("acks", "all", "producer acks: 0 | 1 | all")
	fixedKey := flag.String("fixed-key", "", "if set, use this order_id for every record (to demo determinism)")
	flag.Parse()

	// --- Producer configuration ---------------------------------------------
	// enable.idempotence=true is the load-bearing line. It makes the broker dedupe
	// the producer's own retries via a PID + per-partition sequence number, so a
	// transient network error that triggers a resend does NOT append the record
	// twice. It REQUIRES acks=all and max.in.flight<=5; the client enforces that.
	cfg := &kafka.ConfigMap{
		"bootstrap.servers":                     *bootstrap,
		"acks":                                  *acks,
		"enable.idempotence":                    *acks == "all", // idempotence needs acks=all
		"max.in.flight.requests.per.connection": 5,
		"retries":                               10,
		"retry.backoff.ms":                      100,
		"delivery.timeout.ms":                   30000,
		"linger.ms":                             5, // small batching window for throughput
		"compression.type":                      "lz4",
		"client.id":                             "order-producer",
	}

	producer, err := kafka.NewProducer(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create producer: %v\n", err)
		os.Exit(2)
	}
	defer producer.Close()

	fmt.Printf("producing %d orders to %s (acks=%s, idempotence=%v)\n",
		*count, topic, *acks, *acks == "all")

	// --- Delivery-report consumer -------------------------------------------
	// confluent-kafka-go delivers async results on producer.Events(). We MUST read
	// them: each report tells us the final partition+offset, or the error. Ignoring
	// this channel is how people "lose" records they never confirmed. We run a
	// goroutine that tallies successes and failures until we close the channel.
	var (
		delivered   int
		failed      int
		perPartition = map[int32]int{}
		mu          sync.Mutex
		wg          sync.WaitGroup
	)

	wg.Add(1)
	go func() {
		defer wg.Done()
		for e := range producer.Events() {
			switch ev := e.(type) {
			case *kafka.Message:
				mu.Lock()
				if ev.TopicPartition.Error != nil {
					failed++
					fmt.Fprintf(os.Stderr, "FAILED key=%s: %v\n",
						string(ev.Key), ev.TopicPartition.Error)
				} else {
					delivered++
					perPartition[ev.TopicPartition.Partition]++
				}
				mu.Unlock()
			case kafka.Error:
				// Generic client error (e.g., all brokers down). Log; librdkafka
				// retries transient ones under the hood per our retries setting.
				fmt.Fprintf(os.Stderr, "client error: %v\n", ev)
			}
		}
	}()

	// --- Produce loop -------------------------------------------------------
	// Handle Ctrl+C so an interrupted run still flushes what it queued.
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	rng := rand.New(rand.NewSource(time.Now().UnixNano()))
produceLoop:
	for i := 0; i < *count; i++ {
		select {
		case <-sigChan:
			fmt.Println("\ninterrupted — flushing what we queued...")
			break produceLoop
		default:
		}

		key := *fixedKey
		if key == "" {
			key = fmt.Sprintf("order-%06d", rng.Intn(1_000_000))
		}
		order := OrderPlaced{
			OrderID:    key,
			CustomerID: fmt.Sprintf("cust-%04d", rng.Intn(5000)),
			TotalCents: int64(100 + rng.Intn(50000)),
			Currency:   "USD",
			PlacedAt:   time.Now().UTC().Format(time.RFC3339),
		}
		value, err := json.Marshal(order)
		if err != nil {
			fmt.Fprintf(os.Stderr, "marshal error: %v\n", err)
			continue
		}

		msg := &kafka.Message{
			TopicPartition: kafka.TopicPartition{
				Topic:     stringPtr(topic),
				Partition: kafka.PartitionAny, // let the keyed partitioner decide
			},
			Key:   []byte(key), // KEY = order_id => per-order ordering (Lecture 1 §2.1)
			Value: value,
			Headers: []kafka.Header{
				{Key: "content-type", Value: []byte("application/json")},
				{Key: "event-type", Value: []byte("order.placed.v1")},
			},
		}

		// Produce enqueues; the delivery report arrives later on Events(). If the
		// internal queue is full, Produce returns a retriable error — back off and
		// retry rather than dropping the record.
		for {
			err = producer.Produce(msg, nil)
			if err == nil {
				break
			}
			if err.(kafka.Error).Code() == kafka.ErrQueueFull {
				producer.Flush(100) // drain some, then retry this record
				continue
			}
			fmt.Fprintf(os.Stderr, "produce error key=%s: %v\n", key, err)
			break
		}
	}

	// --- Flush and close ----------------------------------------------------
	// Flush blocks until all queued records have a delivery report (or the timeout).
	// A non-zero return means records are STILL in flight — never exit success then.
	remaining := producer.Flush(15 * 1000)
	if remaining > 0 {
		fmt.Fprintf(os.Stderr, "WARNING: %d records still in flight after flush timeout\n", remaining)
	}

	// Closing the producer ends the Events() channel, which ends the reporter goroutine.
	producer.Close()
	wg.Wait()

	// --- Report -------------------------------------------------------------
	fmt.Println("\n==================== DELIVERY REPORT ====================")
	fmt.Printf("delivered: %d   failed: %d\n", delivered, failed)
	fmt.Println("per-partition tally (proves key cardinality spread the load):")
	for p := int32(0); p < 12; p++ {
		if n, ok := perPartition[p]; ok {
			fmt.Printf("  partition %2d: %d\n", p, n)
		}
	}
	fmt.Println("========================================================")

	if failed > 0 || remaining > 0 {
		os.Exit(1)
	}
}

func stringPtr(s string) *string { return &s }

// -----------------------------------------------------------------------------
// Expected output (go run ... -count 100, healthy cluster)
// -----------------------------------------------------------------------------
//
// producing 100 orders to order.placed.v1 (acks=all, idempotence=true)
//
// ==================== DELIVERY REPORT ====================
// delivered: 100   failed: 0
// per-partition tally (proves key cardinality spread the load):
//   partition  0: 7
//   partition  1: 9
//   partition  2: 8
//   ...
//   partition 11: 10
// ========================================================
//
// The records spread across all 12 partitions because the keys (order-NNNNNN) have
// high cardinality. Run again with `-count 1 -fixed-key A` twice: BOTH single records
// land on the SAME partition, because murmur2("A") % 12 is deterministic. That
// determinism is exactly what gives you per-order ordering.
//
// Expected output (acks=1, broker killed mid-run — the stretch)
// -----------------------------------------------------------------------------
//
// With -acks 1 and a broker killed at the moment it was a partition leader, you may
// see a record reported "Delivered" that a later consumer never sees: the leader
// acked it, then died before a follower replicated it, and the new leader never had
// it. That is the Lecture 1 §4.3 data-loss row, reproduced. Repeat with -acks all and
// min.insync.replicas=2 and the lost record cannot happen — the write either lands on
// >=2 replicas or is rejected (NotEnoughReplicas), never acked-then-lost.
// -----------------------------------------------------------------------------
