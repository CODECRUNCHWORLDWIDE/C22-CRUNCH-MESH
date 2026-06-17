# Lecture 1 — Bounded Contexts and Conway's Law: How to Draw the Lines

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can define a bounded context precisely, distinguish it from a subdomain and from a service, produce a context map for a domain, predict the architecture an org chart will produce via Conway's law, and apply the inverse Conway maneuver to get the architecture you want.

If you remember one sentence from this entire week, remember this one:

> **A microservice boundary is a boundary of change and ownership, not a boundary of nouns. You find it where the language changes — where the same word means two different things to two different teams — and you cut there, because that cut follows the domain and the org, and so it survives.**

The first three weeks taught you that distributed systems fail in ways single machines do not: partitions force a consistency-or-availability choice, there is no global clock, and distributed transactions are not free. All of that is *background radiation* for this week. The decision that determines whether you ever have to confront those failures — and how often — is where you draw your service boundaries. Draw them well and most of your traffic stays inside a single service where a local transaction still works. Draw them badly and every user action becomes a distributed transaction across six services, and you spend the rest of the course paying for it.

ROS people, web-backend people, and data engineers all arrive with the same wrong instinct: decompose by *entity*. This lecture replaces that instinct with a method.

---

## 1. Domain, subdomain, bounded context — three different things

People use these three words interchangeably and it ruins their architecture. They are not the same.

### 1.1 Domain

The **domain** is the whole problem space your organization operates in. For the capstone, the domain is *online retail / e-commerce*. It is enormous, it is messy, and no single model can describe all of it coherently. That last clause is the whole reason bounded contexts exist.

### 1.2 Subdomain

A **subdomain** is a slice of the domain. Domain-Driven Design (DDD) classifies subdomains into three kinds, and the classification drives your investment decisions:

- **Core subdomain** — where your competitive advantage lives. For a retailer, maybe it's the recommendation engine or the dynamic-pricing logic. You build this yourself, with your best engineers, and you guard the model jealously.
- **Supporting subdomain** — necessary for the business but not differentiating. Order fulfillment, inventory tracking. You build it, but you don't gold-plate it.
- **Generic subdomain** — a solved problem you should buy or adopt. Authentication, payments (the rails, not your business logic on top), email delivery. You use Stripe, you use Auth0 or Keycloak, you do not write your own.

The classification matters because **you do not spend core-subdomain effort on a generic subdomain.** A team that builds its own auth service from scratch while a competitor adopts Keycloak and pours that energy into the recommendation engine will lose. Part of decomposition is deciding which subdomains you even own.

### 1.3 Bounded context

A **bounded context** is the boundary within which a single model — a single *ubiquitous language* — is internally consistent. Inside the context, every term means exactly one thing. Cross the boundary and the same word can mean something different.

The canonical example: the word **"customer."**

- In the **Sales** context, a Customer is a lead: a name, a company, a deal stage, a probability-to-close.
- In the **Billing** context, a Customer is a payment instrument and a billing address and a tax status.
- In the **Support** context, a Customer is a ticket history and an entitlement tier.
- In the **Shipping** context, there is no Customer at all — there is a *Recipient* with an address and a delivery preference.

These are *four different models of the same word.* The mistake — the one that produces the entity-service anti-pattern we cover in Lecture 2 — is to build a single `CustomerService` that tries to be all four. It becomes a god object with a bloated schema, owned by no one, that every team must coordinate to change. The DDD answer is the opposite: **let each context have its own Customer.** They are linked by an identifier, not unified into one model.

> **The litmus test for a context boundary:** stand at a proposed boundary and ask, "does a core noun mean the same thing on both sides?" If yes, you may have cut through the middle of a context — bad. If no — if "order" means *a thing being assembled in a warehouse* on one side and *a line on an invoice* on the other — you have found a real boundary. Cut there.

### 1.4 A bounded context is not (necessarily) a microservice

This is the distinction that separates people who have read Evans from people who have read a slide about Evans.

