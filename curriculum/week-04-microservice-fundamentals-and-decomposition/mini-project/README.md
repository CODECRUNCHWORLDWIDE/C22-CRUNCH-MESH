# Mini-Project — Scaffold the Seam: `cart` (Go) and `catalog` (Python), Two Databases, One Contract

> Stand up the first two services of the capstone Polyglot Marketplace Backbone as **independently deployable** processes — `cart` in Go, `catalog` in Python — each owning its own Postgres, communicating over an explicit boundary, with the iron rule that **neither service can read the other's database.** This is the seam you turn into a typed gRPC contract in Week 5 and harden into a production service in Week 6.

This is the artifact that makes the week's theory real. You will *not* just diagram a boundary — you will build one that a `grep` can prove holds. After this week, "the only way `cart` learns about a product is by *asking* `catalog`" is not a principle on a slide; it's a property of your running system, enforced by the fact that `cart` does not have, and cannot get, `catalog`'s database credentials.

**Estimated time:** ~12 hours, split across Thursday, Friday, and Saturday in the suggested schedule.

**Compounds forward:** These two services are the spine of everything that follows. **Week 5** replaces the deliberately-crude HTTP boundary you build here with a typed gRPC + Protobuf contract. **Week 6** takes `cart` from skeleton to production-ready (structured logs, health/readiness probes, graceful shutdown, OpenTelemetry, a Helm chart, a runbook). The capstone runs this exact `cart` across two regions. Build the boundary clean now; you will live in it for twenty weeks.

---

## What you will build

Three deliverables:

1. **`catalog` (Python).** A small HTTP service that owns a `catalog` Postgres database (products: SKU, name, price-in-cents, description) and exposes a read API: `GET /products/{sku}` and `POST /products:batchGet` (a bulk endpoint — you learned why in Lecture 2 §2.3). It connects to *its own* database and no other.

2. **`cart` (Go).** A small HTTP service that owns a `cart` Postgres database (carts and line items: cart_id, sku, qty, price_snapshot_cents). It exposes `POST /carts/{id}/items` (add an item) and `GET /carts/{id}` (read the cart). Crucially, when an item is added, `cart` does **not** read `catalog`'s tables — it *calls* `catalog`'s HTTP API to look up the product, and **snapshots the price** into its own table at add-time (locked price; Lecture 1 §7 and the Bookhive checkout team). It connects to *its own* database and no other.

3. **The deployment + the proof.** Both services and both databases running — locally with `docker compose` for the fast loop, then on Kind as four Kubernetes objects (two Deployments, two StatefulSet/Deployment Postgres instances) — plus a `make verify` target that *proves the boundary holds*: `cart` cannot reach `catalog`'s database, and the only `cart`→`catalog` communication is over the HTTP API.

By the end you have a public repo of two independently deployable services that demonstrate database-per-service, the anti-corruption boundary, and price-snapshotting — the three ideas the whole week builds to.

---

## Why two languages

Because the capstone is polyglot and the boundary must survive it. A contract that only works because both sides are Go and share a struct is not a contract — it's a shared library pretending to be a boundary. By making `cart` Go and `catalog` Python *from day one*, you force the boundary to be a real wire protocol (HTTP+JSON now, gRPC+Protobuf in Week 5), not a language convenience. This is the single most valuable constraint in the mini-project: it makes the boundary honest.

---

## Repository layout

```
marketplace-seam/
├── Makefile                      # build, run, verify, deploy targets
├── docker-compose.yml            # fast local loop: 2 services + 2 postgres
├── README.md                     # your writeup: the boundary, the proof, the diagram
├── services/
│   ├── catalog/                  # Python service — owns catalog_db
│   │   ├── app.py                # the HTTP service (stdlib or FastAPI)
│   │   ├── db.py                 # connects ONLY to catalog_db
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   └── seed.sql              # schema + seed products
│   └── cart/                     # Go service — owns cart_db
│       ├── main.go               # the HTTP service
│       ├── catalog_client.go     # the ACL: calls catalog's API, maps DTO->domain
│       ├── store.go              # connects ONLY to cart_db
│       ├── go.mod
│       ├── Dockerfile
│       └── schema.sql
└── deploy/
    └── kind/
        ├── catalog.yaml          # Deployment + Service + Postgres for catalog
        ├── cart.yaml             # Deployment + Service + Postgres for cart
        └── README.md             # kubectl apply order + verification commands
```

---

## Deliverable 1 — `catalog` (Python), owner of `catalog_db`

The catalog service is a thin read service over its own products table. The key property: its database connection string points at `catalog_db` and nothing else. It exposes:

- `GET /products/{sku}` → `{sku, name, price_cents, description}` or `404`.
- `POST /products:batchGet` with `{"skus": ["A", "B"]}` → `{"products": [...]}`. This is the **bulk endpoint** that lets a caller fetch many products in one round trip instead of looping — the structural fix for the chatty mesh (Lecture 2 §2.3).

