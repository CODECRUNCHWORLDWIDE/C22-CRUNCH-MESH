# Week 6 — Exercises

Three exercises that take a service from "runs" to "production-ready." Do them in order — the audit (1) tells you what's missing, the Go service (2) fixes the runtime behavior, and the Deployment (3) wires it into Kubernetes correctly. The first is a checklist audit; the second is a runnable Go service you can `SIGTERM` and watch drain; the third is a complete manifest you can `kubectl apply`.

## Index

1. **[Exercise 1 — The twelve-factor / readiness audit](exercise-01-twelve-factor-audit.md)** — score the `cart` service against the twelve factors and a production-readiness checklist, producing the gap list the rest of the week closes. (~45 min, guided)
2. **[Exercise 2 — Structured logs, probes, and graceful shutdown](exercise-02-graceful-shutdown.go)** — a runnable Go service with JSON logs, separate liveness/readiness endpoints, and correct `SIGTERM` draining you can observe. (~50 min, runnable)
3. **[Exercise 3 — The hardened Deployment](exercise-03-cart-deployment.yaml)** — a complete Kubernetes Deployment + Service with all three probes, resource requests *and* limits, a non-root `SecurityContext`, a grace period, and a `preStop` hook. (~45 min, applyable)

## How to work the exercises

- Have **Go 1.23+**, **`kubectl`**, and a local **Kind** cluster (`kubectl get nodes` works). `helm` for the mini-project, optional for the exercises.
- Exercise 1 produces a *gap list* — keep it; the mini-project closes every gap on it.
- The Go service (exercise 2) is standalone and uses only the standard library — no external deps — so you can run it anywhere and `kill -TERM` it to watch the drain. The drain behavior is the lesson; read the logs as it shuts down.
- The Deployment (exercise 3) is a complete, applyable manifest. Read every field and know *why* it's there — a readiness review asks "why this value?" for each. The YAML comments explain each.
- When something "should work but doesn't," check in this order: is the container non-root and the port right? does the readiness probe path exist and return 200? is the grace period longer than your drain? This is the operability-debugging discipline.

## Running the Go exercise

```bash
go run exercise-02-graceful-shutdown.go
# in another terminal, watch it drain:
curl localhost:8080/healthz   # liveness: always 200 while alive
curl localhost:8080/readyz    # readiness: 200 when ready, 503 while draining
kill -TERM $(pgrep -f exercise-02)   # watch the graceful-shutdown logs
```

## Applying the Deployment

```bash
kubectl apply -f exercise-03-cart-deployment.yaml
kubectl rollout status deployment/cart
kubectl get pods -l app=cart
# trigger a rolling restart and watch zero-drop behavior:
kubectl rollout restart deployment/cart
```

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-06` to compare.
