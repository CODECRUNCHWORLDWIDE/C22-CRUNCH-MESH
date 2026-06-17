# Lecture 1 — Twelve-Factor, Structured Logging, Health Checks, and Graceful Shutdown

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can apply the twelve factors a service author touches daily, emit correlatable structured logs, distinguish liveness from readiness precisely enough to avoid the classic conflation outage, and implement graceful shutdown that drops zero requests on a rolling deploy.

If you remember one sentence from this entire week, remember this one:

> **Production readiness is a checklist, not a vibe. "It works" is not a defensible state; "it reads config from the environment, logs structured JSON to stdout, separates liveness from readiness, and drains in-flight work on SIGTERM" is — because every clause is checkable.**

You have, over the last two weeks, a gRPC `cart` service with a typed contract and a clean boundary. It *runs*. This lecture is about the gap between "runs" and "survives" — the unglamorous operability work that determines whether your service pages you twice a year or twice a week. Almost none of it is business logic. All of it is the difference between a hobby project and a production service.

---

## 1. Twelve-factor, for the service author

The twelve-factor app is a 2011 methodology that has aged remarkably well. You won't recite all twelve in a review, but six of them are decisions you make *every day* as a service author, and getting them wrong is most of what makes a service un-operable. Here they are through an operability lens, not as dogma.

### 1.1 Config in the environment (Factor III)

**Configuration that varies between deploys lives in the environment, not in the code or a committed file.** The database URL, the log level, the OTLP collector address, feature flags — all read from environment variables (or a mounted config source), never hard-coded, never committed per-environment.

Why this is operability, not preference: it means **one image runs in every environment.** The same `cart:1.4.2` image you tested in staging runs in production, configured differently by its environment. If config is baked in, you build a different image per environment, and now "tested in staging" guarantees nothing about production because it's a *different artifact*. One build, many configs, is the whole game. (We refine the precedence — defaults → file → env → flags — in §5.)

### 1.2 Logs as event streams to stdout (Factor XI)

**A service writes its logs to stdout as an unbuffered stream of events and never concerns itself with routing or storage.** No log files, no log rotation in the app, no syslog config in the code. The execution environment (Kubernetes, the container runtime) captures stdout and routes it — to Loki in Week 17, to `kubectl logs` today.

Why: the app shouldn't know or care where logs go. Decoupling production from routing means you can change the log backend without touching a single service. A service that writes to `/var/log/cart.log` is a service that fights the platform and loses logs when the disk fills. Write to stdout; let the platform handle the rest. (What the log lines *contain* is §2.)

### 1.3 Stateless, share-nothing processes (Factor VI)

**The process keeps no sticky state in memory or on local disk between requests.** Any state that must persist goes to a backing service (Postgres, Redis) — an *attached resource* (Factor IV) reached by a URL from config. The process can be killed and replaced at any instant with no data loss.

Why: this is what makes a service *horizontally scalable* and *disposable*. If request N's result depends on in-memory state left by request N−1 on the *same* replica, you can't load-balance freely and you can't lose a replica safely. Statelessness is the precondition for everything in Phases 2–4 — the mesh, autoscaling, multi-region — to work at all.

### 1.4 Disposability: fast startup, graceful shutdown (Factor IX)

**Processes start fast and shut down gracefully.** Fast startup means a new replica joins the pool quickly (good for scaling and recovery). Graceful shutdown means that on `SIGTERM`, the process stops accepting new work, finishes what's in flight, and exits cleanly — *without dropping requests.* This factor is so important it gets all of §4.

### 1.5 Dev/prod parity (Factor X)

**Keep development, staging, and production as similar as possible** — same backing-service types, same OS, same dependency versions. The polyglot-honesty constraint from Week 4 (Go server, Python client) and the "one image everywhere" of §1.1 are both this factor. Divergence between dev and prod is where "works on my machine" lives.

> **The service-author summary:** config from env, logs to stdout, no sticky state, die gracefully, keep environments alike. Five disciplines that cost almost nothing to follow from day one and are agonizing to retrofit. Do them now, on `cart`, so the rest of the course assumes them.

---

## 2. Structured logging

A log line is data, and data has a schema. "Log a string" is an anti-pattern at scale because strings aren't queryable — you can't ask "show me every error on `/checkout` with latency over 500ms for trace `abc`" of a pile of free text. Structured logs are JSON objects with consistent fields, and they make that query a one-liner.

### 2.1 The schema

Every log line should be a JSON object with at least:

