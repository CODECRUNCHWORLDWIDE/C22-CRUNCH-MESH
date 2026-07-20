# Week 4 — Microservice Fundamentals and Decomposition

Welcome to the week where you stop drawing boxes by gut feel and start drawing them with a method. By Friday you will be able to look at a monolith and a proposed service topology and say, with evidence, where the seams *should* be — and, more importantly, where someone has proposed a seam that will produce a distributed monolith: the worst of both worlds, a system that is hard to deploy *and* tightly coupled.

The first three weeks of Crunch Mesh were deliberately code-light. You read CAP, PACELC, FLP, the consensus literature, vector clocks, and CRDTs. That was not throat-clearing. The single most expensive mistake in distributed systems is not a bug — it is a boundary drawn in the wrong place, because a wrong boundary is paid for on every change, every deploy, and every incident for years. This week is the bridge from theory to the first line you'll draw on the actual `cart` system you carry to the capstone.

The one thing to internalize before you read another line: **a microservice boundary is a boundary of *change* and *ownership*, not a boundary of *nouns*.** The instinct of every engineer coming from a relational-database background is to make a service per entity: a `CustomerService`, an `OrderService`, a `ProductService`, a `AddressService`. That instinct produces the **entity-service anti-pattern** — anemic CRUD wrappers over tables, chatty as hell, where a single user action fans out into eight synchronous calls and one slow dependency takes the whole flow down. The corrective is **bounded contexts**: you find the boundaries where the *language* changes, where "order" means something different to the fulfillment team than it does to the billing team, and you cut there. That cut survives because it follows the org and the domain, not the schema.

This week is where you learn to find that cut, defend it in writing, and recognize in code review when someone has missed it.

## Learning objectives

By the end of this week, you will be able to:

- **Define** a bounded context in the precise Domain-Driven Design sense, distinguish it from a subdomain and from a microservice, and explain why a bounded context is the *unit of decomposition* while a service is merely a deployment artifact.
- **Apply** Conway's law and the inverse Conway maneuver: predict the architecture a given org chart will produce, and reshape teams to produce the architecture you want.
- **Use** at least four decomposition heuristics — verb-vs-noun, transaction boundary, change-frequency clustering, and data-cohesion — and state when each one disagrees with the others and which wins.
- **Name and recognize** the four canonical decomposition anti-patterns — the distributed monolith, the shared database, the chatty mesh, and the entity service — from a description, a diagram, or a code-review diff.
- **Decompose** a monolithic codebase into a candidate service topology, producing a context map (the DDD artifact) that names every context, its relationships, and its team owner.
- **Write** an architecture decision memo that proposes a topology, names the heuristics it followed, and *explicitly records three rejected alternatives* with the reason each was rejected — the artifact a staff engineer actually produces.
- **Identify** the synchronous-call chains and shared-state couplings in a proposed topology that mark it as a distributed monolith, and prescribe the asynchronous or boundary-moving fix.
- **Scaffold** the first two services of the capstone `cart` system as independently deployable Go and Python processes that do *not* share a database, communicating over an explicit contract — the seam you will harden in Weeks 5 and 6.

## Prerequisites

This week assumes you have completed **C22 weeks 1–3**, or have equivalent distributed-systems fluency. Specifically:

- You have read the CAP / PACELC / FLP material from Week 1 and can state why a network partition forces a choice between consistency and availability. Decomposition decisions are partition decisions in disguise — every boundary you draw is a place the network can fail.
- You understand from Week 2 that there is no global clock and no free distributed transaction; "just use a transaction across the two services" is not on the menu, and this week is partly about designing boundaries so you rarely need one.
- You finished the Week 3 CRDT material and understand eventual consistency as a *deliberate* choice for some state and a *footgun* for other state. Boundary-drawing decides which state gets which treatment.
- You can write and run a basic Go program (`go run`, modules, structs, goroutines) and a basic Python service (a `venv`, `pip`, an HTTP handler). We are not teaching the languages; we are using them.
- You have Docker and a local Kubernetes (Kind is assumed; k3d or minikube are fine) installed and working: `docker ps` and `kubectl get nodes` both succeed.

You do **not** need prior microservices experience. We start at the definition of a bounded context and build to a defended topology. If you have built microservices but never been able to say *why* a particular boundary was right, this is the week that knowledge becomes load-bearing.

## Topics covered