Requirements:

- It reads `CATALOG_DATABASE_URL` from the environment. That URL points at `catalog_db`. It must **not** read any env var or hold any credential for `cart_db`.
- The DTO it returns is the *catalog's* model (editorial-shaped). It deliberately includes fields `cart` does not need (e.g. `description`, `category`) — so that when `cart` consumes it, `cart` must translate, not adopt. That translation is the anti-corruption layer in Deliverable 2.
- A `seed.sql` creates the `products` table and inserts ~5 products so the service has something to serve.

You may use the standard library `http.server` or FastAPI/uvicorn — your call. Keep it small. The point is the *boundary*, not the framework.

---

## Deliverable 2 — `cart` (Go), owner of `cart_db`, with the ACL

The cart service owns carts and line items. It exposes:

- `POST /carts/{id}/items` with `{"sku": "A", "qty": 2}` → adds the item, **snapshotting the current price** from catalog into the line item, returns the updated cart.
- `GET /carts/{id}` → the cart with its line items and their snapshotted prices.

The two non-negotiable design rules:

1. **`cart` connects only to `cart_db`.** It reads `CART_DATABASE_URL` and nothing else. It has no credential for `catalog_db`. If you find yourself wanting to `SELECT ... FROM products`, stop — you're about to build a shared database. The product data comes from the *API call*.

2. **The anti-corruption layer (`catalog_client.go`).** When adding an item, `cart` calls `catalog`'s `GET /products/{sku}` (or the batch endpoint), receives catalog's editorial DTO, and **translates it at the boundary** into `cart`'s own narrow domain type:

```go
// catalog_client.go — the anti-corruption layer.
// catalog's DTO has fields cart does not care about; we map to cart's domain
// type at the boundary so catalog's model never leaks into cart's core.

// catalogProductDTO mirrors EXACTLY what catalog's API returns (the foreign model).
type catalogProductDTO struct {
	SKU         string `json:"sku"`
	Name        string `json:"name"`
	PriceCents  int64  `json:"price_cents"`
	Description string `json:"description"` // cart does NOT use this
	Category    string `json:"category"`    // cart does NOT use this
}

// Product is cart's OWN narrow domain type. This is the only product shape
// cart's core code ever sees.
type Product struct {
	SKU        string
	Name       string
	PriceCents int64
}

// translate is the anti-corruption layer: foreign DTO -> local domain. If
// catalog changes its DTO, ONLY this function changes; cart's core is untouched.
func translate(dto catalogProductDTO) Product {
	return Product{
		SKU:        dto.SKU,
		Name:       dto.Name,
		PriceCents: dto.PriceCents,
	}
}
```

The price snapshot is load-bearing: when an item is added, `cart` writes the *current* `PriceCents` into the line item's `price_snapshot_cents` column and **never recomputes it.** A later price change in `catalog` does not change what's already in the cart. This is exactly the "locked price is law" rule from Bookhive's checkout team, and it's why the price lives in `cart_db`, not fetched live every read.

Use `database/sql` with the standard `lib/pq` or `pgx` driver. Keep handlers small; the architecture is the lesson.

---

## Deliverable 3 — the deployment and the proof

### Local loop (`docker compose`)

`docker-compose.yml` brings up four containers: `catalog_db` (Postgres), `cart_db` (Postgres), `catalog` (Python), `cart` (Go). Critically, the compose network is configured so that **`cart` can reach `catalog` on its HTTP port but is NOT given `catalog_db`'s credentials or hostname.** The only `cart`→`catalog` path is the API.

A working end-to-end flow:

```bash
make up                       # docker compose up: 2 dbs, 2 services
# add an item to a cart; cart calls catalog under the hood and snapshots price
curl -XPOST localhost:8081/carts/c1/items -d '{"sku":"SKU-1","qty":2}'
curl localhost:8081/carts/c1
# => the cart with the item, name from catalog, price snapshotted at add-time
```

### Kind deployment

`deploy/kind/` applies four objects per service set. Each service's Deployment gets *only its own* database's connection string as a Secret. The `cart` Deployment's env has `CART_DATABASE_URL` and `CATALOG_URL` (the HTTP service) — and *no* `CATALOG_DATABASE_URL`. That omission is the boundary, made operational.

### The proof (`make verify`)

This is the deliverable that proves the week's central rule. `make verify` must:

1. **Grep the source for cross-owned database access** and find none:
   ```bash
   # cart must not name catalog's database anywhere.
   ! grep -rn "catalog_db\|CATALOG_DATABASE_URL" services/cart/
   # catalog must not name cart's database anywhere.
   ! grep -rn "cart_db\|CART_DATABASE_URL" services/catalog/
   ```
2. **Demonstrate the API path works** (add item → cart reflects it with a name from catalog).
3. **Demonstrate the database path is closed** — from inside the `cart` container, an attempt to connect to `catalog_db` fails (no route / no credential). Capture that failure as evidence.

