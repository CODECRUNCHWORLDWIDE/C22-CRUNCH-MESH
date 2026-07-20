# Week 7 — Exercises

Three focused drills on a running Envoy + gRPC topology. Each takes 30–90 minutes. Do them in order — exercise 3 (the BFF) calls the services that exercises 1 and 2 put behind the proxy. Run everything against your **`cart` and `inventory`** services from Phase 1, deployed to your Kind cluster (or, if your services aren't ready, the standalone gRPC stubs each exercise provides).

## Index

1. **[Exercise 1 — Envoy as ingress in front of cart and inventory](exercise-01-envoy-ingress.md)** — stand up Envoy with a listener, two clusters, and gRPC-capable upstreams; prove the proxy hop with `grpcurl` and the admin `/stats`. (~60 min, guided)
2. **[Exercise 2 — The resilience policy](exercise-02-resilience-policy.yaml)** — a complete Envoy config with per-route timeouts, retries bounded by a budget, outlier detection, and a circuit breaker; drive it with load and watch the stats prove each policy fires. (~60 min, runnable)
3. **[Exercise 3 — The mobile BFF](exercise-03-mobile-bff.go)** — a Go BFF that fans out to `cart` and `inventory` in parallel, batches, degrades gracefully, and returns one response shaped for a phone. (~90 min, runnable)

## How to work the exercises

- Have **Envoy** runnable locally. The simplest path is `func-e`: `curl https://func-e.io/install.sh | bash` then `func-e run -c <config>.yaml`. The official `envoyproxy/envoy:v1.31-latest` container works too.
- Have your **`cart` and `inventory`** services reachable. In-cluster, that's their `Service` DNS names; locally, run them on `localhost` and point the Envoy clusters at `127.0.0.1`.
- **Read the admin endpoint before and after every change.** `curl -s localhost:9901/stats` and `/clusters` are your ground truth. Train the habit of grepping for the cluster you're touching.
- When the proxy "isn't working," check `/config_dump` (did your config load?), then `/clusters` (are the endpoints healthy?), then `/stats` (what happened to the request?). In that order.
- Each runnable exercise ends with an **expected output** block. If your output doesn't match, you're not done.

## Running the exercises

The `.yaml` exercise is run directly with Envoy:

```bash
func-e run -c exercise-02-resilience-policy.yaml
```

The `.go` exercise is a standard Go program. From a module with the generated `cart.v1` / `inventory.v1` stubs on the path:

```bash
go run exercise-03-mobile-bff.go
```

The header of each file lists the exact dependencies and the stub-generation command. If your Phase 1 protos aren't generated, the file's header points you at a minimal `.proto` you can compile in five minutes.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c22-week-07` to compare.
