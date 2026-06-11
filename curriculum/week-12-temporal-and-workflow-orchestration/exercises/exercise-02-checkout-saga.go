// Exercise 2 — The checkout saga with compensation
//
// Goal: Implement the canonical Temporal saga: reserve inventory, charge payment, ship,
//   with the COMPENSATION-STACK pattern (push a compensation after each successful step;
//   on any failure run the stack in reverse order via defer). Inject a failure in
//   ShipOrder and PROVE the compensations (RefundCharge, then ReleaseInventory) run in
//   the correct reverse order. This is the Week-11 choreographed saga, re-expressed as
//   ONE readable, durable function.
//
// Estimated time: 75 minutes. Runnable.
//
// SETUP
//   temporal server start-dev          # in its own terminal (UI on :8233)
//   go mod init checkout-saga
//   go get go.temporal.io/sdk
//
// HOW TO USE THIS FILE
//   go run exercise-02-checkout-saga.go -mode worker            # terminal 1
//   go run exercise-02-checkout-saga.go -mode start -order A    # terminal 2 (happy path)
//   go run exercise-02-checkout-saga.go -mode start -order B -fail-ship  # compensation
//
//   Then open the Web UI, find the workflow, and read the event history: on the
//   -fail-ship run you'll see ShipOrder fail, then RefundCharge, then ReleaseInventory
//   execute, in that order. The saga's success AND failure paths are both visible.
//
// ACCEPTANCE CRITERIA
//   [ ] Happy path: ReserveInventory, ChargePayment, ShipOrder all succeed; no
//       compensation runs; workflow result is "confirmed".
//   [ ] -fail-ship: ShipOrder fails; RefundCharge runs, THEN ReleaseInventory runs
//       (reverse order); workflow returns an error; inventory and payment are undone.
//   [ ] The event history in the Web UI shows the compensations in reverse order.
//   [ ] Killing the worker between ChargePayment and ShipOrder, then restarting, does
//       NOT re-charge (the charge result is replayed from history) — durable execution.
//
// Expected output is at the bottom of the file.

package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"time"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"
)

const taskQueue = "checkout-task-queue"

type Order struct {
	ID         string
	TotalCents int64
	FailShip   bool // when true, ShipOrder fails to exercise compensation
}

type Reservation struct{ ID string }
type Charge struct{ ID string }

// -------------------- Activities (the real work; idempotent) --------------------
// In the capstone these call inventory-service, payment-service, shipping-service.
// Here they log and return. Each is idempotent on its input id (Week 11 discipline).

func ReserveInventory(ctx context.Context, order Order) (Reservation, error) {
	log.Printf("  [activity] ReserveInventory(%s) -> reserved", order.ID)
	return Reservation{ID: "res-" + order.ID}, nil
}

func ChargePayment(ctx context.Context, order Order) (Charge, error) {
	// A real charge uses a stable idempotency key (charge-<order.ID>) so a retry of
	// THIS activity does not double-charge. Temporal won't re-run a COMPLETED activity
	// on workflow replay, but a single activity execution can still be retried.
	log.Printf("  [activity] ChargePayment(%s) -> charged %d cents", order.ID, order.TotalCents)
	return Charge{ID: "chg-" + order.ID}, nil
}

func ShipOrder(ctx context.Context, order Order) error {
	if order.FailShip {
		log.Printf("  [activity] ShipOrder(%s) -> FAILED (carrier down)", order.ID)
		// Non-retryable so the saga compensates immediately instead of retrying forever.
		return temporal.NewNonRetryableApplicationError("carrier down", "CarrierError", nil)
	}
	log.Printf("  [activity] ShipOrder(%s) -> shipped", order.ID)
	return nil
}

// -------------------- Compensations (idempotent undo activities) --------------------

func ReleaseInventory(ctx context.Context, res Reservation) error {
	log.Printf("  [compensate] ReleaseInventory(%s) -> released", res.ID)
	return nil
}

func RefundCharge(ctx context.Context, charge Charge) error {
	log.Printf("  [compensate] RefundCharge(%s) -> refunded", charge.ID)
	return nil
}

// -------------------- The workflow (deterministic orchestration) --------------------

