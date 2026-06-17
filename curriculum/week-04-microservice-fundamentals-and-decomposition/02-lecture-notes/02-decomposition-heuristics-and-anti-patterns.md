# Lecture 2 — Decomposition Heuristics and the Four Anti-Patterns

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can apply four decomposition heuristics and reconcile them when they disagree, recognize the four canonical decomposition anti-patterns from a diagram or a diff, and write the decomposition memo a staff engineer actually produces — including the three rejected alternatives.

Lecture 1 gave you the *concepts*: bounded contexts, the language test, Conway's law. This lecture gives you the *procedure*: the heuristics that turn "find the boundaries" into something repeatable, the failure modes that mark a decomposition gone wrong, and the written artifact that records and defends your decision. Three parts: (1) the heuristics, (2) the anti-patterns, (3) the memo.

---

## Part 1 — The decomposition heuristics

A heuristic is not a law; it's a lens. You apply several, and where they agree you have a strong boundary, and where they disagree you have a *decision* to make and to document. Four heuristics carry most of the weight.

### 1.1 Verb over noun (capabilities, not entities)

Decompose by **business capability** — what the system *does* — not by entity — what the system *stores*. A capability is a verb phrase: "place an order," "reserve inventory," "charge a card," "rank search results." An entity is a noun: "order," "inventory," "card," "result."

Why does this matter so much? Because noun-shaped decomposition produces the **entity-service anti-pattern** (Part 2). A `CustomerService` is a noun; it ends up an anemic CRUD wrapper over the `customers` table that every other service calls for every field of customer data. A capability — "manage a customer's billing relationship" — is a verb; it owns the *behavior* and the data behind it, and it exposes operations, not rows.

Concretely on the capstone: there is no `ProductService`. There is a `catalog` capability ("browse and describe products") and a separate `inventory` capability ("track and reserve stock") and a separate `pricing` capability ("compute the price a customer pays"). All three touch "product," but each owns a different *behavior* over it. Verb-shaped.

> **The test:** can you name the service with a verb phrase describing a business capability? `place-orders`, `reserve-stock`, `rank-search`. If the most natural name is a bare noun (`order`, `product`, `user`), pause — you may be about to build an entity service.

### 1.2 The transaction boundary

This is the heuristic with teeth, because it connects directly to the Week 1–2 theory. **Never draw a service boundary through the middle of a transaction that must be atomic.** If two pieces of state must change together, atomically, all-or-nothing — they belong in the *same* service, behind one local database transaction.

The reason is brutal and non-negotiable: **there are no distributed ACID transactions across services in practice.** Two-phase commit (2PC) exists, but it is a blocking, coordinator-fragile protocol that couples availability across services and is rightly avoided in modern microservice design. So if you split an atomic operation across two services, you have two choices, both worse than not splitting: a saga with compensating actions (eventual consistency, Week 12) or a distributed lock (a fencing-token bug waiting to happen, Week 2). Both are real tools, but you reach for them when the boundary *forces* you to, not by choice.

So: find the transactions. Where a single user action must atomically update several things, those things are *inside* one boundary. Where a user action can tolerate "this happens, then a moment later that happens, and if the second fails we compensate," there is a candidate boundary. The seam goes where the atomicity requirement *ends*.

> Example: "decrement stock and record the reservation" must be atomic → same service (`inventory`). "Place the order" and "charge the card" can be a saga with compensation (reserve, then charge, then on payment failure release the reservation) → different services (`order`, `payment`). The boundary follows the atomicity requirement exactly.

### 1.3 Change-frequency clustering

**Things that change together belong together.** If two pieces of functionality are always modified in the same pull request — every time you touch one, you touch the other — they are coupled, and putting them in different services just means every change becomes a coordinated two-service deploy. That is the distributed monolith.

Conversely, functionality that changes on *different* cadences for *different* reasons wants to be split. If the pricing rules change weekly (promotions, A/B tests) but the catalog descriptions change monthly (editorial), splitting `pricing` from `catalog` lets the volatile part deploy fast without dragging the stable part along, and lets the stable part stay stable without absorbing the volatile part's risk.

