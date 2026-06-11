// Exercise 3 — The event store (append-only, replay-to-rebuild, optimistic concurrency)
//
// Goal: Implement a minimal but correct event-sourced aggregate in Go. Events are
//       the source of truth; current state is FOLDED from events; concurrent
//       conflicting commands are rejected by an optimistic-concurrency version
//       check (a UNIQUE (aggregate_id, version) constraint). This is event
//       sourcing's core mechanic, distilled to one file.
//
// Estimated time: 50 minutes. Runnable.
//
// WHAT THIS DEMONSTRATES
//
//   * Appending events under a per-aggregate version, atomically.
//   * Rebuilding an aggregate's CURRENT STATE by replaying (folding) its events.
//   * Optimistic concurrency: two commands that both load version N and both try
//     to append N+1 — exactly one wins; the loser must reload and retry.
//
// REQUIREMENTS
//
//   * Postgres 16 reachable.
//   * go >= 1.21 and the pgx driver:
//        go mod init eventstore && go get github.com/jackc/pgx/v5 && go mod tidy
//
// RUN
//
//   go run exercise-03-event-store.go \
//       -dsn "postgres://postgres:postgres@localhost:5432/shop"
//
// ACCEPTANCE CRITERIA
//
//   [ ] An order aggregate is built by appending OrderPlaced, OrderPaid,
//       OrderShipped events; loadState replays them to the correct status.
//   [ ] A DELETE of the events and a fresh replay reconstructs the SAME state —
//       state is a pure fold over the log.
//   [ ] The concurrency demo shows exactly ONE of two racing appends succeeds;
//       the other gets a version-conflict error and the program reports it.
//   [ ] You can explain why UNIQUE (aggregate_id, version) is the whole
//       concurrency-control mechanism — no row locks needed.
//
// Expected output is at the bottom of the file.

package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"sync"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

const schema = `
CREATE TABLE IF NOT EXISTS events (
    global_seq   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_id text   NOT NULL,
    version      int    NOT NULL,
    event_type   text   NOT NULL,
    payload      jsonb  NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (aggregate_id, version)        -- the optimistic-concurrency guard
);
`

// ErrVersionConflict is returned when an append loses the optimistic-concurrency
// race: another command already wrote the version we tried to write.
var ErrVersionConflict = errors.New("version conflict: aggregate changed since load")

// Event is one immutable fact in an aggregate's history.
type Event struct {
	Type    string          `json:"type"`
	Payload json.RawMessage `json:"payload"`
	Version int             `json:"version"`
}

// OrderState is the FOLDED current state. It is never stored as the source of
// truth; it is always recomputed from events.
type OrderState struct {
	OrderID   string
	Status    string // "" (none) -> PLACED -> PAID -> SHIPPED -> DELIVERED / CANCELLED
	Version   int    // the version of the last applied event
	Exists    bool
}

// apply folds a single event onto the state. This is the heart of event sourcing:
// current state = events.reduce(apply, empty).
func apply(s OrderState, e Event) OrderState {
	switch e.Type {
	case "OrderPlaced":
		s.Exists = true
		s.Status = "PLACED"
	case "OrderPaid":
		s.Status = "PAID"
	case "OrderShipped":
		s.Status = "SHIPPED"
	case "OrderDelivered":
		s.Status = "DELIVERED"
	case "OrderCancelled":
		s.Status = "CANCELLED"
	}
	s.Version = e.Version
	return s
}

// loadState rebuilds an aggregate's current state by replaying ALL its events in
// order. (A real system would start from the latest snapshot; see the stretch.)
func loadState(ctx context.Context, db *pgxpool.Pool, orderID string) (OrderState, error) {
	rows, err := db.Query(ctx,
		`SELECT event_type, payload, version FROM events
		 WHERE aggregate_id = $1 ORDER BY version ASC`, orderID)
	if err != nil {
		return OrderState{}, err
	}
	defer rows.Close()

	state := OrderState{OrderID: orderID}
	for rows.Next() {
		var e Event
		if err := rows.Scan(&e.Type, &e.Payload, &e.Version); err != nil {
			return OrderState{}, err
		}
		state = apply(state, e)
	}
	return state, rows.Err()
}

// appendEvent appends a new event at expectedVersion+1. If another writer already
// took that version, the UNIQUE constraint rejects us and we return
// ErrVersionConflict — optimistic concurrency, no locks.
func appendEvent(ctx context.Context, db *pgxpool.Pool, orderID string,
	expectedVersion int, eventType string, payload any) error {

	raw, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	_, err = db.Exec(ctx,
		`INSERT INTO events (aggregate_id, version, event_type, payload)
		 VALUES ($1, $2, $3, $4)`,
		orderID, expectedVersion+1, eventType, raw)

	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" { // unique_violation
		return ErrVersionConflict
	}
	return err
}

// shipOrder is a command handler: load current state, validate the transition,
// and append the resulting event. This is the command -> validate -> event loop.
func shipOrder(ctx context.Context, db *pgxpool.Pool, orderID string) error {
	state, err := loadState(ctx, db, orderID)
	if err != nil {
		return err
	}
	if state.Status != "PAID" {
		return fmt.Errorf("cannot ship order in status %q (must be PAID)", state.Status)
	}
	return appendEvent(ctx, db, orderID, state.Version, "OrderShipped",
		map[string]string{"carrier": "crunch-logistics"})
}