- A **bounded context** is a *modeling* concept. It's a boundary in the domain.
- A **microservice** is a *deployment* concept. It's an independently deployable process.

The default, sane mapping is **one bounded context → one service.** But it is not a law. A single bounded context might, for performance or team reasons, be implemented as two or three services. Early on, several bounded contexts might live inside one deployable monolith (a "modular monolith") with the boundaries enforced in code, deferring the operational cost of distribution until you've earned it. Newman is emphatic about this: **the bounded context is the unit you reason about; the service is an implementation decision you make later, and conservatively.**

So the sequence is: find the bounded contexts (modeling), *then* decide how to deploy them (operations). Never the reverse. If you start by deciding "we'll have twelve microservices" and then look for twelve things to put in them, you will produce twelve entity services and a distributed monolith.

---

## 2. The ubiquitous language is the thing you're actually protecting

A bounded context's most valuable asset is its **ubiquitous language**: the vocabulary that is used *identically* in the domain experts' conversation, in the code, in the API, and in the database schema. When a product manager says "a parked order," there is a `ParkedOrder` in the code, not an `Order` with a `status='PARKED'` flag that three developers interpret three ways.

Why does this matter for decomposition? Because **the boundary of the ubiquitous language is the boundary of the context.** The moment you find yourself saying "well, *here* an order is X, but over *there* an order is Y," you have located a context boundary empirically. You did not invent it; you discovered it in the way the business actually talks.

A practical exercise you'll do this week: take a transcript of how different teams describe the same workflow and highlight every place a word changes meaning. Each meaning-shift is a candidate boundary. This is not hand-waving — it is the single most reliable boundary-finding technique in the DDD toolkit, more reliable than any diagram, because it follows the domain rather than the schema.

---

## 3. The context map: the artifact you actually produce

A list of contexts is not enough. You must also describe *how the contexts relate*, because the relationships are where the coupling — and the future pain — lives. The artifact that captures this is the **context map**. DDD names nine relationship patterns; you must know at least these five cold:

| Pattern | What it means | When you use it |
|---|---|---|
| **Shared kernel** | Two contexts share a small, jointly-owned model subset. | Two teams that genuinely must agree on a core type and can coordinate changes. Use *sparingly* — it's tight coupling by design. |
| **Customer–Supplier** | A downstream context depends on an upstream one; the upstream considers the downstream's needs. | The normal, healthy dependency: `order` (customer) depends on `inventory` (supplier), and `inventory` plans its changes around `order`. |
| **Conformist** | Downstream simply accepts the upstream model as-is, no translation. | When the upstream is a powerful external system you can't influence (a payment processor's API) and translating isn't worth it. |
| **Anti-corruption layer (ACL)** | Downstream wraps the upstream behind a translation layer that converts the foreign model into the local one. | When you depend on a messy or legacy upstream and must *not* let its model leak into yours. The single most valuable pattern in the catalog. |
| **Open-host service + Published language** | Upstream offers a well-documented, stable, versioned API (a "published language") for many downstreams. | When many contexts consume you — exactly what a typed gRPC contract (Week 5) gives you. |

The **anti-corruption layer** deserves emphasis because it is the pattern juniors skip and seniors reach for reflexively. Picture `cart` needing product data from a legacy `catalog` whose API returns a baroque DTO with forty fields, snake_case mixed with camelCase, prices in cents-as-strings, and a `deleted` flag that's sometimes `"Y"` and sometimes `true`. If you let that DTO flow into `cart`'s domain, `cart`'s code is now coupled to `catalog`'s historical accidents forever. The ACL is a thin translation package inside `cart` that takes the ugly DTO at the boundary and produces a clean `cart.Product` domain type. `catalog` can change its DTO; only the ACL changes; `cart`'s core is untouched. You will build exactly this in the Week 4 stretch goal and use it constantly thereafter.

Here is a minimal context map for the capstone domain, expressed as a table — the form you'll deliver in the exercises:

| Context | Subdomain kind | Team owner | Upstream of | Downstream of | Integration at boundary |
|---|---|---|---|---|---|
| `cart` | Core | Cart team | `order` | `catalog`, `pricing` | gRPC published language; ACL over `catalog` |
| `catalog` | Supporting | Catalog team | `cart`, `search` | — | Open-host gRPC service |
| `inventory` | Supporting | Inventory team | `order` | — | Customer–supplier with `order` |
| `order` | Core | Order team | `payment`, `fulfillment` | `cart`, `inventory` | Orchestrator; gRPC + events |
| `payment` | Generic (rails) | Payments team | — | `order` | Conformist over external PSP |

Read the integration column. Every boundary has a *named* relationship and a *named* mechanism. A context map with arrows but no pattern names is decoration. The patterns are the point.

---

## 4. Conway's law: your architecture will look like your org chart

In 1968 Melvin Conway published an observation that has survived sixty years of being rediscovered:

> "Any organization that designs a system (defined broadly) will produce a design whose structure is a copy of the organization's communication structure."

This is not a tendency or a risk. On a long enough timeline it is a near-certainty, and the mechanism is simple: two modules that must talk require the two teams that own them to talk, and teams that can't easily communicate will design interfaces that minimize the need to. If you have four backend teams in three time zones, you will get an architecture whose seams fall on the communication-cost boundaries between those teams — regardless of where the *domain's* seams actually are.

The implications for decomposition are sharp:

- **If your org and your domain agree, you're lucky.** Conway's law works *for* you: the team boundaries already match the context boundaries, and the architecture falls out naturally.
- **If your org and your domain disagree, the org wins.** You can draw the "correct" domain boundaries on a whiteboard all day; the system will drift back toward the org chart, because that's the path of least communication resistance. The famous symptom is a "shared" service that every team must coordinate to change — a service that exists because *no single team owns the boundary*, so it became everyone's and therefore no one's.

This is why "just draw better boundaries" is naive advice. The boundaries are partly a *people* problem, and you cannot solve a people problem with a diagram.

---

## 5. The inverse Conway maneuver: reshape the teams to get the architecture

If the org chart determines the architecture, then the lever that actually works is to **change the org chart on purpose to produce the architecture you want.** This is the *inverse Conway maneuver*, and it is the single most powerful — and most underused — architectural tool a staff engineer has.

Concretely: you want a `cart` service and a `catalog` service with a clean boundary between them. Conway says you will get that boundary cleanly *only if there is a cart team and a catalog team with a customer–supplier relationship and a deliberately narrow communication channel between them* (a documented API, not a shared Slack channel where they negotiate schema changes ad hoc). So before you write a line of code, you advocate for that team structure. If instead you have one big "backend team" that owns both, Conway predicts the boundary will erode: the same people maintain both sides, so they'll reach across it for convenience, share a database "just this once," and within a year you have a distributed monolith with two deploy artifacts and zero independence.

**Team Topologies** (Skelton & Pais) systematized this. The key ideas you need:

- **Stream-aligned teams** own a slice of the domain end to end — ideally one bounded context. This is your default team type and your default service owner.
- **Platform teams** provide the substrate (the Kubernetes platform, the mesh, the CI) so stream-aligned teams move fast without each reinventing it. (This course is, in a sense, training platform engineers.)
- **Team cognitive load is a hard constraint.** A team can only hold so much in its head. A bounded context sized to one team's cognitive load is a *good* service boundary; one that overflows it is two services waiting to happen, and one far below it is over-decomposition.

> **The maneuver, stated operationally:** decide the architecture you want, derive the team structure that Conway's law would produce that architecture from, and then advocate for that team structure as hard as you advocate for the design. An architecture proposed without a team structure to sustain it is a wish, not a plan.

---

## 6. The two-pizza team, re-examined