You can mine this from version control directly. Look at the commit history of the monolith: which files change together? A clustering over co-change is a remarkably good first draft of a service boundary, because it's measured from how the system *actually evolves*, not how you imagine it does.

### 1.4 Data cohesion (a service owns its data)

A service **owns its data and no other service reads its tables.** This is both a heuristic for *finding* boundaries (a cluster of tables that are only ever joined to each other, never to tables elsewhere, is a candidate context) and a *hard rule* for keeping them (the shared-database anti-pattern, Part 2).

The finding-version: draw the entity-relationship diagram of the monolith and look for the cut-points — the places where the foreign-key graph is sparse, where you could slice with the fewest edges crossing the cut. Those sparse cuts are candidate boundaries; dense clusters are single contexts. This is, almost literally, a min-cut problem on the schema graph, and it's why "draw the ERD" is step one of any real decomposition.

The keeping-version: once a service owns a set of tables, *no other service may connect to that database.* The only way to read another service's data is to *ask the service*. This is the database-per-service pattern, and it is the single most important operational rule of microservices. The mini-project enforces it with a `grep`.

### 1.5 When the heuristics disagree

They will disagree. The transaction boundary might want `cart` and `pricing` together (the price must be locked atomically when an item is added); change-frequency wants them apart (pricing is volatile, cart is stable). Now you have a *decision*, and the decision is what the memo (Part 3) records.

The reconciliation rules of thumb, in priority order:

1. **The transaction boundary almost always wins** when atomicity is a hard correctness requirement, because violating it means a saga or a distributed lock, which is a large, permanent complexity tax. Don't split an atomic operation to satisfy a softer heuristic.
2. **Data cohesion wins over verb-vs-noun** when they conflict — a clean data boundary you can enforce beats an elegant capability name you can't.
3. **Change-frequency is the tiebreaker** when the others are silent: of two equally-valid boundaries, prefer the one that lets the volatile parts deploy independently.

The discipline is not "apply heuristic X." The discipline is "apply all four, note where they agree (strong boundaries) and where they fight (decisions), and *write down* how you resolved the fights." A decomposition with no documented tradeoffs is a decomposition where someone hid the hard parts.

---

## Part 2 — The four anti-patterns

You will not memorize the right architecture. You will learn to *smell the wrong ones*, because the wrong ones recur with depressing regularity. There are four canonical decomposition anti-patterns. Learn to recognize each from a diagram, a description, *and* a code diff.

### 2.1 The distributed monolith

**The smell:** services that must be deployed together, in a specific order, and that call each other synchronously in lockstep. You changed one service's API and three others broke; you can't deploy `cart` without also deploying `order` and `inventory` in the same release.

**Why it's the worst one:** you paid the *full cost* of distribution — network calls, partial failure, serialization, operational complexity, distributed debugging — and got *none* of the benefit, because the services aren't independently deployable. A real monolith at least deploys atomically and lets you use a local transaction. A distributed monolith is strictly worse than the monolith it replaced.

**How to recognize it in code:** a release process that lists services in dependency order. A version-coupling where `cart v2.3` only works with `order v2.3`. A synchronous call chain where a single request fans through five services and any one being down fails the whole thing. Shared client libraries that every service must upgrade in lockstep.

**The fix:** make the boundaries real. Asynchronous events where synchronous calls aren't required (so `order` reacts to a `cart.checked-out` event instead of `cart` calling `order` and waiting). Versioned, backward-compatible contracts (Week 5) so `cart v2.3` keeps talking to `order v2.2`. And — often — *re-drawing the boundary*, because a distributed monolith is frequently two services that should have been one (you split through a transaction) or one service that should have been two (you didn't, and they coupled).

### 2.2 The shared database

