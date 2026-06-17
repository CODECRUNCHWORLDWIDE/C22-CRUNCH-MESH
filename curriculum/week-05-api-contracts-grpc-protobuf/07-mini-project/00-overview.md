# Mini-Project — Replace the HTTP Seam with a Versioned gRPC Contract

> Take the `cart` (Go) ↔ `catalog` (Python) boundary you built in Week 4 over HTTP+JSON and replace it with a typed, versioned `catalog.v1` gRPC contract. Generate Go and Python stubs from one `.proto`, make `catalog` a gRPC server and `cart` a gRPC client, keep the anti-corruption layer and the price-snapshot invariant, wire `buf lint` + `buf breaking` into CI, and prove the boundary is now compiler-enforced — a renamed field is a build error, not a 3 a.m. `null`.

This is the artifact that turns last week's hopeful boundary into an honest one. After this week, the `cart`→`catalog` call is not a JSON blob held together by a README — it's a contract that both languages are generated from, that a tool checks for breaking changes on every PR, and that a Go client and a Python server share without a single line of common code.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** This gRPC `catalog` is the exact service **Week 6** hardens into production (structured logs through the interceptor, health/readiness probes, graceful shutdown, OpenTelemetry traces threaded through the gRPC interceptor you wire here, a Helm chart, a runbook). The capstone runs gRPC + Protobuf as its entire service backbone — `cart.v1`, `catalog.v1`, `inventory.v1`, `order.v1`, each versioned independently. The contract discipline you build now is the discipline the whole capstone rests on.

---

## What you will build

Four deliverables:

1. **The contract (`catalog/v1/catalog.proto`).** A versioned Protobuf schema for the catalog service — `GetProduct`, `BatchGetProducts`, `ListProducts` (server-streaming) — authored to the style guide (versioned package, `int64` money, well-known `Timestamp`, deliberate field numbers, no `required`). This is the single source of truth both services generate from.

2. **`catalog` as a gRPC server (Python).** Re-implement last week's `catalog` as a gRPC server speaking `catalog.v1`, still owning *only* `catalog_db`, with server reflection enabled (so `grpcurl` can poke it) and a logging interceptor.

3. **`cart` as a gRPC client (Go).** Re-wire last week's `cart` to call `catalog` over gRPC instead of HTTP+JSON. The anti-corruption layer (`translate`) now maps the *generated* `catalogv1.Product` into `cart`'s own domain type — the ACL survives the transport change, which is the point: `cart`'s core never imports `catalogv1`. The price snapshot still happens at add-time.

4. **The CI contract gate.** `buf lint` (enforces the style guide) and `buf breaking` (fails the build on a breaking change) wired into a Makefile target and a GitHub Action, so the contract can't drift or break silently.

By the end you have a polyglot gRPC boundary that is *generated*, *versioned*, *reflection-debuggable*, and *breaking-change-gated* — the production shape of a service contract.

---

## Why replace a working HTTP boundary

Last week's HTTP+JSON boundary *worked*. So why change it? Because "works today" and "stays correct as it evolves" are different properties, and only the second one matters at scale:

- **A typo is a build error, not a runtime 500.** With JSON, `cart` reading `resp["pirce_cents"]` (typo) is a silent `null` → a $0.00 price in a cart → a customer incident. With generated gRPC stubs, `product.PriceCents` is a compiled field; a typo doesn't compile.
- **A renamed field is caught.** If `catalog` renames a field, `cart`'s generated stub changes and `cart` *fails to build* until you reconcile — instead of silently receiving `null`.
- **A breaking change can't merge.** `buf breaking` fails the PR. The contract can't drift.
- **The boundary is self-describing.** Reflection + `grpcurl` means you can debug the live service with no client. JSON-over-HTTP has none of this guarantee.

That's the "typed contract is a moral position" thesis, made operational on your own code.

---

## Repository layout

```
marketplace-seam/                 # evolve last week's repo
├── Makefile                      # gen, lint, breaking, run, verify targets
├── buf.yaml                      # buf module config
├── buf.gen.yaml                  # codegen config (Go + Python)
├── proto/
│   └── catalog/v1/
│       └── catalog.proto         # THE CONTRACT — single source of truth
├── gen/                          # generated; checked in OR generated in CI
│   ├── go/catalogv1/             # Go stubs (for cart)
│   └── py/catalog/v1/            # Python stubs (for catalog)
├── services/
│   ├── catalog/                  # Python gRPC SERVER, owns catalog_db
│   │   ├── server.py             # implements catalog.v1.CatalogService
│   │   ├── db.py                 # connects ONLY to catalog_db
│   │   ├── requirements.txt      # grpcio, grpcio-tools, grpcio-reflection
│   │   └── Dockerfile
│   └── cart/                     # Go gRPC CLIENT, owns cart_db
│       ├── main.go               # HTTP API for cart, calls catalog over gRPC
│       ├── catalog_client.go     # the ACL: catalogv1.Product -> cart.Product
│       ├── store.go              # connects ONLY to cart_db
│       └── go.mod
└── .github/workflows/contract.yml  # buf lint + buf breaking on every PR
```

