// Exercise 2 — The Circuit Breaker (runnable)
//
// Goal: Wrap the `payment` dependency in a CIRCUIT BREAKER (sony/gobreaker) with a
//       TIMEOUT and a JITTERED, BUDGETED retry, then PROVE the three reliability
//       behaviors that keep one dependency's failure from becoming a cascade:
//         1. Under healthy payment, calls pass (breaker CLOSED).
//         2. When payment starts failing, the breaker OPENS and calls FAIL FAST
//            (immediately, without burning a timeout or loading the dead dependency).
//         3. After a cooldown, the breaker goes HALF-OPEN, probes, and CLOSES again
//            when payment recovers.
//
//       This is the syllabus pattern: "implement a circuit breaker in Go around the
//       payment dependency." The point is not the library; it's the failure each
//       piece prevents (Lecture 2 §1).
//
// Estimated time: 60 minutes. Runnable.
//
// HOW TO RUN
//   go mod init cb-demo
//   go get github.com/sony/gobreaker/v2
//   go run exercise-02-circuit-breaker.go --fail-rate 0.8 --duration 30s
//
//   --fail-rate is the probability the simulated payment dependency fails. Start at
//   0.0 (all healthy, breaker closed), raise to 0.8 (breaker opens), then the program
//   flips payment back to healthy mid-run so you watch it recover through half-open.
//
// PREREQUISITES
//   - Go 1.22+. No real payment service needed: this models payment with a stub whose
//     failure rate you control, so the breaker behavior is reproducible. Swap callPayment
//     for your real gRPC payment client to wrap the actual dependency.

package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"math/rand"
	"sync/atomic"
	"time"

	"github.com/sony/gobreaker/v2"
)

// --- The simulated payment dependency ----------------------------------------
// failRate is read atomically so we can flip payment healthy/unhealthy mid-run.
var failRate atomic.Uint64 // stored as permille (0..1000) for atomic float-free access

func setFailRate(p float64) { failRate.Store(uint64(p * 1000)) }
func getFailRate() float64  { return float64(failRate.Load()) / 1000.0 }

var errPaymentDown = errors.New("payment: upstream error (503)")