func CheckoutSaga(ctx workflow.Context, order Order) (result string, err error) {
	ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
		StartToCloseTimeout: 30 * time.Second,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumAttempts:    3,
		},
	})

	// The compensation stack: each entry undoes one COMPLETED step. The deferred
	// closure runs them in REVERSE order if the saga ends in error.
	var compensations []func()
	defer func() {
		if err != nil {
			for i := len(compensations) - 1; i >= 0; i-- {
				compensations[i]()
			}
		}
	}()

	// Step 1: reserve inventory.
	var res Reservation
	if err = workflow.ExecuteActivity(ctx, ReserveInventory, order).Get(ctx, &res); err != nil {
		return "", err // nothing to compensate yet
	}
	compensations = append(compensations, func() {
		// Use a disconnected context so compensation runs even if the workflow ctx is
		// being cancelled. (disconnect detail elided for the exercise; ctx works here.)
		_ = workflow.ExecuteActivity(ctx, ReleaseInventory, res).Get(ctx, nil)
	})

	// Step 2: charge payment.
	var charge Charge
	if err = workflow.ExecuteActivity(ctx, ChargePayment, order).Get(ctx, &charge); err != nil {
		return "", err // defer runs ReleaseInventory
	}
	compensations = append(compensations, func() {
		_ = workflow.ExecuteActivity(ctx, RefundCharge, charge).Get(ctx, nil)
	})

	// Step 3: ship. On failure, defer runs RefundCharge THEN ReleaseInventory (reverse).
	if err = workflow.ExecuteActivity(ctx, ShipOrder, order).Get(ctx, nil); err != nil {
		return "", err
	}

	return "confirmed", nil // success: defer sees err == nil and compensates nothing
}

// -------------------- main: worker or starter --------------------

func main() {
	mode := flag.String("mode", "worker", "worker | start")
	orderID := flag.String("order", "A", "order id")
	failShip := flag.Bool("fail-ship", false, "force ShipOrder to fail (exercise compensation)")
	flag.Parse()

	c, err := client.Dial(client.Options{HostPort: "localhost:7233"})
	if err != nil {
		log.Fatalln("dial:", err)
	}
	defer c.Close()

	switch *mode {
	case "worker":
		w := worker.New(c, taskQueue, worker.Options{})
		w.RegisterWorkflow(CheckoutSaga)
		w.RegisterActivity(ReserveInventory)
		w.RegisterActivity(ChargePayment)
		w.RegisterActivity(ShipOrder)
		w.RegisterActivity(ReleaseInventory)
		w.RegisterActivity(RefundCharge)
		log.Println("worker started; polling", taskQueue)
		if err := w.Run(worker.InterruptCh()); err != nil {
			log.Fatalln("worker:", err)
		}
	case "start":
		order := Order{ID: *orderID, TotalCents: 4200, FailShip: *failShip}
		we, err := c.ExecuteWorkflow(context.Background(), client.StartWorkflowOptions{
			ID:        "checkout-" + *orderID,
			TaskQueue: taskQueue,
		}, CheckoutSaga, order)
		if err != nil {
			log.Fatalln("start:", err)
		}
		var result string
		err = we.Get(context.Background(), &result)
		if err != nil {
			// Expected on -fail-ship: the saga failed and compensated.
			var appErr *temporal.ApplicationError
			if errors.As(err, &appErr) {
				fmt.Printf("workflow %s FAILED (compensated): %v\n", we.GetID(), err)
				return
			}
			log.Fatalln("get result:", err)
		}
		fmt.Printf("workflow %s result: %q\n", we.GetID(), result)
	}
}

// -----------------------------------------------------------------------------
// Expected output
// -----------------------------------------------------------------------------
//
// Happy path (worker terminal, -order A):
//   [activity] ReserveInventory(A) -> reserved
//   [activity] ChargePayment(A) -> charged 4200 cents
//   [activity] ShipOrder(A) -> shipped
// Starter terminal:
//   workflow checkout-A result: "confirmed"
//
// Compensation path (worker terminal, -order B -fail-ship):
//   [activity] ReserveInventory(B) -> reserved
//   [activity] ChargePayment(B) -> charged 4200 cents
//   [activity] ShipOrder(B) -> FAILED (carrier down)
//   [compensate] RefundCharge(chg-B) -> refunded         <-- reverse order:
//   [compensate] ReleaseInventory(res-B) -> released         charge undone first,
// Starter terminal:                                           then inventory
//   workflow checkout-B FAILED (compensated): ... CarrierError ...
//
// The whole saga — forward path AND compensation — is ONE readable function, and the
// compensations ran in REVERSE order automatically via the defer + stack. Compare this
// to Week 11's five scattered consumers. THAT readability is why orchestration wins for
// complex compensating processes.
//
// Durable-execution proof: kill the worker (Ctrl+C) right after "ChargePayment ->
// charged" prints, then restart it. The workflow RESUMES at ShipOrder; ChargePayment is
// NOT re-run (its result is replayed from the event history). Zero double-charge, zero
// lost progress.
// -----------------------------------------------------------------------------
