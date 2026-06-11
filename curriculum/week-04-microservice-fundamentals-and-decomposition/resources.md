# Week 4 — Resources

Every resource here is either **free** or a **canonical book** you should own if you intend to do this work professionally. The two books — Evans and Newman — are the load-bearing references for the entire phase; everything else is supplementary and free. Where a paper or talk is the original source of an idea (Conway's law, the two-pizza team), the primary source is linked, not a blog summary of it.

The bias of this reading list matches the course: open, primary-source, and skeptical of vendor marketing. You read Evans on bounded contexts, not a conference slide that reduced him to a bullet point.

## The two books (own these)

- **Eric Evans — *Domain-Driven Design: Tackling Complexity in the Heart of Software* (2003).** The source. For this week, Part IV (Strategic Design): Chapters 14 (Maintaining Model Integrity — the context-map patterns), 15 (Distillation — core vs supporting vs generic subdomains), and 16 (Large-Scale Structure). Dense. Read Chapter 14 twice.
  Publisher page: <https://www.domainlanguage.com/ddd/>
- **Sam Newman — *Building Microservices*, 2nd edition (2021).** The practitioner's complement to Evans. Chapters 1–3 (what a microservice is, how to model boundaries, splitting the monolith) are this week. Newman is the one who says, more clearly than anyone, "don't start with microservices."
  Publisher page: <https://www.oreilly.com/library/view/building-microservices-2nd/9781492034018/>

If you can only buy one this month, buy Newman; it is the more directly applicable to the labs. But Evans is the one you'll re-read for a decade.

## Free primary sources (read these this week)

- **Melvin Conway — "How Do Committees Invent?" (1968).** The original Conway's-law paper. Short, readable, and far sharper than the one-liner it's been reduced to.
  <https://www.melconway.com/Home/Committees_Paper.html>
- **Martin Fowler — "BoundedContext".** The clearest free explanation of the bounded context, by the person who did the most to popularize Evans.
  <https://martinfowler.com/bliki/BoundedContext.html>
- **Martin Fowler — "MicroservicePremium" and "MonolithFirst".** Why microservices have a complexity cost you must earn the right to pay, and why most systems should start as a monolith.
  <https://martinfowler.com/bliki/MicroservicePremium.html>
  <https://martinfowler.com/bliki/MonolithFirst.html>
- **Martin Fowler — "Conway's Law".** Fowler's write-up of the inverse Conway maneuver and the team-architecture relationship.
  <https://martinfowler.com/bliki/ConwaysLaw.html>
- **Chris Richardson — microservices.io pattern catalog.** The decomposition patterns (by business capability, by subdomain), the database-per-service pattern, and the anti-patterns, each with a crisp problem/solution statement.
  <https://microservices.io/patterns/index.html>

## The two-pizza team, from sources (not folklore)

- **Werner Vogels — "A Conversation with Werner Vogels" (ACM Queue, 2006).** The interview where the Amazon "you build it, you run it" and small-team service-ownership model is described by the CTO, first-hand. This is the primary source the two-pizza story is usually mis-cited from.
  <https://queue.acm.org/detail.cfm?id=1142065>
- **Team Topologies (Skelton & Pais) — the four team types and three interaction modes.** The modern, rigorous treatment of "shape the teams to get the architecture." The website summarizes the model for free.
  <https://teamtopologies.com/key-concepts>

## Deeper DDD (for the mini-project and the memo)

- **Vaughn Vernon — *Implementing Domain-Driven Design* (2013).** The "red book." More tactical than Evans. Chapter 2 (Domains, Subdomains, Bounded Contexts) and Chapter 3 (Context Maps) are exactly this week's material with worked examples.
  <https://www.informit.com/store/implementing-domain-driven-design-9780321834577>
- **DDD Reference (Eric Evans, 2015) — the free condensed glossary.** Every DDD term in two pages each. Keep it open while you write your context map.
  <https://www.domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf>
- **Context Mapping (Nick Tune et al.) — the visual notation.** How to actually *draw* a context map, with the relationship-pattern arrows.
  <https://github.com/ddd-crew/context-mapping>

## Splitting the monolith (the lab skill)

- **Sam Newman — *Monolith to Microservices* (2019).** The decomposition-specific book. The strangler-fig pattern, the branch-by-abstraction, and how to split a database without downtime. Chapters 3 and 4 underpin the mini-project.
  <https://www.oreilly.com/library/view/monolith-to-microservices/9781492047834/>
- **Martin Fowler — "StranglerFigApplication".** The canonical pattern for incrementally replacing a monolith.
  <https://martinfowler.com/bliki/StranglerFigApplication.html>
- **The "Database per service" pattern and the dual-write problem** (microservices.io). Why two services must not share tables, and what to do instead (you will meet the outbox pattern properly in Week 11).
  <https://microservices.io/patterns/data/database-per-service.html>

## Talks worth your time (free, no signup)

- **Sam Newman — "Don't Start With Microservices."** The single most useful talk for a team about to over-decompose. Search the GOTO Conferences channel.
  <https://www.youtube.com/@GOTO-> (GOTO Conferences)
- **Mary Poppendieck / various — Conway's-law and team-topology talks.** The DDD Europe and Team Topologies conference channels post their sessions free.
  <https://www.youtube.com/@dddeurope>
- **Eric Evans — "DDD and Microservices: At Last, Some Boundaries."** Evans himself on why microservices and bounded contexts are the same conversation. (DDD Europe archive.)
  <https://www.youtube.com/@dddeurope>

## Tools you'll use this week

- **`go`** (1.23+) — for the `cart` service scaffold and the smell-detector exercise. `go version` should report 1.23 or newer.
- **`python3`** (3.12+) with a `venv` — for the `catalog` read service and the topology-scoring exercise.
- **Docker + Kind** — `kind create cluster` for the mini-project deploy. Both services run as separate Deployments with separate Postgres instances.
- **A diagramming tool** — anything that produces a context map: Excalidraw, Mermaid (in your markdown), draw.io, or pen and paper photographed. The diagram is a deliverable; the tool is not.
- **`grep` / `ripgrep`** — your shared-database detector. `rg DATABASE_URL services/` is, embarrassingly often, the fastest architecture audit in your toolbox.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Domain** | The whole problem space your business is in (e-commerce, say). |
| **Subdomain** | A slice of the domain: *core* (your competitive edge), *supporting* (needed but not differentiating), *generic* (buy/use off the shelf, like auth). |
| **Bounded context** | The boundary within which a single model and a single ubiquitous language are consistent. "Order" means one thing inside it. |
| **Ubiquitous language** | The shared vocabulary of a bounded context, used identically in conversation, code, and the schema. |
| **Context map** | The artifact showing every bounded context and the relationships between them. |
| **Anti-corruption layer (ACL)** | A translation boundary that keeps another context's model from leaking into yours. |
| **Conway's law** | A system's structure mirrors the communication structure of the org that built it. |
| **Inverse Conway maneuver** | Deliberately reshaping teams to produce the architecture you want. |
| **Distributed monolith** | Services that must deploy together and call each other in lockstep — all cost of distribution, none of the independence. |
| **Shared database** | Two+ services reading/writing the same tables — invisible coupling. The cardinal sin. |
| **Chatty mesh** | One user action causing many synchronous service hops; latency and failure compound. |
| **Entity service** | A noun-shaped CRUD wrapper over a table (`CustomerService`), anemic and over-decomposed. |
| **Two-pizza team** | A team small enough to feed with two pizzas; the unit of single-owner service responsibility. |
| **Database per service** | Each service owns its data store; no other service touches it directly. |

---

*If a link 404s, please open an issue so we can replace it.*