Amazon's "two-pizza team" — a team small enough to be fed by two pizzas — is the most-cited and most-misunderstood story in microservices. Let's correct it from the primary source (Werner Vogels's 2006 ACM Queue interview, in the resources).

What the two-pizza team actually optimized for:

- **Single ownership.** One team owns a service end to end — "you build it, you run it." The team that writes the code carries the pager. This couples the cost of bad design to the people who can fix it, which is the whole point.
- **Independent deployability.** A two-pizza team must be able to ship its service without a cross-team release train. That independence is the *benefit* of microservices you are paying the distribution cost to get. If two services can't deploy independently, you have the cost without the benefit — a distributed monolith.

What the two-pizza team did *not* mean:

- It did **not** mean "a service per developer." The team is two-pizza-*sized* (roughly 6–10 people), and it might own one service or a few closely related ones. The unit is the *team's ownership*, not the headcount-to-service ratio.
- It did **not** mean "smaller is always better." Amazon did not shard services until the team owning them felt the cognitive-load pain. They split when ownership became unclear, not on a schedule.

The honest summary a senior engineer gives in 2026: **the two-pizza team is an org-design idea wearing a service-size costume.** The size of the pizza order tells you the size of the *team*; the team's cognitive load tells you the size of the *service*; and a service exists to give one team a thing it can own, deploy, and operate alone. Decompose to that, not to a number.

---

## 7. A worked example on the capstone domain

Let's apply sections 1–6 to the capstone — the Polyglot Marketplace Backbone — so the method is concrete.

**Step 1 — Domain and subdomains.** The domain is online retail. Subdomains, classified:

- *Cart* — core-ish (the conversion funnel is where money is made; smooth cart UX is differentiating). Built in-house, in Rust eventually for the CRDT story, but Go for now.
- *Catalog* — supporting. Product data; built in-house but not gold-plated.
- *Inventory* — supporting. Authoritative stock counts.
- *Order* — core. The orchestration of a purchase is the heart of the business.
- *Payment* — the *rails* are generic (you conform to a PSP), but the charge/refund/reversal *workflow* is supporting and built in-house (Temporal, Week 12).
- *Search* — supporting; a read model fed by CDC.

**Step 2 — Bounded contexts and the language test.** "Product" in `catalog` is a rich editorial object (descriptions, images, taxonomy). "Product" in `cart` is a thin line item (a SKU, a price snapshot, a quantity). "Product" in `inventory` is a stock-keeping unit with an on-hand count. Three meanings → three contexts. We do **not** build a `ProductService`; each context keeps its own notion of a product, linked by SKU.

**Step 3 — Context map.** `cart` is downstream of `catalog` (it needs product names and prices) and `pricing`. It puts an **ACL** over `catalog` so `catalog`'s editorial model doesn't leak in. `order` is downstream of `cart` (reads the cart at checkout) and customer–supplier with `inventory`. `payment` is a conformist over the external PSP. This is exactly the table in §3.

**Step 4 — Conway check.** For this to hold, we need a cart team and a catalog team with a documented gRPC contract between them (Week 5) and no shared database (the mini-project rule). If one team owned both, Conway predicts the ACL would rot and the two would share tables. So the design *implies* a team structure, and we'd advocate for it.

**Step 5 — Deployment decision.** One context, one service, each independently deployable, each with its own Postgres. We resist the urge to split `cart` into `cart-read` and `cart-write` services on day one — that's a performance optimization to earn later, not a starting topology. (Premature split is its own anti-pattern; YAGNI applies to services too.)

That is the whole method: domain → subdomains → contexts (via the language test) → context map (with named relationships) → Conway check → deployment. You will run this exact sequence on a 40 kLOC monolith in the challenge.

---

## 7.5 The three relationship patterns you'll reach for most, in code

Section 3 catalogued nine relationship patterns; in practice three of them carry most of your real integration work, and each shows up as a concrete code shape. Knowing the shape, not just the name, is what makes the pattern usable.

**The anti-corruption layer, concretely.** It is a translation function (or a small package) inside the *downstream* context that takes the upstream's foreign type and produces the local domain type. Nothing in the downstream's core ever sees the foreign type. In Go:

```go
// Inside cart's package. The ONLY place catalog's DTO appears.
type catalogDTO struct {            // catalog's model — ugly, not ours
	SKU         string
	Name        string
	PriceCents  int64
	Description string   // cart doesn't care
	LegacyFlags map[string]string
}

type Product struct {               // cart's OWN clean domain type
	SKU        string
	Name       string
	PriceCents int64
}

func fromCatalog(dto catalogDTO) Product {   // the ACL
	return Product{SKU: dto.SKU, Name: dto.Name, PriceCents: dto.PriceCents}
}
```

When `catalog` changes its DTO, only `fromCatalog` changes. The blast radius of an upstream change is one function. That is the entire value proposition, and it is why the ACL is the pattern seniors reach for reflexively when depending on anything they don't control.

**Customer–supplier, concretely.** The downstream (customer) depends on the upstream (supplier), and the supplier *commits to considering the customer's needs* — which in practice means a versioned, backward-compatible contract (Week 5) and a deprecation policy, not ad-hoc schema changes. The code shape is a generated client from a published `.proto`, plus an agreement (often literally a document) that the supplier won't break it. The relationship is healthy precisely because the dependency is *explicit and governed*, not implicit and surprising.

**Conformist, concretely.** The downstream simply adopts the upstream's model with no translation — usually because the upstream is a powerful external system (a payment processor) whose model you can't influence and translating isn't worth it. The code shape is: you use the vendor's SDK types directly in the adapter layer, accepting the coupling as a deliberate trade. The danger is letting conformist creep *inward* — the vendor's types leaking into your core. The discipline: conform at the edge, and put an ACL behind it if the vendor's model is ugly enough to hurt.

The choice between customer–supplier-with-ACL and conformist is one you'll make constantly: *do I control or influence the upstream?* If yes, customer–supplier with a clean contract. If no, conformist at the edge, ACL if needed. Naming this choice in your context map is the difference between a map that documents the coupling and one that merely draws arrows.

## 7.6 A note on the modular monolith — the boundary without the distribution

A recurring confusion: students hear "find the bounded contexts" and conclude "therefore deploy each as a microservice immediately." Lecture-1 §1.4 already separated the modeling decision from the deployment decision, but it deserves a concrete alternative: the **modular monolith.**

A modular monolith is a *single deployable* in which the bounded-context boundaries are enforced *in code* — separate packages/modules, no cross-module database access, communication through explicit in-process interfaces that mirror the eventual network contracts — but everything ships and runs as one process. You get the modeling discipline (clean boundaries, owned data, no entity services) *without* the operational cost of distribution (no network calls, no partial failure, a local transaction still works across contexts when you genuinely need one).

This is frequently the *correct* starting architecture, and not an embarrassing compromise. It lets a small team move fast with good boundaries, defers the operational tax until a real splitting force (Lecture 2 §Part 5) shows up, and — because the boundaries are already drawn in code — makes the eventual extraction to services mechanical rather than a rewrite. The strangler-fig migration (Lecture 2) is *easy* from a well-modularized monolith and *agony* from a big ball of mud. So: find the contexts now (always), deploy them as services later (when forced). The modular monolith is how you do the first without prematurely committing to the second.

The capstone honors this: `cart` begins as one service with clean internal boundaries, and only the *forces* of multi-region active-active and independent scaling (Phase 4) justify the splits that come later. Drawing boundaries early and distributing late is the mark of someone who has paid the distributed-monolith tax once and refuses to pay it again.

---

## 8. Recap

You should now be able to:

- Distinguish a domain, a subdomain (core/supporting/generic), and a bounded context, and explain why the bounded context — not the entity, not the table — is the unit of decomposition.
- Use the ubiquitous-language test ("does this word change meaning here?") to locate context boundaries empirically.
- Produce a context map that names each context, its owner, and the *relationship pattern* at each boundary — especially the anti-corruption layer.
- State Conway's law precisely and predict the architecture a given org will produce.
- Apply the inverse Conway maneuver: derive the team structure that would produce your desired architecture, and advocate for it as part of the design.
- Re-tell the two-pizza-team story correctly, as an org-design idea about single ownership and independent deployability, not a service-size rule.

Next: the heuristics that turn "find the boundaries" into a repeatable procedure, and the four anti-patterns that mark a decomposition gone wrong. Continue to [Lecture 2 — Decomposition Heuristics and Anti-Patterns](./02-decomposition-heuristics-and-anti-patterns.md).

---

## Appendix — Common questions and confusions

These come up every cohort. Read them; they'll save you a wrong turn.

**"Isn't a bounded context just a synonym for a microservice?"**
No, and conflating them is the most common DDD mistake. A bounded context is a *modeling* boundary — where one model and one language hold. A microservice is a *deployment* artifact — an independently deployable process. The default is one context per service, but a context can span several services (for scale or team reasons) and several contexts can share one deployable (a modular monolith). Decide the contexts first (modeling), the deployment second (operations). Reverse the order and you get entity services.

**"How big should a context be?"**
As big as one team can hold in its head and own end to end (Lecture 1 §5 cognitive load; Lecture 2 §Part 5 sizing). Too big and the team drowns; too small and you over-decompose into entity services. There is no line count. The test is ownership: can one team build, run, deploy, and reason about it alone? If yes, it's sized right.

**"What if the same data is needed by two contexts?"**
Then one context *owns* it and the other *asks* for it (Lecture 2 §Part 7) — synchronous call, snapshot, event-fed read model, or CDC, chosen by the consistency the boundary needs. The data is never *shared at the table*. "Both need product data" is not a reason to share a table; it's a reason to pick a cross-service data pattern.

**"My company has one big backend team. Does any of this apply?"**
Yes, but Conway's law warns you: with one team, the boundaries you draw will erode, because the same people maintain both sides and will reach across for convenience. Either (a) advocate for the inverse Conway maneuver — split the team to match the architecture you want — or (b) start as a *modular monolith* with the boundaries enforced in code, deferring the split until the org grows. What you must *not* do is draw microservice boundaries on a whiteboard and assign them all to one team; that's a distributed monolith waiting to happen.

**"How do I find the contexts if there are no clear teams or language differences yet?"**
Three converging signals: (1) the *language test* — where does a word change meaning? (2) the *transaction boundary* (Lecture 2 §1.2) — where does atomicity end? (3) the *change-frequency* (Lecture 2 §1.3) — what changes together? Where two or three of these agree, you have a strong boundary. Where they disagree, you have a documented decision. Start with the language test; it's the most reliable and the cheapest to run (a transcript and a highlighter).

**"Is it ever right to *not* decompose?"**
Frequently. Fowler's "MonolithFirst" is the default for a new system or a small team. Decompose when a concrete *force* appears — independent deployability, independent scaling, team ownership, or fault isolation (Lecture 2 §Part 5). No force, no split. The discipline of this week is as much about *when not to* as *where to*.

---

## Appendix — The nine context-map relationship patterns, summarized

Section 3 detailed the five you'll use most. Here is the full set for reference, so the next time a colleague names one you know it.

| Pattern | One-line meaning |
|---|---|
| Partnership | Two contexts succeed or fail together; coordinated planning. |
| Shared kernel | A small, jointly-owned shared model subset. Tight coupling by design. |
| Customer–Supplier | Downstream depends on upstream; upstream considers downstream's needs. |
| Conformist | Downstream adopts upstream's model as-is, no translation. |
| Anti-corruption layer | Downstream wraps upstream behind a translation layer. |
| Open-host service | Upstream offers a well-defined protocol for many consumers. |
| Published language | A shared, documented interchange format (a `.proto`, an OpenAPI spec). |
| Separate ways | Two contexts deliberately have no integration; cheaper to duplicate. |
| Big ball of mud | The anti-pattern: no clear boundaries at all. Name it to escape it. |

The two worth extra attention beyond §3: **Separate ways** is the underused one — sometimes the right integration is *no* integration, because the coupling cost exceeds the duplication cost. And **Big ball of mud** is the one you're escaping: naming a region of the system as a mud-ball is the first step to drawing real boundaries through it.

### How to actually draw the map

1. List the bounded contexts (from the language test).
2. For each pair that integrates, draw a directed edge upstream → downstream.
3. Label each edge with its relationship pattern *and* its mechanism (gRPC, events, ACL).
4. Mark each context's subdomain kind (core/supporting/generic) and team owner.
5. Circle any edge you can't name a pattern for — that's a boundary you don't yet understand.

A context map that survives this process is one you can defend in a review. A map with unlabeled arrows is decoration. The labels — the patterns and mechanisms — are the actual engineering content, because they're what determine the coupling, the failure modes, and the cost of change at each boundary.

### The subdomain investment matrix

One more lens that pays off in the memo: cross the subdomain kind with where to *invest*.

| Subdomain kind | Build or buy? | Who staffs it | Example |
|---|---|---|---|
| Core | Build, with your best engineers | Senior, owned long-term | the pricing/promotions engine |
| Supporting | Build, but don't gold-plate | A capable team, pragmatic | catalog, inventory |
| Generic | Buy / adopt off-the-shelf | Integrate, don't build | auth (Keycloak), payments rails (Stripe) |

The mistake that this matrix prevents is *building a generic subdomain* — writing your own auth service from scratch while a competitor adopts Keycloak and pours that energy into the core. Part of decomposition is deciding which subdomains you *own* at all. A `catalog` context you build and an `auth` context you adopt are both contexts on your map, but only one of them deserves your engineers' time. Mark the kind on every context, and let it drive the build-vs-buy conversation before you've sunk a quarter into reinventing OAuth.

This connects back to Conway's law: you should not have a *team* dedicated to a generic subdomain you ought to buy. If you find an org with a six-person "authentication platform team" maintaining a homegrown identity service, Conway predicts they'll keep building it (the team's existence justifies the work) — and the inverse maneuver is to disband that team and adopt Keycloak, redirecting the people to a core subdomain. Org design and subdomain classification are the same conversation viewed from two angles.

### The whole method, on one card

For your notes, the entire Lecture-1 procedure compressed:

```text
1. DOMAIN        — name the whole problem space (e-commerce).
2. SUBDOMAINS    — slice it; classify each core / supporting / generic.
                   (Build core, build-don't-gild supporting, BUY generic.)
3. CONTEXTS      — language test: where does a word change meaning? Cut there.
                   (No entity services. Each context owns its model.)
4. CONTEXT MAP   — name the relationship pattern + mechanism on EVERY edge.
                   (ACL where a foreign model would leak in.)
5. CONWAY CHECK  — does a team structure exist to sustain these boundaries?
                   If not, run the inverse maneuver (reshape teams).
6. DEPLOYMENT    — one context -> one service (default), OR a modular monolith
                   until a splitting force (deploy/scale/own/isolate) appears.
```

Run these six steps in order on any system and you will produce a defensible decomposition. Skip step 3's language test and you get entity services; skip step 4's labels and you get a decorative diagram; skip step 5 and your boundaries erode; skip step 6's restraint and you over-decompose. Each step guards against a specific, common failure — which is why the *order* matters as much as the steps.

## References

- *Domain-Driven Design*, Eric Evans, Part IV (Strategic Design): <https://www.domainlanguage.com/ddd/>
- *Building Microservices* (2nd ed.), Sam Newman, Chapters 1–3: <https://www.oreilly.com/library/view/building-microservices-2nd/9781492034018/>
- "How Do Committees Invent?", Melvin Conway, 1968: <https://www.melconway.com/Home/Committees_Paper.html>
- "BoundedContext", Martin Fowler: <https://martinfowler.com/bliki/BoundedContext.html>
- "Conway's Law", Martin Fowler: <https://martinfowler.com/bliki/ConwaysLaw.html>
- "A Conversation with Werner Vogels", ACM Queue, 2006: <https://queue.acm.org/detail.cfm?id=1142065>
- Team Topologies key concepts: <https://teamtopologies.com/key-concepts>