- `time` — RFC3339 timestamp.
- `level` — `DEBUG` / `INFO` / `WARN` / `ERROR`, meaning something consistent.
- `msg` — a short, *stable* message (a constant string you can group by, not an interpolated sentence).
- `trace_id` — the OpenTelemetry trace id (Lecture 2), so this log links to its trace.
- contextual fields — `sku`, `cart_id`, `duration_ms`, `grpc_code`, etc., as *named fields*, not embedded in `msg`.

In Go, the standard library's `slog` does this:

```go
logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
slog.SetDefault(logger)

slog.Info("item_added",
	"cart_id", cartID,
	"sku", sku,
	"qty", qty,
	"price_cents", priceCents,
	"trace_id", traceID,
	"duration_ms", time.Since(start).Milliseconds(),
)
// {"time":"2026-06-10T14:03:11Z","level":"INFO","msg":"item_added",
//  "cart_id":"c1","sku":"SKU-1","qty":2,"price_cents":7999,
//  "trace_id":"4bf92f...","duration_ms":3}
```

Note `msg` is the constant `"item_added"`, not `"added 2 of SKU-1 to cart c1"`. The constant is *groupable* — Loki can count `item_added` events; it can't count distinct interpolated sentences. The variables go in fields.

### 2.2 Levels that mean something

- `DEBUG` — developer detail, off in production.
- `INFO` — normal, noteworthy events (an item added, a request served). Sample if high-volume.
- `WARN` — something recovered or degraded but didn't fail (a retry succeeded, a cache miss spiked).
- `ERROR` — a request or operation failed. Every `ERROR` should be actionable; if it isn't, it's a `WARN`.

A log at the wrong level is noise. If `ERROR` fires for things that are fine, on-call learns to ignore `ERROR`, and the one real error is lost in the cry-wolf. Level discipline is alert discipline.

### 2.3 What NOT to log