---

## Deliverable 1 — the contract

Use the `catalog.v1` schema from the exercises as the starting point. The non-negotiables (Lecture 1 §3):

- `package catalog.v1;` — the version is in the package.
- `int64 price_cents` — never a float for money.
- `google.protobuf.Timestamp updated_at` — well-known type, not a hand-rolled epoch.
- Deliberate, stable field numbers; the hottest field (`sku`) is number 1.
- A `BatchGetProducts` bulk RPC — the chatty-mesh fix carried over from Week 4, now typed.

Run `buf lint` and fix anything it flags before you generate. The lint pass is your first gate.

---

## Deliverable 2 — `catalog` as a gRPC server (Python)

Re-implement `catalog` as a gRPC server. The shape:

- It generates its stubs from `proto/catalog/v1/catalog.proto` (Python plugins, or `buf generate`).
- It implements `catalog_pb2_grpc.CatalogServiceServicer`: `GetProduct` (unary, NOT_FOUND for unknown SKU — a real status code, not a 200), `BatchGetProducts` (bulk), `ListProducts` (server-streaming).
- It reads products from `catalog_db` via `db.py`, which connects to `CATALOG_DATABASE_URL` and **nothing else** — the Week-4 database-per-service rule survives the transport change.
- It enables **server reflection** (`grpcio-reflection`) so `grpcurl` works against it.
- It has a logging interceptor that logs method, status code, and duration (the hook for Week 6 tracing).

The key continuity: `catalog` still owns its data and exposes it only through the contract. gRPC replaced HTTP; the boundary is the same boundary, now typed.

---

## Deliverable 3 — `cart` as a gRPC client (Go), ACL intact

Re-wire `cart`'s product lookups to gRPC. The critical design rule — the one the whole week defends — is that **the anti-corruption layer survives the transport change**:

```go
// catalog_client.go — the ACL, now over gRPC.
// cart's CORE code must never import or see catalogv1.Product. Only this file does.

import catalogv1 "github.com/crunchmesh/catalog/gen/go/catalogv1"

// Product is cart's OWN domain type (unchanged from Week 4).
type Product struct {
	SKU        string
	Name       string
	PriceCents int64
}

type CatalogClient struct {
	grpc catalogv1.CatalogServiceClient
}

// GetProduct calls catalog over gRPC and translates the GENERATED type into
// cart's domain type at the boundary. If catalog evolves catalogv1.Product,
// ONLY this function changes; cart's core is untouched. That is the ACL's whole
// job, and it is exactly as valuable over gRPC as it was over HTTP.
func (c *CatalogClient) GetProduct(ctx context.Context, sku string) (Product, error) {
	resp, err := c.grpc.GetProduct(ctx, &catalogv1.GetProductRequest{Sku: sku})
	if err != nil {
		return Product{}, err // a gRPC status (e.g. NotFound) — handle it upstream
	}
	p := resp.GetProduct()
	return Product{
		SKU:        p.GetSku(),
		Name:       p.GetName(),
		PriceCents: p.GetPriceCents(),
	}, nil
}
```

The two invariants from Week 4 must both still hold:

- **`cart` connects only to `cart_db`** — it has no `CATALOG_DATABASE_URL`; it learns about products only by calling the gRPC service.
- **The price is snapshotted at add-time** into `cart_db`; a later price change in `catalog` does not alter an existing cart.

And the new invariant:

- **`cart`'s core never imports `catalogv1`** — only `catalog_client.go` (the ACL) does. Prove it: `grep -rln "catalogv1" services/cart/ | grep -v catalog_client.go` returns nothing.

Use the bulk `BatchGetProducts` for the batch-add path; this is the typed version of the chatty-mesh fix.

---

## Deliverable 4 — the CI contract gate

Wire two checks so the contract can't drift or break silently:

```bash
make lint       # buf lint — enforces the style guide
make breaking   # buf breaking --against '.git#branch=main' — fails on a breaking change
```

And a GitHub Action (`.github/workflows/contract.yml`) that runs both on every PR touching `proto/`. This is the mechanism that turns Lecture 1's evolution rules into an enforced policy: an engineer who reuses a field number or changes a type can't merge. The bot remembers the rules so humans don't have to.

---

## Rules

