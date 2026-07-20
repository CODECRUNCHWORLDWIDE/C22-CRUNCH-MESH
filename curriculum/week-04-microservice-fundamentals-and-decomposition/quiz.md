# Week 4 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 5. Answer key is at the bottom — don't peek.

---

**Q1.** What is a bounded context, in the precise DDD sense?

- A) A microservice.
- B) The boundary within which a single model and a single ubiquitous language are internally consistent — inside it, every term means exactly one thing.
- C) A database table and the code that wraps it.
- D) A team.

---

**Q2.** The word "Customer" means a lead in Sales, a payment instrument in Billing, and a ticket history in Support. What does DDD prescribe?

- A) Build one `CustomerService` that unifies all three models.
- B) Let each context have its own Customer model, linked by an identifier; do *not* unify them into one model.
- C) Pick the richest model (Billing) and make the others use it.
- D) Store all three in a shared `customers` table.

---

**Q3.** Which statement about the relationship between a bounded context and a microservice is correct?

- A) They are the same thing.
- B) A bounded context is a deployment concept; a microservice is a modeling concept.
- C) A bounded context is a modeling concept; a microservice is a deployment concept. The default mapping is one-to-one, but several contexts may start inside one deployable monolith.
- D) Every bounded context must be split into at least three microservices.

---

**Q4.** Conway's law states:

- A) Smaller teams write better code.
- B) An organization will produce a system whose structure mirrors the organization's communication structure.
- C) Microservices should be sized to a two-pizza team.
- D) Every system tends toward a distributed monolith over time.

---

**Q5.** What is the *inverse Conway maneuver*?

- A) Rewriting the system to ignore the org chart.
- B) Deliberately reshaping the teams to produce the architecture you want.
- C) Merging all teams into one to remove communication boundaries.
- D) Letting the architecture dictate the org chart automatically.

---

**Q6.** You must decide whether `inventory`'s "decrement stock and record the reservation" belongs in one service or two. Which heuristic decides, and what does it say?

- A) Change-frequency clustering; split them because they change at different rates.
- B) The transaction boundary; keep them together because the operation must be atomic and there are no distributed ACID transactions across services in practice.
- C) Verb-vs-noun; split them because "stock" and "reservation" are different nouns.
- D) Data cohesion; split them because they're different tables.

---

**Q7.** What is the defining property of the *distributed monolith* anti-pattern?

- A) It uses too many databases.
- B) Services that must be deployed together in lockstep and call each other synchronously — all the cost of distribution, none of the independent deployability.
- C) A single service that is too large.
- D) Services written in different languages.

---

**Q8.** Why is the *shared database* anti-pattern called insidious?

- A) Databases are slow.
- B) The coupling is invisible in the service code — nothing in service A's source says it depends on service B; the dependency lives in the schema, where no code review catches it.
- C) It requires too much disk.
- D) It only affects NoSQL databases.

---

**Q9.** A single "load order page" request makes `order` call `catalog` once per line item, then `pricing` once per line item, then `inventory`. This is which anti-pattern, and what's the structural fix?

- A) Shared database; fix by merging the databases.
- B) The chatty mesh (an across-the-network N+1); fix with bulk endpoints (`GetProducts([]sku)`), async read models, or coarser boundaries.
- C) Entity service; fix by adding a cache.
- D) Distributed monolith; fix by deploying together.

---

**Q10.** What makes a service an *entity service*, and why is it patient zero for the other anti-patterns?

- A) It's written in Java; it causes nothing.
- B) It's an anemic CRUD wrapper over one table with no business behavior; because it has no logic, the logic ends up in orchestrators that must make many fine-grained calls (chatty mesh) and reach into multiple services' data (shared database).
- C) It has too many endpoints; it causes scaling problems only.
- D) It owns multiple tables; it causes deployment problems only.

---

**Q11.** The two-pizza team is best understood as:

- A) A rule that every service must have at most eight developers.
- B) An org-design idea about single ownership and independent deployability — the team is two-pizza-*sized* and owns a service it can build, run, and deploy alone; it is not "a service per developer."
- C) A literal statement about catering budgets.
- D) A mandate to split every service when it exceeds a line count.

---

**Q12.** In the decomposition memo, why are *three rejected alternatives* required?

- A) To make the memo longer.
- B) Because the quality of a decision is visible only in the alternatives considered and rejected; rejected alternatives are the evidence that the chosen design resulted from analysis, and they pre-empt the reviewer's "did you consider X?"

- C) Because three is a lucky number.
- D) They aren't required; one proposal is enough.

---

**Q13.** `cart` needs product data from a messy legacy `catalog` whose DTO has forty fields and inconsistent types. What pattern keeps `catalog`'s model from leaking into `cart`, and where does it live?

- A) Shared kernel; it lives in a jointly-owned package.
- B) Conformist; `cart` adopts catalog's model as-is.
- C) Anti-corruption layer; a thin translation inside `cart` that converts the foreign DTO into `cart`'s clean domain type at the boundary — so when catalog changes its DTO, only the ACL changes.
- D) Open-host service; catalog publishes a language `cart` must adopt wholesale.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — A bounded context is the boundary of model and language consistency. Not a service, not a table, not a team (though it often aligns with a team). (Lecture 1 §1.3.)
2. **B** — Each context keeps its own Customer, linked by identity. Unifying produces the entity-service god object. (Lecture 1 §1.3.)
3. **C** — Modeling concept vs deployment concept; default one-to-one but contexts may share a monolith early. The reverse mapping in B is the trap. (Lecture 1 §1.4.)
4. **B** — The structure mirrors the communication structure. The others are true-ish statements about *other* ideas, but not Conway's law. (Lecture 1 §4.)
5. **B** — Reshape teams to get the architecture. It's the only reliable lever because the org chart wins over the whiteboard. (Lecture 1 §5.)
6. **B** — Transaction boundary; atomic operations stay together because distributed ACID isn't practical. This heuristic wins on atomicity conflicts. (Lecture 2 §1.2, §1.5.)
7. **B** — Lockstep deploy + synchronous coupling = all cost, no independence; strictly worse than the monolith it replaced. (Lecture 2 §2.1.)
8. **B** — Invisible-in-code coupling via the schema; the cardinal sin because no review catches it. (Lecture 2 §2.2.)
9. **B** — Chatty mesh / across-the-network N+1; fixed by bulk endpoints, read models, or coarser boundaries. (Lecture 2 §2.3.)
10. **B** — Anemic CRUD-over-one-table; it strands logic in orchestrators, which causes the chatty mesh and tempts the shared database. It's the root cause. (Lecture 2 §2.4.)
11. **B** — Org-design idea about ownership and independent deploy; two-pizza-*sized* team, not a service-per-dev rule. (Lecture 1 §6.)
12. **B** — Rejected alternatives are the evidence of analysis and pre-empt the reviewer. The part that makes it a senior artifact. (Lecture 2 §3.2.)
13. **C** — Anti-corruption layer, inside the downstream (`cart`), translating the foreign DTO to the local domain type at the boundary. (Lecture 1 §3.)

</details>

---

If you scored under 9, re-read the lecture sections cited in the answers you missed. If you scored 11 or higher, you're ready for the [homework](./homework.md).