Never log secrets (passwords, tokens, API keys, the `DATABASE_URL` with its password), PII (card numbers, full addresses, emails — beyond what's lawful and necessary), or whole request/response bodies (they bloat logs and leak data). Log *identifiers* (`cart_id`, `user_id` if permitted), not *contents*. A log pipeline is a data store; treat it like one for compliance. The OWASP logging cheat sheet is the authority here.

---

## 3. Health checking: liveness vs readiness (the conflation that causes outages)

Kubernetes has three probes, and conflating two of them causes one of the most common self-inflicted outages in the ecosystem. Learn the distinction with precision.

### 3.1 The three probes, precisely

- **Liveness** answers *"is this process wedged and in need of a restart?"* If the liveness probe fails, **Kubernetes restarts the container.** Use it to recover from deadlocks and unrecoverable internal states. It should check only the process's *own* health — a cheap internal check that the event loop is turning. It must **not** check dependencies.
- **Readiness** answers *"can this replica serve traffic right now?"* If the readiness probe fails, **Kubernetes removes the pod from the Service's endpoints** (stops sending it traffic) but does **not** restart it. Use it to gate traffic during startup, during a transient inability to serve, and during shutdown draining. It *may* check whether the service is ready to do its job.
- **Startup** answers *"has this process finished booting?"* It gates the liveness and readiness probes for slow starters, so a service that takes 40 seconds to warm a cache isn't killed by liveness at second 10.

### 3.2 The conflation outage

Here is the outage, step by step, and it has taken down major services:

> A team makes their **readiness** probe check a **dependency** — say, `cart`'s readiness checks that it can reach `catalog`. The reasoning sounds good: "don't send traffic to `cart` if it can't reach `catalog`." Then `catalog` has a brief 10-second blip. *Every* `cart` replica's readiness probe fails *simultaneously*. Kubernetes removes *all* of them from the Service. Now `cart` has zero endpoints — a **total outage** — caused by a *transient blip in a dependency* that `cart` could have degraded around. When `catalog` recovers, all replicas come back at once, thundering-herd the now-cold `catalog`, and you oscillate.

The fix is the rule: **readiness checks only what *this* replica needs to serve its own traffic — its own server is up, its own resources are initialized. It does not check dependencies.** A dependency being down is handled in the *request path* (degrade, return a sensible error, circuit-break in Week 18), not by yanking yourself out of rotation. And **liveness *never* checks a dependency** — a dependency outage must never trigger a restart, because restarting doesn't fix someone else's service and a restart loop makes everything worse.

> **The precise rule:** liveness = "restart me if I'm wedged" (self only, cheap, no deps). Readiness = "stop sending me traffic while I can't serve" (self only — *not* deps). Handle dependency failures in the request path, never in the probes. Memorize this; it's the single highest-leverage operational fact in the week.

### 3.3 gRPC health checking

For a gRPC service, the standard is the `grpc.health.v1.Health` service. You implement `Check` (and optionally `Watch`), and Kubernetes' native `grpc:` probe calls it. Your readiness implementation flips the health status to `NOT_SERVING` during shutdown draining (§4) so Kubernetes stops routing to you *before* you stop accepting.

```go
import "google.golang.org/grpc/health"
import healthpb "google.golang.org/grpc/health/grpc_health_v1"

healthServer := health.NewServer()
healthpb.RegisterHealthServer(grpcServer, healthServer)
// Mark serving once initialized:
healthServer.SetServingStatus("cart.v1.CartService", healthpb.HealthCheckResponse_SERVING)
// On shutdown, BEFORE GracefulStop:
healthServer.SetServingStatus("cart.v1.CartService", healthpb.HealthCheckResponse_NOT_SERVING)
```

---

## 4. Graceful shutdown (the zero-dropped-requests discipline)

This is the part that, done right, makes deploys boring — and done wrong, makes every rolling deploy drop requests. The whole `cart` service exists to take requests; dropping them on deploy is unacceptable, and avoiding it is mechanical.

### 4.1 The Kubernetes termination sequence

When a pod is terminated (a rolling deploy, a scale-down, a node drain), Kubernetes does this, roughly in parallel:

1. The pod is marked Terminating; the **endpoints controller** begins removing it from the Service's endpoints (so new traffic stops being routed to it) — *eventually*. This is asynchronous.
2. The `preStop` hook (if any) runs.
3. The container gets **`SIGTERM`**.
4. Kubernetes waits up to **`terminationGracePeriodSeconds`** (default 30s).
5. If the process hasn't exited, it gets **`SIGKILL`** — a hard kill, in-flight requests dropped.

### 4.2 The readiness-removal race (why `preStop` exists)

Step 1 (removal from endpoints) is **asynchronous and not guaranteed to complete before step 3 (`SIGTERM`)**. So there's a window where your process has received `SIGTERM` but the load balancer *still thinks you're a valid endpoint* and keeps sending you new requests. If you stop accepting the instant `SIGTERM` lands, those in-flight new requests are dropped — a deploy-time error.

The standard mitigation is a **`preStop` hook with a short sleep** (e.g. 5 seconds):

```yaml
lifecycle:
  preStop:
    exec:
      command: ["sleep", "5"]
```

The sleep runs *before* `SIGTERM`, giving the endpoints controller time to remove you from rotation, so by the time your process gets `SIGTERM`, traffic has already stopped flowing to you. It's a kludge, but it's the *standard* kludge, and not having it is the #1 cause of "we drop a few requests every deploy."

### 4.3 The shutdown handler

On `SIGTERM`, your process must: stop accepting new work, mark itself not-ready/not-serving, drain in-flight requests, close resources in order (server first, then DB pool, then anything else), and exit — all inside the grace period.

```go
func main() {
	// ... set up grpcServer, db, healthServer ...

	// Catch SIGTERM/SIGINT.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	go func() {
		if err := grpcServer.Serve(lis); err != nil {
			slog.Error("serve failed", "err", err)
		}
	}()

	<-ctx.Done() // block until SIGTERM
	slog.Info("shutdown_started")

	// 1) Flip health to NOT_SERVING so Kubernetes/clients stop routing to us.
	healthServer.SetServingStatus("cart.v1.CartService", healthpb.HealthCheckResponse_NOT_SERVING)

	// 2) GracefulStop drains in-flight RPCs, then stops the server. Bound it.
	done := make(chan struct{})
	go func() {
		grpcServer.GracefulStop() // waits for in-flight RPCs to finish
		close(done)
	}()
	select {
	case <-done:
		slog.Info("graceful_stop_complete")
	case <-time.After(25 * time.Second): // under the 30s grace period
		slog.Warn("graceful_stop_timeout; forcing stop")
		grpcServer.Stop()
	}

	// 3) Close backing resources AFTER the server has drained.
	db.Close()
	slog.Info("shutdown_complete")
}
```

The order matters: flip health *first* (stop new traffic), then drain (`GracefulStop` finishes in-flight RPCs), then close the DB (after no RPC needs it). Closing the DB before draining would fail the in-flight requests you were trying to protect. And the bounded `select` ensures you exit *before* `SIGKILL` even if a request hangs — a hung drain that runs past the grace period gets `SIGKILL`'d and drops requests anyway, so cap it under the grace period and force-stop.

You will implement exactly this in Exercise 2 and *prove* it drops zero requests under a rolling restart in the mini-project.

---

## 5. Configuration hierarchy

Twelve-factor says config in the environment (§1.1), but real services need a *precedence* when multiple sources disagree. The conventional, correct order, lowest to highest priority:

1. **Built-in defaults** (in code) — sane values so the service runs with zero config in dev.
2. **Config file** (mounted ConfigMap) — environment-wide settings.
3. **Environment variables** — per-deploy overrides (the twelve-factor primary).
4. **Command-line flags** — per-invocation overrides, highest priority (great for debugging: `--log-level=debug` beats everything).

Higher sources override lower. So a flag beats an env var beats a file beats a default. This order is right because it goes from *most general* (a default that applies everywhere) to *most specific* (a flag for this one run). Libraries like `viper` (Go) implement this precedence; you can also hand-roll it.

**Secrets** are config with extra rules: they come from the environment or a *mounted Kubernetes Secret file*, never from a committed file, never baked into the image, never logged (§2.3). For now, a `DATABASE_URL` with a password in a Kubernetes Secret mounted as an env var is the standard. The *better* answer — short-lived, rotated, identity-based credentials via SPIFFE/SPIRE — is Week 21; know it's coming, and design so swapping a long-lived secret for a workload identity later touches only the config layer, not the business logic.

---

## 6. Recap

You should now be able to:

- Apply the six twelve-factors a service author touches daily (config from env, logs to stdout, statelessness, disposability, parity, attached resources) and explain each as an operability decision.
- Emit structured JSON logs with a consistent schema and a `trace_id`, use levels that mean something, and never log secrets or PII.
- State the precise difference between liveness and readiness, explain the conflation outage (a dependency-checking readiness probe taking down all replicas at once), and know that probes check *self*, never dependencies.
- Implement graceful shutdown: the `SIGTERM` → flip-health → drain → close sequence, bounded under the grace period, plus the `preStop` sleep that dodges the readiness-removal race.
- Order a configuration hierarchy (defaults → file → env → flags) and handle secrets correctly with a path to workload identity later.

Next: making the service observable — baseline OpenTelemetry traces and RED metrics — packaging it as a Helm chart, and writing the runbook that turns your on-call knowledge into the team's. Continue to [Lecture 2 — Observability, Helm, and the Runbook](./02-observability-helm-and-the-runbook.md).

---

## Appendix A — The full pod-termination timeline, annotated

Graceful shutdown fails when you misunderstand the *ordering* of what Kubernetes does on termination. Here is the precise sequence, with what your service must do at each step.

```text
t=0    Pod marked Terminating.
       │  Kubernetes does TWO things, IN PARALLEL (this is the trap):
       │  (a) endpoints controller starts removing the pod from the Service
       │      (async — may take a few hundred ms to propagate to kube-proxy/LB)
       │  (b) the kubelet begins the container shutdown sequence below
       ▼
t=0    preStop hook runs (if defined).  <-- your `sleep 5` lives here
       │  Purpose: burn time so (a) finishes before SIGTERM, so traffic has
       │  already stopped routing to you when your process starts shutting down.
       ▼
t=5    SIGTERM sent to PID 1 in the container.  <-- your handler fires
       │  Your service: flip readiness/health to not-ready, drain in-flight,
       │  close resources, exit. ALL of this must finish before...
       ▼
t=5..  (grace period counting down from terminationGracePeriodSeconds)
       ▼
t=45   SIGKILL — if the process hasn't exited. In-flight work is DROPPED.
       (with terminationGracePeriodSeconds: 40 and preStop sleep 5)
```

Two facts ruin most first attempts:

1. **Endpoint removal is asynchronous and racy** (step a). Without the `preStop` sleep, `SIGTERM` can arrive while the load balancer still routes new requests to you. Those new requests hit a process that's already shutting down → dropped. The sleep papers over the race.
2. **The grace period is a hard ceiling.** Your *entire* drain (preStop sleep + flip + drain + close) must fit inside `terminationGracePeriodSeconds`, or `SIGKILL` drops whatever's left. So bound your drain *under* the grace period (the exercise uses a 25s drain under a 30s+ grace) and force-stop if it overruns — a forced stop that drops a few requests is strictly better than a `SIGKILL` that drops all in-flight requests.

## Appendix B — Structured logging anti-patterns to avoid

You will be tempted by each of these. Don't.

- **Interpolating variables into `msg`.** `slog.Info(fmt.Sprintf("added %d of %s", qty, sku))` defeats the entire purpose — now `msg` is unique per call and ungroupable. Put variables in *fields*: `slog.Info("item_added", "qty", qty, "sku", sku)`.
- **Logging the whole request/response.** Bloats the log store, leaks PII, and buries the signal. Log identifiers and outcomes, not payloads.
- **Logging the `DATABASE_URL` on startup "to confirm config."** It contains the password. Log the *host and database name*, never the full DSN.
- **`ERROR` for things that are fine.** A cache miss is not an error; a retry that succeeded is not an error. Cry-wolf `ERROR`s train on-call to ignore `ERROR`, and then the one real one is lost. If it's recoverable and recovered, it's `WARN` or `INFO`.
- **No `trace_id` field.** A log line you can't tie to a trace is a log line you can't correlate during an incident. Always attach the active trace id (Lecture 2 §1.2).
- **Logging in a hot loop without sampling.** A per-request `INFO` at 10k RPS is 10k log lines/sec — expensive and unreadable. Sample high-volume info logs; keep every `WARN`/`ERROR`.

The unifying principle: **a log is structured data destined for a query engine (Loki, Week 17), not a sentence for a human to read in a terminal.** Design every log line as a row you'll later filter and aggregate, and these anti-patterns become obviously wrong.

## Appendix C — Config precedence, worked

The defaults → file → env → flags order (Lecture 1 §5) in a concrete example. Suppose `LOG_LEVEL`:

```text
1. Built-in default in code:        info        (so it runs with zero config)
2. ConfigMap mounted at /etc/cart:  warn        (this environment is noisy)
3. Environment variable LOG_LEVEL:  (unset)     (no per-deploy override)
4. Command-line flag --log-level:   debug       (you're debugging this one run)

Effective value: debug  (the flag, highest priority, wins)
```

Remove the flag and it's `warn` (the ConfigMap). Remove that and it's `info` (the default). The order goes most-general (a default for everywhere) to most-specific (a flag for this one invocation), which is exactly the precedence you want: the more specific the source, the more it reflects a deliberate, local intent that should override the general setting. Libraries like `viper` implement this; if you hand-roll it, apply the sources in this order and let later ones overwrite earlier ones.

---

## Appendix D — The readiness/liveness cheat card

Tape this above your monitor. It is the highest-leverage operational table in the week.

| | Liveness | Readiness | Startup |
|---|---|---|---|
| Question | "Am I wedged?" | "Can I serve now?" | "Have I booted?" |
| On failure | Restart container | Remove from endpoints | Hold off liveness/readiness |
| Checks | Self only | Self only | Self only |
| Checks a dependency? | **NEVER** | **NEVER** | **NEVER** |
| Cheap? | Yes (event loop turning) | Yes (initialized + not draining) | Yes |
| Flips during shutdown? | No (still alive) | **Yes** (to not-ready) | n/a |

The one rule under all of it: **probes check the pod itself, never its dependencies.** A dependency outage is a request-path concern (degrade, error, circuit-break), not a probe concern. Violate this and a dependency blip becomes your total outage.

A final note on probe *tuning*: don't make liveness too aggressive. A liveness probe with a 1-second period and a failure threshold of 1 will restart a pod on a single slow response — and under load, every pod gets one slow response eventually, so you get a restart storm that *causes* the outage you feared. Liveness should fire only on genuine wedging: a generous period (10s), a failure threshold of 3, a short timeout. Readiness can be tighter (you *want* to pull a struggling pod out of rotation quickly), but liveness restarts are expensive and should be rare. The default posture: readiness sensitive, liveness forgiving.

The deepest version of the rule is a question to ask of any probe you write: *"if this probe fails, is the right response to restart me / stop my traffic?"* If a `catalog` outage failing your readiness would restart-or-deroute *you* — a service that's perfectly healthy — then the probe is checking the wrong thing. Restart and de-rotation are responses to *your* problems, not the network's. Keep that question in mind and you'll never write the conflation outage.

## References

- The Twelve-Factor App: <https://12factor.net/>
- Kubernetes — Configure Liveness, Readiness, Startup Probes: <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>
- Kubernetes — Pod Lifecycle (termination): <https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination>
- Go `slog` — structured logging: <https://pkg.go.dev/log/slog>
- gRPC Health Checking Protocol: <https://github.com/grpc/grpc/blob/master/doc/health-checking.md>
- gRPC Go `Server.GracefulStop`: <https://pkg.go.dev/google.golang.org/grpc#Server.GracefulStop>