---

## Rules

- **You must not** give `cart` any way to reach `catalog`'s database. No shared connection string, no shared ORM models, no "products" table in `cart_db`. If `grep -rn "CATALOG_DATABASE_URL" services/cart/` returns anything, you've broken the project's reason to exist.
- **You must** snapshot the price into `cart_db` at add-time. Re-fetching the live price on every cart read is a different (and wrong) design — it means a price change retroactively alters carts.
- **You must** route every `cart`→`catalog` product lookup through the anti-corruption layer (`translate`); `cart`'s core code must never see `catalogProductDTO`.
- **You may** use any web framework and any Postgres driver. The boundary is the lesson, not the framework.
- Go 1.23+, Python 3.12+, Postgres 16, Docker, Kind.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c22-week-04-marketplace-seam-<yourhandle>`.
- [ ] `make up` brings up both services and both databases; the end-to-end `curl` flow works (add item → cart shows it with catalog's name and a snapshotted price).
- [ ] `cart` and `catalog` each connect to **only their own** database. `make verify`'s grep checks pass (no cross-owned DB references).
- [ ] The **anti-corruption layer** exists: `catalog`'s DTO is translated to `cart`'s domain type at the boundary; `cart`'s core never references `catalogProductDTO`.
- [ ] The price is **snapshotted** at add-time; changing a product's price in `catalog` after an item is added does **not** change the price already in the cart. Demonstrate this in the README.
- [ ] Both services deploy to Kind; the `cart` Deployment has `CATALOG_URL` but *not* `CATALOG_DATABASE_URL`.
- [ ] `make verify` proves the database path between services is closed (the in-container connection attempt to the foreign DB fails).
- [ ] A `README.md` with the context diagram, the run commands, and a paragraph explaining *why* the price is snapshotted and *why* the ACL exists.
- [ ] Committed and pushed.

---

## Grading rubric (100 points)

| Area | Points | What we look for |
|---|---:|---|
| **Database-per-service discipline** | 25 | Each service owns one DB; no cross-owned credentials; `make verify` grep is clean; the in-container foreign-DB connection demonstrably fails. |
| **The anti-corruption layer** | 20 | `translate()` exists and is the only place catalog's DTO appears in cart; cart's core uses only `Product`; changing catalog's DTO would touch only the ACL. |
| **Price snapshotting** | 15 | Price is locked into `cart_db` at add-time; a later catalog price change does not alter existing carts; demonstrated. |
| **Independent deployability** | 20 | Both services build and deploy separately; the bulk `batchGet` endpoint exists; no sync cycle; each is a clean independent process. |
| **Polyglot honesty** | 10 | `cart` is Go, `catalog` is Python; the boundary is a real wire protocol, not a shared struct. |
| **Docs & hygiene** | 10 | Clear README with the diagram and the "why snapshot / why ACL" paragraph; sensible commits; no secrets or `node_modules`/`vendor` checked in. |

**90+** is portfolio-grade and ready to become the Week 5 gRPC pair and the Week 6 hardened service. **70–89** works but has a leaky boundary or a live-price read. **Below 70** means the boundary isn't actually enforced — fix database-per-service first; it's the whole point.

---

## Stretch goals

- **Batch the add path.** Add `POST /carts/{id}/items:batch` that takes several SKUs and uses catalog's `batchGet` to fetch them all in one round trip — proving you understand the chatty-mesh fix in your own code, not just in the exercise.
- **The fault injection.** Make `catalog` return 500 for a SKU and show how `cart` degrades: does it fail the add, retry, or queue? There's no single right answer — but you must *choose* and document it (foreshadows the resilience patterns in Week 18).
- **Strangler-fig note.** Write a one-paragraph plan for how, if this had started as a monolith, you'd have extracted `catalog` first using the strangler-fig pattern. This is exactly the migration-path section of the challenge memo, applied to your own code.
- **Contract-readiness.** Write down the *shape* of the gRPC contract you'd define next week for `cart`→`catalog` (`GetProduct`, `BatchGetProducts`, the message fields). You'll define it for real in Week 5; sketching it now makes that week faster.

---

## How this connects to the rest of C22

- **Week 5 (gRPC + Protobuf)** replaces the HTTP+JSON boundary with a typed `catalog.v1` contract and generates Go and Python stubs from one `.proto` — making this exact `cart`→`catalog` call type-safe and versioned.
- **Week 6 (the hardened service)** takes `cart` and adds structured logging, health/readiness probes, graceful shutdown, OpenTelemetry, a Helm chart, and a runbook — turning today's skeleton into a service that passes a production-readiness review.
- **The capstone** runs this `cart` across two regions with a CRDT-backed cart state. The database-per-service boundary you enforce today is what makes that possible at all.

When you've finished, push the repo and take the [quiz](../quiz.md).
