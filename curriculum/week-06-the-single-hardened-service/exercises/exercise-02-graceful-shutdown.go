// Exercise 2 — Structured logs, liveness/readiness, and graceful shutdown (Go)
//
// Goal: Build the runtime behavior every hardened service needs — structured JSON
//       logs, SEPARATE liveness and readiness endpoints (Lecture 1 §3), and
//       correct SIGTERM draining (§4) — in a single standalone Go program you can
//       run, hit, and kill to WATCH the drain. This is the behavior you fold into
//       the gRPC cart service in the mini-project.
//
// Estimated time: 50 minutes. Runnable. Standard library only — no go.mod, no deps.
//
// HOW TO USE THIS FILE
//
//        go run exercise-02-graceful-shutdown.go
//        # serves on :8080. Endpoints:
//        #   GET /healthz  -> liveness:  200 while the process is alive
//        #   GET /readyz   -> readiness: 200 when ready, 503 while draining/starting
//        #   GET /work     -> a "request" that takes ~2s (to have something in flight)
//
//   In another terminal, observe the three behaviors:
//
//     1) Readiness gating on startup:
//          curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/readyz
//          # 503 for the first ~1s (warming up), then 200.
//
//     2) Liveness vs readiness are different:
//          /healthz is 200 the instant the process is up; /readyz lags until ready.
//
//     3) Graceful shutdown (the main event):
//          # start a slow request in the background, THEN SIGTERM:
//          ( curl -s localhost:8080/work & ) ; sleep 0.3 ; kill -TERM $(pgrep -f exercise-02)
//          # Watch the logs: readiness flips to 503 FIRST, the in-flight /work
//          # request COMPLETES, THEN the server closes. Zero dropped requests.
//
// ACCEPTANCE CRITERIA
//
//   [ ] Logs are JSON with time/level/msg and contextual fields.
//   [ ] /healthz is 200 from process start; /readyz is 503 until warm, then 200.
//   [ ] On SIGTERM: readiness flips to 503, in-flight /work finishes, then exit.
//   [ ] A /work request started just before SIGTERM is NOT dropped (it returns 200).
//
// Expected output is at the bottom of the file.

package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

const (
	addr           = ":8080"
	warmupDuration = 1 * time.Second  // simulate cache warm / connection priming
	drainGrace     = 25 * time.Second // bound the drain UNDER the k8s grace period
	workDuration   = 2 * time.Second  // each /work "request" takes this long
)

// readiness is an atomic flag flipped by warmup and by shutdown. Liveness is a
// constant 200 (the process is up); readiness reflects "can I serve right now?".
// This separation is the whole point of Lecture 1 §3.
type appState struct {
	ready    atomic.Bool
	inflight sync.WaitGroup // tracks in-flight /work requests so we can drain them
}

func (s *appState) livenessHandler(w http.ResponseWriter, r *http.Request) {
	// Liveness checks ONLY that the process is alive. No dependencies, ever.
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

func (s *appState) readinessHandler(w http.ResponseWriter, r *http.Request) {
	// Readiness checks ONLY whether THIS replica can serve now. Also no deps.
	if s.ready.Load() {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ready"))
		return
	}
	w.WriteHeader(http.StatusServiceUnavailable)
	_, _ = w.Write([]byte("not ready"))
}

// workHandler simulates a real request that takes time. We register it in the
// inflight WaitGroup so graceful shutdown can wait for it to finish.
func (s *appState) workHandler(w http.ResponseWriter, r *http.Request) {
	if !s.ready.Load() {
		// While draining we refuse NEW work (defense in depth; the LB should have
		// stopped routing to us once readiness flipped, but belt and suspenders).
		http.Error(w, "shutting down", http.StatusServiceUnavailable)
		return
	}
	s.inflight.Add(1)
	defer s.inflight.Done()

	start := time.Now()
	// Simulate work; respect the request context so a client cancel is honored.
	select {
	case <-time.After(workDuration):
	case <-r.Context().Done():
		slog.Warn("work_cancelled", "reason", r.Context().Err().Error())
		return
	}
	slog.Info("work_done", "duration_ms", time.Since(start).Milliseconds())
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("done"))
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	state := &appState{}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", state.livenessHandler)
	mux.HandleFunc("/readyz", state.readinessHandler)
	mux.HandleFunc("/work", state.workHandler)

	srv := &http.Server{
		Addr:              addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second, // basic slowloris protection
	}

	// Warm up asynchronously, then flip readiness. Liveness is already serving.
	go func() {
		slog.Info("warming_up", "duration", warmupDuration.String())
		time.Sleep(warmupDuration)
		state.ready.Store(true)
		slog.Info("ready", "addr", addr)
	}()

	// Serve in a goroutine so main can wait for SIGTERM.
	go func() {
		slog.Info("server_starting", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("listen_failed", "err", err.Error())
			os.Exit(1)
		}
	}()

	// Block until SIGTERM/SIGINT (the disposability contract, Lecture 1 §4).
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	<-ctx.Done()

	slog.Info("shutdown_started")

	// STEP 1: flip readiness to false FIRST, so the load balancer stops routing
	// new traffic to us before we stop accepting. This is the ordering that makes
	// the deploy zero-drop.
	state.ready.Store(false)
	slog.Info("readiness_flipped_to_not_ready")

	// STEP 2: drain in-flight /work requests, bounded under the grace period.
	drainCtx, cancel := context.WithTimeout(context.Background(), drainGrace)
	defer cancel()

	drained := make(chan struct{})
	go func() {
		state.inflight.Wait() // wait for in-flight work to finish
		close(drained)
	}()
	select {
	case <-drained:
		slog.Info("inflight_drained")
	case <-drainCtx.Done():
		slog.Warn("drain_timeout; some requests may not have completed")
	}

	// STEP 3: shut down the HTTP server (stops accepting, closes idle conns).
	shutCtx, shutCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutCancel()
	if err := srv.Shutdown(shutCtx); err != nil {
		slog.Error("server_shutdown_error", "err", err.Error())
	}

	// STEP 4: close backing resources here (DB pool, etc.) AFTER the server has
	// drained, so nothing in flight loses its dependencies mid-request.
	// (No DB in this standalone exercise; the comment marks where it goes.)
	slog.Info("shutdown_complete")
}

// -----------------------------------------------------------------------------
// Expected output (a clean run with a request in flight at SIGTERM)
// -----------------------------------------------------------------------------
//
// {"time":"...","level":"INFO","msg":"server_starting","addr":":8080"}
// {"time":"...","level":"INFO","msg":"warming_up","duration":"1s"}
// {"time":"...","level":"INFO","msg":"ready","addr":":8080"}
// {"time":"...","level":"INFO","msg":"shutdown_started"}
// {"time":"...","level":"INFO","msg":"readiness_flipped_to_not_ready"}
// {"time":"...","level":"INFO","msg":"work_done","duration_ms":2001}   <- the in-flight request FINISHED
// {"time":"...","level":"INFO","msg":"inflight_drained"}
// {"time":"...","level":"INFO","msg":"shutdown_complete"}
//
// The order is the lesson: readiness flips to NOT-ready FIRST (so the LB stops
// routing), THEN the in-flight /work request completes (work_done), THEN the
// server closes. A request that was in flight when SIGTERM arrived was NOT
// dropped. That is the zero-dropped-requests-on-deploy promise from the README,
// reproduced in ~140 lines of standard library.
//
// Contrast: a naive service that calls os.Exit(0) on SIGTERM would kill the
// in-flight /work mid-request — a dropped request on every single deploy.
// -----------------------------------------------------------------------------