**The smell:** two or more services read and/or write the same database tables. It looks innocent — "we're both just reading the `products` table, what's the harm?" — and it is the most insidious coupling there is, because *it's invisible in the service code.* Nothing in `cart`'s source says it depends on `catalog`; the dependency is in the schema, where no code review catches it.

**Why it's poison:** the database schema becomes an undocumented, un-versioned shared contract owned by no one. `catalog` can't change its `products` table — rename a column, split a table, add a NOT NULL — without breaking `cart`, and it doesn't even *know* `cart` is reading it. Every schema migration becomes a cross-team coordination event. The services are fused at the data layer no matter how clean the code looks.

**How to recognize it:** `grep -rn "DATABASE_URL" services/` and check whether any service holds a connection string for a database another service owns. Two services with the same JDBC/DSN. A migration in `catalog`'s repo that, when applied, breaks `cart`'s queries. The mini-project's headline check (`grep` for cross-owned `DATABASE_URL`) exists precisely to catch this.

**The fix:** database per service, no exceptions. The *only* way one service reads another's data is by asking it — a synchronous gRPC call (Week 5) for read-your-writes needs, or by subscribing to events / a CDC feed (Weeks 10–14) for an eventually-consistent local copy. Yes, that's more work than a join. The work is the price of the boundary being real.

### 2.3 The chatty mesh

**The smell:** one user action triggers a storm of fine-grained synchronous calls between services. Loading a single order page makes `order` call `cart`, then `catalog` (per line item!), then `pricing` (per line item!), then `inventory`, then `customer` — twenty synchronous hops for one page, each adding latency and each a new failure point.