- **You must not** give `cart` access to `catalog_db` (Week-4 rule, still in force).
- **You must not** let `catalogv1` (the generated type) leak into `cart`'s core. Only the ACL (`catalog_client.go`) may import it. `grep -rln "catalogv1" services/cart/ | grep -v catalog_client.go` must be empty.
- **You must** snapshot the price at add-time into `cart_db`; no live price reads on cart read.
- **You must** generate both Go and Python from the *same* `.proto`; the two services share no code.
- **You must** wire `buf breaking` so the contract is gated in CI.
- **You may** use `buf` or raw `protoc`; `buf` is strongly recommended (it gives you lint + breaking for free).
- Go 1.23+, Python 3.12+, `buf` (or `protoc` + plugins), Postgres 16, Docker, Kind.

---

## Acceptance criteria

- [ ] A public GitHub repo (evolve `c22-week-04-marketplace-seam-<yourhandle>` or fork it to `c22-week-05-...`).
- [ ] `buf lint` passes; `buf generate` produces Go and Python stubs from `catalog.proto`.
- [ ] `catalog` runs as a gRPC server with reflection; `grpcurl -plaintext localhost:50051 list` shows `catalog.v1.CatalogService`; `GetProduct` returns a product and NOT_FOUND for an unknown SKU.
- [ ] `cart` calls `catalog` over gRPC; the end-to-end add-item flow works and the cart shows the catalog name and a snapshotted price.
- [ ] The **ACL holds**: `grep -rln "catalogv1" services/cart/ | grep -v catalog_client.go` is empty (cart's core never sees the generated type).
- [ ] **Database-per-service holds**: `cart` has no `CATALOG_DATABASE_URL`; the Week-4 `make verify` grep is still clean.
- [ ] **Price snapshot holds**: change a price in `catalog` after an item is added; the existing cart's price is unchanged. Demonstrated.
- [ ] `buf breaking` is wired into `make breaking` and a GitHub Action; a deliberately-breaking PR fails the check (show the failing run).
- [ ] A `README.md` with the contract, the run commands, the `grpcurl` cross-check, and a paragraph on why a typed contract is worth replacing a working HTTP boundary.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Contract quality** | 20 | Versioned package; `int64` money; well-known types; deliberate field numbers; `buf lint` clean. |
| **Polyglot interop** | 20 | Python server, Go client, generated from one `.proto`, sharing no code; `grpcurl` reflection works; NOT_FOUND is a status code. |
| **ACL discipline** | 20 | `translate` is the only place the generated type appears in cart; the grep is empty; cart's core uses only `cart.Product`. |
| **Invariants preserved** | 20 | Database-per-service still holds; price snapshot still holds; both demonstrated. |
| **Contract gate (CI)** | 15 | `buf breaking` wired; a breaking PR fails the check; shown in the README. |
| **Docs & hygiene** | 5 | Clear README with the `grpcurl` cross-check; sensible commits; generated code either checked in deliberately or generated in CI, not half-and-half. |

**90+** is portfolio-grade and is exactly what Week 6 hardens into production. **70–89** works but the ACL leaks or the contract isn't gated. **Below 70** means the boundary isn't actually compiler-enforced — fix codegen and the ACL first; they're the point.

---

## Stretch goals

- **Add a bidi `WatchPrices` stream** to `catalog.v1` and implement both ends: the Python server pushes price updates; a Go consumer subscribes/unsubscribes on the same stream. This is the streaming kind the exercises didn't cover (Lecture 2 §1.4).
- **Connect for the browser.** Add a Connect (or gRPC-Web) endpoint so a browser could call `catalog` directly, and explain the HTTP/2-trailers reason it needs the translation (Lecture 2 §2).
- **Interceptor → tracing preview.** Make the server's logging interceptor emit a trace-id and propagate it in metadata; this is the exact seam Week 6 turns into OpenTelemetry. Doing it now makes next week trivial.
- **`buf` registry.** Push the module to the Buf Schema Registry (free tier) and have `cart` depend on the published module instead of a local path — the production shape of sharing a contract across repos.

---

## How this connects to the rest of C22

- **Week 6 (the hardened service)** takes this gRPC `catalog`/`cart` and adds twelve-factor config, structured logging, health/readiness probes, graceful shutdown, OpenTelemetry (threaded through *this week's* interceptor), a Helm chart, and a runbook — a production-readiness review.
- **Weeks 7–9 (the mesh)** put this gRPC traffic behind Envoy/Istio, with mTLS and traffic shifting — and gRPC is exactly the traffic the mesh is best at managing.
- **The capstone** uses gRPC + Protobuf as its entire backbone, with `cart.v1`, `catalog.v1`, `inventory.v1`, `order.v1` versioned independently and gated by `buf breaking` in CI — the discipline you build here, scaled to the whole system.

When you've finished, push the repo and take the [quiz](../05-quiz.md).
