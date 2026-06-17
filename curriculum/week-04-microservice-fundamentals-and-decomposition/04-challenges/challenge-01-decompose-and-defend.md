# Challenge 1 — Decompose and Defend a 40 kLOC Monolith

**Time estimate:** ~90 minutes.

## Problem statement

You are the staff engineer brought in to lead the decomposition of **Marketplace**, a 40,000-line monolithic e-commerce backend that has outgrown its single-deploy, single-database shape. The CTO wants a service topology and — crucially — a *defense* of it she can take to the board. She has been burned before by an architect who proposed twelve microservices that turned into a distributed monolith, so she will specifically ask: "what else did you consider, and why is this better?"

You will produce the artifact a staff engineer actually produces: a decomposition memo with a context map, the heuristics applied, the data ownership, **three rejected alternatives each with a specific reason**, and a migration path. This mirrors the real skill: the proposal is the easy part; the defense is the job.

## The monolith

Marketplace is a Python/Django monolith with one Postgres database. Here is its shape, distilled from the codebase and the teams who maintain it.

### The modules (and who touches them)

| Django app | Lines | What it does | Hot or cold? |
|---|---:|---|---|
| `catalog` | 6,200 | Product listings, descriptions, images, categories, search indexing | Cold (changes monthly) |
| `pricing` | 3,100 | Base prices, promotions, coupon engine, regional tax | **Hot** (changes weekly; A/B tests daily) |
| `cart` | 2,400 | The shopping cart; add/remove/quantity; checkout entry point | Warm |
| `orders` | 5,800 | Order lifecycle: placed → paid → fulfilled → delivered; order history | Warm |
| `inventory` | 4,300 | Stock counts across 4 warehouses; reservations with 30-min expiry | Warm |
| `payments` | 3,900 | Stripe integration; charges, refunds, chargebacks; idempotency keys | Cold (changes rarely; *must* be correct) |
| `fulfillment` | 4,100 | Warehouse picking, shipping labels, carrier integration, tracking | Warm |
| `accounts` | 3,200 | User auth, profiles, addresses, saved payment tokens | Cold |
| `reviews` | 2,000 | Product reviews and ratings; moderation queue | Cold |
| `notifications` | 1,800 | Email/SMS for order updates, shipping, marketing | Cold |

### The pain (why decompose at all)

- **Deploy coupling.** Every change ships the whole monolith. The `pricing` team wants to deploy A/B tests daily but is blocked behind `payments` changes that need a slow review. One slow module gates ten fast ones.
- **Scaling mismatch.** `catalog` and `search` take 80% of the read traffic; `payments` takes 2% but must never go down. They scale together because they deploy together — wasteful and risky.
- **Ownership rot.** The `promotions` table (owned conceptually by `pricing`) is read directly by `cart`, `orders`, and `fulfillment`. A `promotions` schema change last quarter broke checkout in production. Nobody knew `fulfillment` read it.
- **Cognitive overload.** No one understands the whole thing. Onboarding takes three months.

### Known cross-module data reads (the shared-database reality)

Today, with one database, these direct table reads exist across module lines:

- `cart` reads `catalog.products` and `pricing.promotions` directly.
- `orders` reads `catalog.products`, `pricing.promotions`, `inventory.stock`, `accounts.addresses` directly.
- `fulfillment` reads `orders.orders`, `inventory.stock`, `accounts.addresses`, and `pricing.promotions` (for packing-slip discounts).
- `notifications` reads `orders.orders`, `accounts.users`, `fulfillment.shipments`.
- `reviews` reads `catalog.products`, `accounts.users`.

Every one of these is a future shared-database coupling you must resolve in the target topology.

## Your task

Produce a decomposition memo (`challenge-01-memo.md`) with **all six sections** from Lecture 2 §3.1:

1. **Context.** One paragraph naming the *pain* the decomposition solves (deploy coupling, scaling mismatch, ownership rot). If you decide some modules should *stay* in a monolith, say so and why — not everything must be a service (Fowler's MonolithFirst applies even when splitting).

2. **The proposed topology.** Your services/contexts, each with subdomain kind (core/supporting/generic), team owner, and owned tables. A **context map** (Mermaid or hand-drawn-and-photographed) with a *named DDD relationship pattern* at every boundary. Apply the language test — note where a noun (e.g. "product," "address," "user") means different things in different contexts and split accordingly.

3. **The heuristics applied.** For each non-obvious boundary, name which heuristic put it there:
   - Where did the **transaction boundary** keep things together? (Hint: "reserve stock and record the reservation" is atomic; "place order" and "charge card" is a saga.)
   - Where did **change-frequency clustering** split things? (Hint: hot `pricing` vs cold `catalog`.)
   - Where did **data cohesion** draw a line?
   - Where two heuristics disagreed, state which won and why (transaction boundary wins on atomicity; §1.5).

4. **The data ownership table.** Every service and the tables it owns, the explicit statement that no service reads another's tables, and *how each of the known cross-module reads above is resolved* — gRPC call, or event-fed read model. Every direct read in the "Known cross-module data reads" list must have a resolution.

5. **Three rejected alternatives**, each with a *specific* reason it lost. You must include at least these forms (you may add more):
   - An **over-decomposed** alternative (e.g. an entity service per table — `ProductService`, `UserService`, `AddressService`). Reject it by naming the anti-pattern and its consequence.
   - An **under-decomposed** alternative (e.g. leave `orders` + `payments` + `fulfillment` as one "commerce" service). Reject it by naming what pain it fails to solve.
   - A **plausible-but-wrong boundary** (e.g. a single `ProductService` unifying catalog + inventory + pricing). Reject it with the heuristic it violates (these three have different change frequencies AND inventory needs atomic reservation transactions catalog reads would contend with).

6. **Risks and migration path.** How you get from the monolith to the target *incrementally* (strangler-fig, not big-bang). Which service do you extract *first*, and why? (Hint: the one whose extraction relieves the most pain with the least risk — often the hot, well-bounded one with few inbound reads.)

## Use the tools

Before you submit, run the topology through the exercise tools:

- Encode your proposed topology in `exercise-02-decompose-the-monolith.py`'s `Topology` form and run it. It must report **0 ERROR** (no shared tables, no entity services). If it flags a smell, fix the topology, not the tool.
- Encode your call graph in `exercise-03-distributed-monolith-smell.go`'s `Topology` form and run it. It must report **no sync cycle** and an acceptable chain depth. If `orders` calls `payments` synchronously and `payments` calls back into `orders`, you have a cycle — break it with an event.

Paste both tools' final output into the memo as evidence (this is the "use at least two independent signals" discipline from the exercises, applied to your own design).

## Acceptance criteria

- [ ] `challenge-01-memo.md` exists with all six sections.
- [ ] The context map has a *named* relationship pattern at every boundary; at least one **anti-corruption layer** appears and is justified.
- [ ] **No entity services** — no `ProductService`/`UserService`/`AddressService` in the chosen topology. (They may appear only in the *rejected* alternatives.)
- [ ] Every one of the five "Known cross-module data reads" is explicitly resolved in the data-ownership table (gRPC or event-fed read model), and **no service reads another's tables** in the target.
- [ ] **Three rejected alternatives**, each with a *specific* reason — not "it was worse," but a named anti-pattern or violated heuristic.
- [ ] The exercise tools report 0 ERROR and no sync cycle on your proposed topology, with their output pasted in as evidence.
- [ ] A migration path that names the *first* service to extract and why.
- [ ] Committed to your Week 4 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The seductive wrong answer is the **single `ProductService`**. "Product" appears in catalog, inventory, and pricing, so it *feels* like it should be one service. But — language test — a product is a rich editorial object in catalog, a stock-counted SKU in inventory, and a price-bearing item in pricing. Three meanings, three contexts. Worse: inventory's reservation must be an *atomic transaction* (decrement stock + record reservation), and if catalog's high-volume reads share that database, they contend with the reservation locks. Unifying them couples a hot read path to a transactional write path — the worst of both. If your chosen topology has a `ProductService`, you fell in the trap; move it to your rejected-alternatives section with this exact reasoning and re-decompose.

A second, subtler trap: resolving the `promotions` cross-reads by making `promotions` a *shared library* that every service imports. That's the shared database wearing a code costume — every service still couples to the promotions schema, just via a package version instead of a table. The right answer is `pricing` owns promotions and *exposes a computed price* (`pricing.ComputePrice(sku, region) -> Money`); no one else knows promotions exist.

## Stretch

- Run the **inverse Conway maneuver** on your topology: write the team structure (stream-aligned teams, platform team) that would *produce* this architecture, and name the one boundary most at risk of eroding if two contexts share a team.
- Pick the open-source monolith you know best (Mastodon, Discourse, Sentry self-hosted) and write the *one-paragraph* version of this memo for it. You'll expand exactly this into the Week 12 midterm architecture-review essay.
- Add a `search` context as a read model fed by `catalog` changes. Defend *why it's event-fed and not a synchronous call into catalog* — this is your first taste of the Weeks 10–14 eventing material, and the answer ("search must survive catalog being down, and search reads vastly outnumber catalog writes") is the canonical CQRS justification.

## Why this matters

In Week 12 you defend your `cart` system at the Phase 1 architecture review in front of two external reviewers. They will not ask you to recite the anti-patterns — they'll point at a boundary on your design and ask "why there, and what did you reject to get there?" This challenge *is* that conversation, rehearsed against a harder problem than your own system. Every senior design loop you'll ever sit eventually hands you a monolith and asks you to draw the lines and defend them. The engineer who can name three rejected alternatives without flinching is the one who gets the staff offer.