- **Bounded contexts and the ubiquitous language.** The DDD definitions: domain, subdomain (core / supporting / generic), bounded context, context map, and the relationship patterns (shared kernel, customer–supplier, conformist, anti-corruption layer, open-host service, published language). Why the context boundary is where the *language* changes.
- **Conway's law and the inverse Conway maneuver.** "Organizations design systems that mirror their communication structure." Why your architecture will converge on your org chart whether you like it or not, and how the inverse maneuver — reshape the teams to get the architecture — is the only reliable lever.
- **The Amazon two-pizza-team origin story, re-examined.** What the two-pizza team actually optimized for (independent deployability and a single owner per service), what it did *not* mean (a service per developer), and why the story is more about org design than service size.
- **Decomposition heuristics.** Verb-vs-noun (capabilities over entities); the transaction boundary (cut where a single atomic transaction is *not* required, never through the middle of one); change-frequency clustering (things that change together belong together); data cohesion (a service owns its data and no one else reads its tables). What to do when two heuristics disagree.
- **The four anti-patterns in depth.** The **distributed monolith** (services that must be deployed together and call each other synchronously in lockstep — all the cost of distribution, none of the independence). The **shared database** (two services writing the same tables — the coupling you cannot see in the service code). The **chatty mesh** (one user action, N synchronous hops, latency and failure multiplied). The **entity service** (CRUD wrappers over tables, anemic and noun-shaped).
- **The context map as a deliverable.** Producing the artifact: a diagram and a table naming each context, its team owner, its upstream/downstream relationships, and the integration pattern at each boundary (especially the anti-corruption layer).
- **The decomposition memo.** The written architecture artifact: the proposed topology, the heuristics applied, the data ownership, and — the part juniors skip — three rejected alternatives with the reason each lost. This is the artifact graded at the Phase 1 architecture review in Week 12.
- **Scaffolding the seam.** Standing up the capstone's first two services (`cart` in Go, a thin `catalog` read in Python) as independently deployable processes with no shared database, communicating over an explicit boundary you will turn into a typed gRPC contract next week.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Bounded contexts; ubiquitous language; context maps    |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Conway's law; heuristics; the decomposition exercise   |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | The four anti-patterns; the distributed-monolith smell |    2h    |    1.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Data ownership; the decomposition memo                 |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | Scaffolding the seam; the topology critique            |    0h    |    0h     |     1h     |    0.5h   |   1h     |     3h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                 |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, review, memo polish                              |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                        | **6h**   | **7h**    | **4h**     | **3.5h**  | **5h**   | **12h**      | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Evans, Newman, Vernon, the Conway's-law sources, and the talks worth your time |
| [lecture-notes/01-bounded-contexts-and-conways-law.md](./lecture-notes/01-bounded-contexts-and-conways-law.md) | Bounded contexts, the ubiquitous language, context maps, Conway's law, and the inverse maneuver |
| [lecture-notes/02-decomposition-heuristics-and-anti-patterns.md](./lecture-notes/02-decomposition-heuristics-and-anti-patterns.md) | The decomposition heuristics, the four anti-patterns, and the decomposition memo |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-draw-the-context-map.md](./exercises/exercise-01-draw-the-context-map.md) | Read a monolith description and produce a context map with named contexts, owners, and relationships |
| [exercises/exercise-02-decompose-the-monolith.py](./exercises/exercise-02-decompose-the-monolith.py) | A runnable analyzer that scores a proposed topology against the decomposition heuristics |
| [exercises/exercise-03-distributed-monolith-smell.go](./exercises/exercise-03-distributed-monolith-smell.go) | A Go tool that detects synchronous-call-chain and shared-database smells in a topology spec |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-decompose-and-defend.md](./challenges/challenge-01-decompose-and-defend.md) | Decompose a 40 kLOC monolith and defend the topology with three rejected alternatives |
| [quiz.md](./quiz.md) | 13 questions with a hidden answer key |
| [homework.md](./homework.md) | Six problems including the headline decomposition memo |
| [mini-project/README.md](./mini-project/README.md) | Scaffold the capstone `cart` + `catalog` seam as two independently deployable services |

## The "no shared database" promise

C22 uses a recurring marker for every decomposition that holds up: **two services, two databases, one explicit contract.** When you finish the mini-project, this command should return *nothing*:

```bash
# Find any service that connects to a database it does not own.
$ grep -rn "DATABASE_URL" services/ | grep -v "$(basename $(pwd))"
```

If `cart` can open a connection to `catalog`'s Postgres, you have built a shared database with extra steps, and the boundary is a lie. The point of Week 4 is to make "the only way `cart` learns about a product is by *asking* `catalog`" the ordinary case — and to make a direct table read *loud* instead of silent.

## Stretch goals

If you finish the regular work early and want to push further:

- Read **Eric Evans, *Domain-Driven Design*, Chapter 14** (Maintaining Model Integrity) until you can draw all nine context-map relationship patterns from memory and give a real example of each.
- Take an open-source monolith you know — Mastodon, Discourse, or the Sentry self-hosted backend — and write a one-page context map for it. You will reuse exactly this skill for the Week 12 midterm architecture-review essay.
- Implement a tiny **anti-corruption layer** in Go: a `cart` package that talks to a legacy `catalog` whose model you do not control, translating its ugly DTO into `cart`'s clean domain type at the boundary. This is the single most valuable integration pattern in the DDD toolkit.
- Run the team-topology thought experiment from Lecture 1 §6 on your *actual* employer's org chart. Predict the architecture it produces. Then check whether you were right. The accuracy will disturb you.

## Up next

Week 5 takes the seam you scaffold here and makes it a **typed contract**: gRPC and Protobuf, the request–offered compatibility of schema evolution, and why a typed surface between two services is a moral position and not just an engineering convenience. The `cart` and `catalog` services you stand up this week become the polyglot client/server pair you wire together next week. Push your mini-project before you start it.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