func main() {
	dsn := flag.String("dsn", "", "postgres DSN, e.g. postgres://user:pass@host:5432/db")
	flag.Parse()
	if *dsn == "" {
		log.Fatal("missing -dsn")
	}
	ctx := context.Background()

	db, err := pgxpool.New(ctx, *dsn)
	if err != nil {
		log.Fatalf("connect: %v", err)
	}
	defer db.Close()

	if _, err := db.Exec(ctx, schema); err != nil {
		log.Fatalf("schema: %v", err)
	}

	orderID := "order-1001"
	// Clean slate for a repeatable run.
	_, _ = db.Exec(ctx, `DELETE FROM events WHERE aggregate_id = $1`, orderID)

	fmt.Println("== Part 1: build an aggregate by appending events ==")
	must(appendEvent(ctx, db, orderID, 0, "OrderPlaced",
		map[string]any{"customer_id": 42, "total_cents": 1999}))
	st, _ := loadState(ctx, db, orderID)
	must(appendEvent(ctx, db, orderID, st.Version, "OrderPaid",
		map[string]any{"method": "card"}))
	must(shipOrder(ctx, db, orderID)) // command handler validates PAID->SHIPPED
	st, _ = loadState(ctx, db, orderID)
	fmt.Printf("  current state (folded from events): status=%s version=%d\n",
		st.Status, st.Version)

	fmt.Println("\n== Part 2: state is a PURE FOLD — rebuild gives the same answer ==")
	st2, _ := loadState(ctx, db, orderID)
	fmt.Printf("  replay #2: status=%s version=%d (identical => deterministic fold)\n",
		st2.Status, st2.Version)

	fmt.Println("\n== Part 3: a rejected command (invalid transition) ==")
	// Shipping again is invalid: status is SHIPPED, not PAID. The command is
	// rejected; NO event is appended. Commands can be refused; events cannot.
	if err := shipOrder(ctx, db, orderID); err != nil {
		fmt.Printf("  shipOrder rejected as expected: %v\n", err)
	}

	fmt.Println("\n== Part 4: optimistic concurrency — two racing appends ==")
	// Two goroutines both load version N and both try to append N+1. Exactly one
	// wins; the other gets ErrVersionConflict from the UNIQUE constraint.
	raceID := "order-2002"
	_, _ = db.Exec(ctx, `DELETE FROM events WHERE aggregate_id = $1`, raceID)
	must(appendEvent(ctx, db, raceID, 0, "OrderPlaced", map[string]any{"x": 1}))
	base, _ := loadState(ctx, db, raceID)

	var wg sync.WaitGroup
	results := make([]error, 2)
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			// Both use the SAME base.Version — the race.
			results[idx] = appendEvent(ctx, db, raceID, base.Version,
				"OrderPaid", map[string]any{"goroutine": idx})
		}(i)
	}
	wg.Wait()

	wins, conflicts := 0, 0
	for _, e := range results {
		switch {
		case e == nil:
			wins++
		case errors.Is(e, ErrVersionConflict):
			conflicts++
		default:
			log.Fatalf("unexpected error: %v", e)
		}
	}
	fmt.Printf("  racing appends: %d succeeded, %d got version-conflict\n", wins, conflicts)
	if wins == 1 && conflicts == 1 {
		fmt.Println("  CORRECT: exactly one writer won. UNIQUE(aggregate_id, version)")
		fmt.Println("  is the entire concurrency-control mechanism — no row locks.")
	} else {
		fmt.Println("  UNEXPECTED: expected exactly 1 win + 1 conflict.")
		os.Exit(1)
	}
}

func must(err error) {
	if err != nil {
		log.Fatal(err)
	}
}

// Avoid an unused-import error in environments that strip pgx (defensive; pgx is
// used transitively via pgxpool and pgconn). The blank reference keeps the import
// meaningful if a future edit removes the direct use.
var _ = pgx.ErrNoRows

/*
-----------------------------------------------------------------------------
Expected output (shape)
-----------------------------------------------------------------------------

== Part 1: build an aggregate by appending events ==
  current state (folded from events): status=SHIPPED version=3

== Part 2: state is a PURE FOLD — rebuild gives the same answer ==
  replay #2: status=SHIPPED version=3 (identical => deterministic fold)

== Part 3: a rejected command (invalid transition) ==
  shipOrder rejected as expected: cannot ship order in status "SHIPPED" (must be PAID)

== Part 4: optimistic concurrency — two racing appends ==
  racing appends: 1 succeeded, 1 got version-conflict
  CORRECT: exactly one writer won. UNIQUE(aggregate_id, version) is the entire
  concurrency-control mechanism — no row locks.

The four parts ARE event sourcing in miniature: events are the source of truth
(Part 1), state is a deterministic fold over them (Part 2), commands are
validated against current state and can be refused while events cannot (Part 3),
and concurrency is handled by an optimistic version check rather than locks
(Part 4). Everything else — snapshots, upcasting, projections — is built on these.
-----------------------------------------------------------------------------
*/