// callPayment simulates the real dependency: it sometimes fails, and a failing call
// is SLOW (it would burn the caller's timeout) — which is exactly why failing fast
// via the breaker matters. Replace this with your gRPC payment client.
func callPayment(ctx context.Context) (string, error) {
	// A failing dependency is typically slow, not instant — model that.
	if rand.Float64() < getFailRate() {
		select {
		case <-time.After(2 * time.Second): // a SLOW failure: holds the caller for 2s
			return "", errPaymentDown
		case <-ctx.Done():
			return "", ctx.Err() // the TIMEOUT cut it short (Lecture 2 §1.1)
		}
	}
	// healthy: fast success
	select {
	case <-time.After(20 * time.Millisecond):
		return "charged", nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

// --- Timeout + jittered, budgeted retry around the call ----------------------

// callWithTimeout bounds every attempt (Lecture 2 §1.1). An unbounded wait is a bug.
func callWithTimeout(parent context.Context, perTry time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(parent, perTry)
	defer cancel()
	return callPayment(ctx)
}

// jitteredBackoff: FULL jitter (random in [0, exp cap]) so retries DON'T synchronize
// into a thundering herd (Lecture 2 §1.2). Plain exponential backoff still synchronizes.
func jitteredBackoff(attempt int, base, cap time.Duration) time.Duration {
	exp := base << attempt // base * 2^attempt
	if exp > cap {
		exp = cap
	}
	return time.Duration(rand.Int63n(int64(exp) + 1)) // random in [0, exp]
}

// A crude global retry budget: retries may be at most ~10% of calls. When failures
// spike, this is exhausted and retries are suppressed — so retries help with isolated
// transients but CANNOT amplify a widespread failure into a retry storm (Lecture 2 §1.2).
var (
	totalCalls atomic.Int64
	retries    atomic.Int64
)

func retryBudgetAvailable() bool {
	t := totalCalls.Load()
	if t < 20 {
		return true // warm-up grace
	}
	return retries.Load()*10 < t // retries < 10% of total
}

// --- The breaker -------------------------------------------------------------

func newBreaker() *gobreaker.CircuitBreaker[string] {
	return gobreaker.NewCircuitBreaker[string](gobreaker.Settings{
		Name:        "payment",
		MaxRequests: 3,               // in HALF-OPEN, allow 3 probe requests through
		Interval:    10 * time.Second, // counters reset every Interval while CLOSED
		Timeout:     5 * time.Second,  // OPEN -> HALF-OPEN cooldown
		ReadyToTrip: func(c gobreaker.Counts) bool {
			// trip OPEN when we've seen enough requests AND the failure ratio is high
			return c.Requests >= 10 && float64(c.TotalFailures)/float64(c.Requests) >= 0.5
		},
		OnStateChange: func(name string, from, to gobreaker.State) {
			fmt.Printf("  >> breaker %q: %v -> %v\n", name, from, to)
		},
	})
}

// doCharge: the full guarded call — breaker wraps (timeout + jittered/budgeted retry).
// When the breaker is OPEN, breaker.Execute returns ErrOpenState IMMEDIATELY (fail fast)
// without ever calling payment — that's the cascade-prevention (Lecture 2 §1.3).
func doCharge(cb *gobreaker.CircuitBreaker[string]) (string, error) {
	totalCalls.Add(1)
	return cb.Execute(func() (string, error) {
		const maxAttempts = 3
		var lastErr error
		for attempt := 0; attempt < maxAttempts; attempt++ {
			if attempt > 0 {
				if !retryBudgetAvailable() {
					break // retry budget exhausted: do NOT amplify a widespread failure
				}
				retries.Add(1)
				time.Sleep(jitteredBackoff(attempt, 50*time.Millisecond, 1*time.Second))
			}
			res, err := callWithTimeout(context.Background(), 200*time.Millisecond)
			if err == nil {
				return res, nil
			}
			lastErr = err
		}
		return "", lastErr
	})
}

func main() {
	failRateFlag := flag.Float64("fail-rate", 0.8, "payment failure probability (0..1)")
	dur := flag.Duration("duration", 30*time.Second, "how long to drive load")
	flag.Parse()

	cb := newBreaker()
	setFailRate(0.0) // start healthy

	fmt.Println("Phase 1: payment HEALTHY — breaker should stay CLOSED, calls pass.")
	deadline := time.Now().Add(*dur / 3)
	var ok, failed, fastFail int
	driver := func(until time.Time) {
		for time.Now().Before(until) {
			_, err := doCharge(cb)
			switch {
			case err == nil:
				ok++
			case errors.Is(err, gobreaker.ErrOpenState), errors.Is(err, gobreaker.ErrTooManyRequests):
				fastFail++ // breaker rejected without calling payment — FAST, cheap failure
			default:
				failed++
			}
			time.Sleep(15 * time.Millisecond)
		}
	}
	driver(deadline)

	fmt.Printf("Phase 2: payment FAILING at %.0f%% — breaker should OPEN and FAIL FAST.\n", *failRateFlag*100)
	setFailRate(*failRateFlag)
	driver(time.Now().Add(*dur / 3))

	fmt.Println("Phase 3: payment RECOVERED — breaker should HALF-OPEN, probe, then CLOSE.")
	setFailRate(0.0)
	driver(time.Now().Add(*dur / 3))

	fmt.Printf("\nResults: ok=%d  fail-fast(breaker open)=%d  slow-failed=%d  retries=%d/%d calls\n",
		ok, fastFail, failed, retries.Load(), totalCalls.Load())
	fmt.Println("Final breaker state:", cb.State())
}

// -----------------------------------------------------------------------------
// Expected output (shape)
// -----------------------------------------------------------------------------
//
//   Phase 1: payment HEALTHY — breaker should stay CLOSED, calls pass.
//   Phase 2: payment FAILING at 80% — breaker should OPEN and FAIL FAST.
//     >> breaker "payment": closed -> open          <-- tripped on the failure ratio
//   Phase 3: payment RECOVERED — breaker should HALF-OPEN, probe, then CLOSE.
//     >> breaker "payment": open -> half-open        <-- cooldown elapsed, probing
//     >> breaker "payment": half-open -> closed      <-- probes succeeded, recovered
//
//   Results: ok=...  fail-fast(breaker open)=...  slow-failed=...  retries=.../... calls
//   Final breaker state: closed
//
// WHAT TO OBSERVE
//   - In Phase 2, once the breaker OPENS, "fail-fast" climbs FAST and "slow-failed"
//     stops climbing — because open calls return INSTANTLY without hitting payment.
//     That is the cascade-prevention: cart isn't burning 2s timeouts on dead payment.
//   - retries stays a SMALL fraction of calls — the retry budget refused to amplify
//     the widespread Phase-2 failure into a retry storm.
//   - In Phase 3, the breaker recovers automatically via half-open probes — no human.
//
// ACCEPTANCE CRITERIA
//   [ ] Phase 1: breaker stays CLOSED, calls succeed.
//   [ ] Phase 2: breaker OPENS; fail-fast count climbs; you can explain why failing
//       fast PROTECTS cart (no thread pile-up on 2s timeouts to a dead dependency).
//   [ ] Phase 3: breaker goes OPEN -> HALF-OPEN -> CLOSED automatically on recovery.
//   [ ] Retries are jittered (full jitter) and budgeted (a small fraction of calls);
//       you can explain why un-jittered, unbudgeted retries cause a thundering herd /
//       retry storm.
//   [ ] Every payment call has a TIMEOUT; you can state why an unbounded wait is a bug.
// -----------------------------------------------------------------------------