**Why it hurts:** latency adds up (twenty hops at 10ms each is 200ms of pure network before any work), and failure *multiplies* (if each hop is 99.9% available, twenty hops in series is 98% available — you've turned three nines into less than two). The chatty mesh is what you get when you decompose too finely (entity services, §2.4) and then have to reassemble the data on every request.

**How to recognize it:** an N+1 query problem but across the network — a loop that calls a service once per item. A request whose trace (you'll have OpenTelemetry by Week 6) is a deep, wide tree of synchronous spans. A p99 latency dominated by serial network time, not compute.

**The fix:** coarser boundaries (don't split things that are always fetched together), batch/bulk endpoints (`GetProducts([]sku)` not `GetProduct(sku)` in a loop), and asynchronous data replication (keep a local read-model copy via events so you don't call out at all). Often the deepest fix is re-decomposition: the chatty mesh is usually a symptom of entity services, and the cure is to re-aggregate into capability services.

### 2.4 The entity service

**The smell:** a service per database entity — `CustomerService`, `OrderService`, `ProductService`, `AddressService` — each an anemic CRUD wrapper exposing `create/read/update/delete` over one table, with no behavior of its own. Noun-shaped, as warned in Part 1.

**Why it's the root cause of the other three:** entity services have no business logic, so the logic has to live *somewhere* — and it ends up in whatever orchestrator calls them, which then must make many fine-grained calls (the chatty mesh) to assemble anything useful, and frequently reaches into multiple services' data (tempting the shared database), and couples to all of them at once (the distributed monolith). The entity service is patient zero.

**How to recognize it:** a service whose entire API is CRUD over one table. A service named with a bare entity noun. A service with no domain logic — it's a thin shim over an ORM. The tell: you can't describe what the service *does* without saying "it stores Xs."

**The fix:** decompose by capability, not entity (Part 1.1). Merge the anemic entity services into the capability that *owns the behavior* over those entities. `CustomerService` + `AddressService` + the billing logic that was stranded in the orchestrator become a `billing` context that owns customers' billing relationships and exposes *operations* ("charge this customer," "update billing address") rather than rows.

> **The anti-pattern decision tree** (tape this next to the heuristics): *Services deploy in lockstep?* → distributed monolith. *Two services, one set of tables?* → shared database. *One action, many synchronous hops?* → chatty mesh. *A service that's just CRUD over a table?* → entity service. The four are related: entity services *cause* chatty meshes, which tempt shared databases, which produce distributed monoliths. Cut the root (entity services) and the others often resolve.

---

## Part 3 — The decomposition memo

A topology in your head is worthless; a topology on a whiteboard is ephemeral; a topology in a *memo* is an engineering artifact that can be reviewed, defended, and held to account. The decomposition memo is the deliverable, and it is the thing graded at the Phase 1 architecture review in Week 12. A staff engineer produces this; a junior produces a diagram and calls it done.

### 3.1 What the memo must contain

1. **Context.** One paragraph: what system, what's driving the decomposition (a scaling pain, a team-ownership pain, a deploy-coupling pain). If you can't name the *pain* the decomposition solves, you may not need to decompose at all (Fowler's "MonolithFirst").
2. **The proposed topology.** The list of services/contexts, each with its subdomain classification, its team owner, and its owned data. A context map (the diagram from Lecture 1 §3) with named relationship patterns at every boundary.
3. **The heuristics applied.** For each non-obvious boundary, *which* heuristic put it there and why. "We split `pricing` from `catalog` on change-frequency: pricing changes weekly, catalog monthly."
4. **The data ownership table.** Every service and the tables it owns, with the explicit statement that no service reads another's tables, and the mechanism by which cross-service data is obtained (gRPC call vs event-fed read model).
5. **The three rejected alternatives.** This is the part that distinguishes the memo from a wish. For *each* rejected alternative: what it was, and the specific reason it lost. "Alternative A: a single `ProductService` for catalog+inventory+pricing. Rejected: it's an entity service; the three have different change frequencies and the inventory reservation needs an atomic transaction that catalog reads would contend with."
6. **The risks and the migration path.** What could go wrong, and how you'd get from the current monolith to the target topology incrementally (strangler-fig, not big-bang).

### 3.2 Why three rejected alternatives, specifically

Because **the quality of a decision is visible only in the alternatives you considered and rejected.** Anyone can propose *an* answer. A senior engineer proposes an answer *and demonstrates they explored the space* — that they considered the obvious entity-service split and rejected it for a named reason, considered the do-nothing option and rejected it for a named reason, considered the over-aggregated single-service option and rejected it for a named reason. The rejected alternatives are the *evidence* that the chosen design is the result of analysis, not the first thing that came to mind. A reviewer who sees three well-reasoned rejections trusts the proposal; a reviewer who sees only the proposal assumes you didn't think.

It also defends you against the most common review failure: the reviewer asking "did you consider X?" If X is in your rejected-alternatives section with a reason, you've already won the conversation. If it isn't, you're improvising.

### 3.3 The memo as a living contract

The memo is not write-once. When reality disagrees with it — when a boundary you drew turns out to need a saga you didn't anticipate, or two services you split keep deploying together — you update the memo and record *why the original reasoning was wrong*. This is how an organization accumulates architectural judgment instead of repeating mistakes. The Week 12 architecture review explicitly checks whether your memo has been updated as the `cart` system evolved, because a memo that never changed is a memo nobody used.

---

## Part 4 — A worked decomposition, heuristic by heuristic

Theory becomes muscle only when you watch it applied to a real cut. Take the Bookhive monolith from Exercise 1 — a bookstore with `catalog`, `pricing`, `cart`, `orders`, `inventory`, `payments` all in one Django app and one Postgres — and walk the four heuristics in order, narrating each decision the way the memo would.

**Heuristic 1 — verb over noun.** First pass: name the *capabilities*, not the entities. "Browse and describe books," "compute the price a customer pays," "assemble a cart and check out," "track and reserve stock," "charge and refund." Five verbs. Notice there is no "manage books" verb that spans editorial + stock + price — those are three different behaviors over the same noun, so the noun "book" does not become a service. The verbs are the first draft of the boundaries: `catalog`, `pricing`, `cart`/`checkout`, `inventory`, `payment`.

**Heuristic 2 — the transaction boundary.** Now find the atomic operations and refuse to cut through them. "Decrement stock and write the reservation row" must be atomic — a reservation that decrements stock but doesn't record itself, or vice versa, corrupts inventory. So those two stay inside `inventory`, behind one local transaction. Contrast: "place the order" and "charge the card" need *not* be atomic — you can reserve, then charge, and compensate (release the reservation) if the charge fails. That's a saga, and the seam between `order` and `payment` goes exactly where the atomicity requirement ends. The transaction boundary confirms `inventory` is one service and splits `order` from `payment`.

**Heuristic 3 — change-frequency clustering.** Mine the (hypothetical) git history. `pricing` (promotions, coupons, A/B tests) changes weekly, sometimes daily. `catalog` (descriptions, images, taxonomy) changes monthly. They co-change rarely. Splitting them lets the volatile `pricing` deploy fast without dragging the stable `catalog` along, and lets `catalog` stay stable without absorbing `pricing`'s churn-risk. This heuristic *confirms* the verb-first split of `pricing` from `catalog` — two heuristics agreeing is a strong boundary.

**Heuristic 4 — data cohesion.** Draw the ERD and look for sparse cuts. The `products`/`categories` tables are joined to each other constantly and to almost nothing else — a dense cluster, one context (`catalog`). The `stock`/`reservations` tables likewise (one context, `inventory`). The `promotions`/`tax_rates` tables (one context, `pricing`). The min-cut of the schema graph falls almost exactly where the verbs and change-frequency already put the lines. Four heuristics, one topology: that convergence is what a *strong* decomposition looks like.

**Where they fought.** They didn't, much, on Bookhive — which is itself a finding worth recording in the memo ("all four heuristics agreed on the catalog/pricing/inventory split; the only judgment call was whether `search` is its own context"). When the heuristics *don't* fight, say so; the absence of conflict is evidence the domain has natural seams, and a reviewer values that you checked. When they *do* fight (transaction boundary wants `cart`+`pricing` together for the price-lock; change-frequency wants them apart), you invoke the §1.5 priority order — transaction boundary wins on atomicity — and you *document the loser*, because the next engineer will wonder why `pricing` isn't folded into `cart`.

---

## Part 5 — Service sizing and YAGNI-for-services

A decomposition is not just *where* the lines go; it's *how many* lines. Two failure modes bracket the right answer, and both are common.

**Over-decomposition** is the trendier mistake in 2026. A team reads about microservices, decides "more services = more modern," and ships forty services for a system that has the domain complexity of six. The symptoms are exactly the anti-patterns of Part 2 at scale: entity services everywhere, a chatty mesh on every page, and a distributed monolith because forty services that fine-grained *cannot* be independently meaningful — they only do anything useful in concert. The cognitive load (Lecture 1 §5) overflows every team; nobody understands the whole; an incident touches eight services. Over-decomposition buys you all the operational cost of distribution to solve a problem you didn't have.

**Under-decomposition** is the older mistake: leaving things coupled that have genuinely diverged — a single "commerce" service that owns ordering, payment, fulfillment, and inventory, where the payment team's slow, careful release cadence gates the fulfillment team's fast one, and a memory leak in one takes all four down. The symptom is *ownership pain*: a service that several teams must coordinate to change, which is the §Lecture-1 "owned by everyone and therefore no one" smell.

The corrective for both is **YAGNI applied to services**: *You Aren't Gonna Need It* — don't create a service boundary until a concrete force demands it. The forces that legitimately demand a split are: independent deployability (two parts must ship on different cadences), independent scaling (two parts have wildly different load profiles), team ownership (two teams need to own two things without coordinating on every change), and fault isolation (one part's failure must not take down the other). If *none* of those forces is present, the two things belong in one service — or one modular monolith — until one of them shows up. Newman's "MonolithFirst" is this principle as a starting posture: begin coupled, split when a force *makes you*, and you'll never over-decompose. The capstone `cart` starts as *one* service for exactly this reason; you split `cart-read` from `cart-write` only if and when a real read/write load asymmetry forces it, never on day one because it looks tidy.

> **The sizing rule:** a service is correctly sized when it maps to one bounded context, fits one team's cognitive load, and has at least one of the four splitting forces (deploy / scale / ownership / fault-isolation) justifying its separation from its neighbors. No force, no split. A boundary with no force behind it is a boundary you'll pay for and a benefit you'll never collect.

---

## Part 7 — Resolving cross-service data without a shared database

The single hardest practical question in decomposition is: *if `cart` can't read `catalog`'s tables, how does it get product data?* The shared-database anti-pattern (§2.2) forbids the easy answer. Here are the four legitimate answers, in increasing order of decoupling, each with its trade.

### 7.1 Synchronous query (gRPC call)

`cart` calls `catalog.GetProduct(sku)` at the moment it needs the data. Simple, always-fresh, read-your-writes consistent.

- **Trade:** `cart` is now *available-coupled* to `catalog` — if `catalog` is down, `cart`'s call fails, and you must decide how `cart` degrades (Lecture-6 will make this rigorous; for now: return a typed error, or serve a cached/snapshotted value). Latency adds up if you do it in a loop (the chatty-mesh trap — use bulk endpoints).
- **Use when:** the data must be fresh at read time and a brief dependency coupling is acceptable. A stock check before checkout.

### 7.2 Snapshot-at-write (the price-lock pattern)

`cart` calls `catalog` *once*, at the moment an item is added, and **copies the relevant fields into its own table** (the price snapshot from the mini-project). Subsequent reads never call `catalog`.

- **Trade:** the copy can go stale — but staleness is often *correct* (the price locked at add-time *should not* change when catalog's price changes later). You own a copy, so you own keeping it as-fresh-as-the-domain-requires.
- **Use when:** the value should be frozen at a moment in time, or the read path must not depend on the upstream. The canonical e-commerce pattern.

### 7.3 Event-fed read model (CQRS)

`catalog` *publishes* events (`product.updated`) and `cart` (or a dedicated read service) maintains a local denormalized copy, updated asynchronously as events arrive. `cart` reads its own copy; it never calls `catalog` on the read path.

- **Trade:** *eventual* consistency — the local copy lags the source by the event-propagation delay. You must tolerate "catalog updated a name 200ms ago and cart hasn't seen it yet." And you've taken on the operational weight of an event spine (Weeks 10–11).
- **Use when:** reads vastly outnumber writes, the read path must survive the source being down, and eventual consistency is acceptable. The `search` read model is the textbook case.

### 7.4 Change-data-capture (CDC)

Like 7.3, but instead of the source *publishing* events, a CDC tool (Debezium, Week 14) tails the source's database transaction log and emits change events without the source service writing any publishing code.

- **Trade:** the most decoupled (the source doesn't even know it's being consumed) but the most infrastructure, and it reads the *database* shape, not a curated event — so it can leak schema details (mitigate with a transformation).
- **Use when:** you can't modify the source to publish events, or you want a low-effort stream of every change. The lakehouse feed (Week 15).

### 7.5 The decision

| Need | Pattern | Consistency |
|---|---|---|
| Fresh at read, brief coupling OK | Synchronous gRPC | Strong (read-your-writes) |
| Frozen at a moment | Snapshot-at-write | Frozen on purpose |
| Reads ≫ writes, survive source outage | Event-fed read model | Eventual |
| Can't modify source / want every change | CDC | Eventual |

The wrong answer to "how does `cart` get product data" is *always* "share the `products` table." The *right* answer is one of these four, chosen by the consistency and coupling the boundary needs. Naming which one — and why — for each cross-service read is exactly what the decomposition memo's data-ownership section (§3.1.4) must do. A memo that says "cart reads product data" without saying *how* has hidden the hardest decision in the design.

---

## 6. Recap

You should now be able to:

- Apply the four decomposition heuristics — verb-vs-noun, transaction boundary, change-frequency clustering, data cohesion — and reconcile them when they disagree, in the documented priority order (transaction boundary first).
- Recognize the four anti-patterns — distributed monolith, shared database, chatty mesh, entity service — from a diagram, a description, or a code diff, and prescribe the fix for each.
- Trace the causal chain between the anti-patterns (entity services cause chatty meshes cause shared-database temptation cause distributed monoliths) and know to cut at the root.
- Write a decomposition memo with all six sections, *including three rejected alternatives each with a specific reason*, and explain why the rejected alternatives are the part that makes it a senior artifact.

Next: the exercises put this on a real monolith. You'll draw a context map, score a proposed topology against the heuristics, and run a smell-detector over a topology spec. Continue to [the exercises](../03-exercises/00-overview.md).

---

## Appendix — The anti-pattern field guide

A quick-reference card for code review. When you see the symptom, name the anti-pattern and reach for the fix.

| Symptom you observe | Anti-pattern | First-line fix |
|---|---|---|
| A release runbook lists services "in this order" | Distributed monolith | Backward-compatible contracts; make one coupling edge async |
| Two services share a JDBC/DSN or read the same tables | Shared database | Database-per-service; the owner exposes an API/event, no one else reads its tables |
| `cart v2.3` only works with `order v2.3` | Distributed monolith | Versioned contracts (Week 5); `buf breaking` in CI |
| A request trace is a deep tree of synchronous spans | Chatty mesh | Bulk endpoints; event-fed read models; coarser boundaries |
| A loop that calls a service once per item | Chatty mesh (network N+1) | A bulk `GetXs([]id)` endpoint |
| A service named `XService` with only CRUD | Entity service | Merge into the capability that owns the behavior |
| A "shared models" library every service must upgrade together | Shared database in disguise | Each service owns its types; share a *contract*, not types |
| A "config service" everyone calls on startup synchronously | Chatty mesh + availability coupling | Push config (env/ConfigMap), don't pull it on a hot path |
| One schema migration breaks three other teams | Shared database | The migration's repo owns those tables alone; others consume via API/events |

### A worked code-review example

You're reviewing a PR. The diff adds, to the `order` service, a function:

```python
# order/handlers.py — in the PR under review
def get_order_summary(order_id):
    order = db.query("SELECT * FROM orders WHERE id = %s", order_id)
    # reaching directly into catalog's and pricing's tables:
    product = db.query("SELECT * FROM products WHERE sku = %s", order.sku)
    promo = db.query("SELECT * FROM promotions WHERE sku = %s", order.sku)
    return {...}
```

What do you flag? Two things. First, **`order` is reading `products` and `promotions`** — tables owned by `catalog` and `pricing`. That's the shared database (§2.2): invisible coupling, and a `catalog` schema change will silently break `order`. Second, even if those were `order`'s tables, the *pattern* — fetch the order, then fetch related data per row — is the seed of a chatty mesh if it grows.

The review comment writes itself: *"`order` is reading `catalog`'s `products` and `pricing`'s `promotions` directly — that's a shared database. `order` should call `catalog.GetProduct` / `pricing.GetPrice` over the contract, or (better, since the order is historical) read a price/name **snapshot** it stored at order-placement time. Either way, `order` must not query another service's tables."* That comment, grounded in the named anti-pattern and a named fix, is what senior code review looks like — and it's a comment you can now write on sight.

### Why naming matters more than knowing

You will forget the precise definitions. You will not forget the *smell*, once trained — the little wrongness of a service called `UserService` that only does CRUD, of a release that lists services in order, of a loop that calls out per item. The value of this lecture is not the taxonomy; it's the trained reflex that says "that's a shared database" the instant you see two services with one DSN, *before* the schema migration breaks production. The exercises (the Python scorer, the Go cycle detector) exist to mechanize that reflex so a tool catches what your eye might miss. Run them on your own designs; the smells are invisible until you've trained on them, and then they're everywhere.

---

## Appendix B — The strangler-fig migration, concretely

The decomposition memo's migration path (§3.1.6) should almost never be "big-bang rewrite." The standard, safe pattern is the **strangler fig** (Fowler), named for the vine that grows around a tree until it replaces it. You extract one capability at a time, with the monolith running the whole time, and the system is always shippable.

The shape, for extracting `catalog` out of the Bookhive monolith:

```text
1. Put a routing layer (a gateway / facade) in FRONT of the monolith.
   All traffic still goes to the monolith; the router is a no-op pass-through.

2. Build the new `catalog` service alongside, with its OWN database, seeded
   from (and kept in sync with) the monolith's product tables.

3. Route ONLY catalog read traffic to the new service via the router.
   Everything else still hits the monolith. Watch error rates; roll back the
   route instantly if anything's wrong (it's a router config, not a deploy).

4. Once catalog reads are stable on the new service, route catalog WRITES too,
   and make the new service authoritative. The monolith stops owning products.

5. Delete the product code and tables from the monolith. The vine has replaced
   that branch of the tree.

6. Repeat for the next capability (pricing, then inventory, ...).
```

Why this beats a rewrite: at every step the system is *running and shippable*, each extraction is *independently reversible* (it's a routing change), and the blast radius of a mistake is one capability, not the whole system. The big-bang rewrite — "we'll build the new microservices and cut over on a weekend" — is how migrations become 18-month death marches that ship nothing until the end and then ship a disaster. The strangler fig ships value continuously and de-risks every step.

The hard part is step 2's "kept in sync" — the new service's database must stay consistent with the monolith's during the transition. The tools for that are exactly the cross-service data patterns of Part 7: a synchronous read-through during early reads, then CDC (Week 14) to stream the monolith's changes into the new service's store until it becomes authoritative. The migration path in your memo should name which of these you'll use for the sync, because "keep them in sync" without a mechanism is the hand-wave that sinks migrations.

## Appendix C — A decomposition memo skeleton

Copy this into your homework and fill it in. The headings are the §3.1 sections; the prompts are what each must answer.

```text
# Decomposition memo: <system>

## 1. Context
<What system, what PAIN drives this. If no pain, why decompose at all?>

## 2. Proposed topology
<Context map (diagram). Table: context | subdomain kind | owner | owned tables.
 Every boundary edge labeled with a DDD pattern + mechanism.>

## 3. Heuristics applied
<For each non-obvious boundary: which heuristic, and why. Where two fought,
 which won (transaction boundary first) and why.>

## 4. Data ownership
<Table: every table -> its one owner. For each cross-service read: how it's
 resolved (sync gRPC / snapshot / event-fed read model / CDC). No shared tables.>

## 5. Rejected alternatives (THREE, each with a SPECIFIC reason)
<A) over-decomposed (entity services) -> rejected because ...
 B) under-decomposed (one big service) -> rejected because ...
 C) plausible-but-wrong boundary (e.g. ProductService) -> rejected because ...>

## 6. Risks & migration path
<Strangler-fig steps. Which service extracted FIRST and why. Sync mechanism.>
```

The section that earns the memo its trust is #5. Anyone can write #2. Demonstrating in #5 that you explored and *rejected* the obvious-but-wrong options — with named reasons — is what turns a proposal into a defensible decision. Fill #5 last and fill it hardest.

## References

- *Building Microservices* (2nd ed.), Sam Newman, Chapters 1–3 (decomposition) and *Monolith to Microservices*, Chapters 3–4: <https://www.oreilly.com/library/view/monolith-to-microservices/9781492047834/>
- microservices.io — decomposition patterns and anti-patterns (Chris Richardson): <https://microservices.io/patterns/index.html>
- "Database per service" pattern: <https://microservices.io/patterns/data/database-per-service.html>
- "MonolithFirst", Martin Fowler: <https://martinfowler.com/bliki/MonolithFirst.html>
- "StranglerFigApplication", Martin Fowler: <https://martinfowler.com/bliki/StranglerFigApplication.html>
- *Domain-Driven Design*, Eric Evans, Chapter 15 (Distillation — core/supporting/generic): <https://www.domainlanguage.com/ddd/>
