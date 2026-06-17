# Lecture 2 — The Gameday and the Blameless Postmortem

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can run a 90-minute gameday with a runbook and named roles; execute the broker-loss/exactly-once drill and verify the invariant with offsets and an idempotency audit; write a blameless postmortem good enough to publish; and articulate the "five whys" critique and why contributing-factors analysis is more honest.

If you remember one sentence from this lecture, remember this one:

> **A gameday is a rehearsed incident with the safety on: the same roles, runbook, and dashboards you'd use in a real outage, run against a fault you chose, so that when the real one comes you've already practiced — and the postmortem is where the practice turns into a permanent change to the system.**

Lecture 1 gave you the experiment: one hypothesis, one fault, one metric. The gameday is the experiment scaled up into a *drill* — multiple experiments, a clock, named roles, and the explicit goal of finding something worth a postmortem. This is the dress rehearsal for the capstone's two mandatory drills, and it's the closest the course gets to the thing you'll actually do on a real on-call rotation.

---

## 1. The gameday: structure, roles, and the runbook

### 1.1 What a gameday is (and is not)

A gameday is a **scheduled, time-boxed exercise where a team injects failures against hypotheses, observes the response, and writes up what they learned.** It is a drill, not a stunt. The difference from ad-hoc chaos:

- It's **scheduled**, so the right people are present and watching, and nobody's surprised.
- It has **roles**: someone runs the experiment (the game master / commander), someone records the timeline (the scribe), someone watches the dashboards (the observer). In a richer gameday, *responders* who don't know the injected fault diagnose it blind — which is the most realistic on-call practice there is.
- It has a **runbook**: the ordered list of experiments, each with its hypothesis, steady-state metric, abort condition, and rollback. You wrote those in Lecture 1's template; the runbook is them, sequenced.
- It produces **postmortems** for the non-trivial findings — the deliverable that makes the 90 minutes pay off.

It is **not**: a demo (a demo shows things working; a gameday tries to make them fail), a load test (that's steady-state; the gameday is the fault on *top* of steady state), or a free-for-all (no hypothesis, no metric, no abort = not a gameday).

### 1.2 The roles

Even a two-person gameday benefits from explicit roles; borrow them from the SRE incident-response model (Week 18 touched these):

- **Commander / game master.** Runs the runbook: announces each experiment, injects the fault (applies the chaos CRD), calls the abort if the condition triggers, and keeps time. In a blind gameday, the game master is the *only* person who knows what fault is active.
- **Scribe.** Maintains the timeline in real time: "14:03:10 injected `kafka-broker-loss`; 14:03:14 consumer lag began climbing; 14:03:31 lag peaked at 28 s; 14:03:55 broker rescheduled; 14:04:40 lag back to baseline." This timeline *is* the spine of every postmortem. Writing it after the fact from memory is how postmortems become fiction; the scribe writes it live.
- **Observer(s).** Watch the steady-state dashboards and call out what the metrics do. They own the verdict: "the error-rate SLI held" or "we breached the SLO at 14:03:40 — that's the abort trigger."

For your two-person (or solo) capstone rehearsal, you'll wear multiple hats — but *name the hat you're wearing at each moment*, because the discipline of "right now I'm the scribe, I'm writing the timeline" is what keeps the gameday from collapsing into staring at a terminal.

### 1.3 The 90-minute structure

The syllabus calls for a 90-minute gameday. Here's the shape:

- **Minutes 0–10 — Pre-flight.** Confirm steady state: the system is healthy, the load generator is holding the agreed RPS, every dashboard is green and live. Read out the runbook: the experiments in order, each hypothesis, each abort condition. **Confirm the abort conditions before anyone injects anything** — they're not negotiable mid-fault.
- **Minutes 10–75 — The experiments.** Run them one at a time. For each: announce → measure baseline → inject → observe the steady-state metric → record the verdict → roll back → confirm recovery to baseline *before the next one*. Never stack faults unless that's a deliberate, planned experiment; overlapping uncontrolled faults make the verdict unreadable. Budget ~10 minutes per experiment for six experiments; the broker-loss drill (§2) gets more.
- **Minutes 75–85 — Debrief.** Walk the findings. Which hypotheses held? Which were refuted? Which refutations are real bugs (a finding) versus tuning (an action item)? Rank them.
- **Minutes 85–90 — Assign postmortems.** Every non-trivial finding gets a postmortem with an owner. "We'll write it later" without an owner means it's never written.

### 1.4 The runbook, written out

A gameday runbook is a table — here's the one for your capstone's six experiments:

| # | Experiment | Hypothesis | Steady-state SLI | Abort if | Rollback |
|---|---|---|---|---|---|
| 1 | `cart` pod-kill (one of 3) | error < 1%, p99 < 200 ms | cart RED error ratio | error > 5% for 60 s | `kubectl delete podchaos` |
| 2 | west↔east partition (5 m) | both regions serve locally; CRDT converges on heal | per-region cart availability | either region < 95% avail for 60 s | `kubectl delete networkchaos`; verify convergence |
| 3 | cart→inventory 200 ms delay | user p99 absorbs it via retries/timeout budget | order-path p99 | p99 > 1 s for 60 s | `kubectl delete networkchaos` |
| 4 | `order` CPU stress | HPA scales out; p99 recovers or load-sheds | order RED + replica count | error > 5% for 90 s | `kubectl delete stresschaos` |
| 5 | Kafka I/O latency 100 ms | bounded consumer lag; no loss | consumer-group lag | lag > 60 s | `kubectl delete iochaos` |
| 6 | Kafka broker-loss (one of 3) | no loss; **no double-process** | lag + idempotency-key audit | data loss detected | `kubectl delete podchaos`; run EOS audit |

Notice the abort conditions are concrete numbers, decided in advance. That's the safety property. "Abort if it looks bad" is not an abort condition; "abort if the error SLI exceeds 5% for 60 seconds" is.

### 1.5 The pre-flight checklist

Before minute 0, run a checklist — the gameday equivalent of a pilot's pre-flight, because the failures you cause are real and the cost of an unprepared start is a real outage:

- **The system is healthy.** Every dashboard green, no pre-existing incident. Injecting into a degraded system gives uninterpretable results (you can't attribute the breach to your fault).
- **Steady load is flowing.** The load generator is holding the agreed RPS. A fault on an idle system is unfelt.
- **Every steady-state metric is live and visible.** Confirm each experiment's SLI renders in real time. The one you can't see is the one you can't judge.
- **The abort conditions are agreed and on screen.** Read them out. Nobody renegotiates an abort condition mid-fault.
- **Rollback is rehearsed.** For each experiment, the exact `kubectl delete` is in the runbook. You do not improvise the rollback while the system is on fire.
- **Roles are assigned.** Who's the commander, who's the scribe, who watches which dashboard. Even solo, name the hats.
- **A communication channel is open** (even just a shared doc) where the scribe writes the timeline live and everyone can see it.

Skipping the pre-flight is how a gameday becomes a real incident. The whole point is *controlled* failure; control starts before injection.

### 1.6 Why one experiment at a time

The runbook runs experiments serially, with recovery confirmed between them, and this is not fussiness — it's interpretability. If you inject a partition *and* a broker loss simultaneously and the order error rate spikes, **you cannot attribute the spike**: was it the partition, the broker, or their interaction? You've spent your blast radius and learned nothing actionable. One fault at a time means every verdict is attributable to exactly one cause.

The exception — and it's a deliberate, planned one — is a *compound experiment* where the interaction *is* the hypothesis: "the system survives a broker loss *during* a region partition" is a legitimate experiment if that combination is a real-world scenario you want to test. But you write it as one experiment with one hypothesis about the combination, run after the individual faults have been tested in isolation, not as two faults you happened to overlap. Deliberate compound: fine. Accidental overlap: an unreadable mess.

---

## 2. The broker-loss / exactly-once drill in full

This is the most important drill of the week, because it tests your system's most important invariant. It's the rehearsal for **capstone Drill B**, and it's worth doing slowly and exactly.

### 2.1 The setup and the invariant

You have, from Weeks 10–11: a 3-broker Kafka cluster (`acks=all`, `min.insync.replicas=2`), an outbox table in Postgres that writes events transactionally with the business change, Debezium streaming the outbox to Kafka, and an **idempotent consumer** that processes each event using an idempotency key so that re-delivering the same event is a no-op. The invariant is: **each business event is processed exactly once, despite broker failure and the at-least-once redelivery it causes.**

The threat the drill tests: when a broker dies, Kafka re-elects partition leaders, in-flight produces may be retried, and the consumer may be rebalanced and *re-delivered messages it already processed* (offsets aren't committed atomically with the side effect — that's why you have idempotency keys, not just offset commits). A naive consumer double-processes: charges the card twice, decrements inventory twice. Your design says it won't. The drill proves it.

### 2.2 Running the drill

```bash
# 0. Pre-flight: hold steady load (e.g. 1k orders over the drill), record the baseline.
#    Capture the consumer group's committed offsets and the processed-key count BEFORE.
kafka-consumer-groups.sh --bootstrap-server $BROKER --describe --group order-consumer
#   TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
#   order.placed.v1  0          10421           10421          0

# 1. Inject: kill one broker (the PodChaos from Lecture 1 §4.5).
kubectl apply -f kafka-broker-loss.yaml

# 2. Observe: ISR shrinks, a leader re-elects, produce/consume stalls briefly,
#    then resumes. Lag spikes and recovers. Watch:
kafka-topics.sh --bootstrap-server $BROKER --describe --topic order.placed.v1
#   ... Isr: 1,2   (was 0,1,2 — broker 0 dropped out)  Leader moved 0 -> 1
watch -n2 "kafka-consumer-groups.sh --bootstrap-server $BROKER --describe --group order-consumer"
#   LAG climbs to ~28, then drains back to 0 as the consumer catches up.

# 3. Roll back: let the broker reschedule (Strimzi/StatefulSet brings it back),
#    ISR returns to 0,1,2.
kubectl delete -f kafka-broker-loss.yaml

# 4. THE VERDICT — the idempotency audit (this is the point):
#    For every business event in the test window, assert it was applied exactly once.
```

### 2.3 The verdict is an audit, not "it recovered"

"It recovered" is necessary but nowhere near sufficient. The hypothesis is about *correctness under redelivery*, and correctness is proven by an audit of side effects:

- **Payment:** for each `order_id`, the `payments` table (or Temporal workflow history) shows exactly one successful charge. Zero `order_id`s with two charges. The idempotency key on the charge is what made the redelivered "charge this order" a no-op.
- **Inventory:** for each SKU, the decrement count equals the order count. No SKU decremented twice for one order.
- **The processed-keys table:** the consumer's idempotency-key store has one row per event id; the count equals the distinct event count, not the *delivered* count (which is higher, because redelivery happened — that's the at-least-once you survived).

The strongest single piece of evidence: **delivered count > processed count, and side-effect count == business-event count.** That gap — more deliveries than processings — is the proof redelivery *happened* and your idempotency *absorbed it*. If delivered == processed, you got lucky and the broker loss didn't actually cause a redelivery, so the drill didn't test the invariant; rerun with a harder fault (kill the broker mid-batch, or kill the consumer too) until you observe a redelivery and then prove it was absorbed.

> **The "it recovered" vs "it recovered correctly" distinction is the whole lesson.** A system can come back up, drain its lag, and look perfectly healthy on the dashboard while having silently double-charged 40 customers. The dashboard shows availability; only the audit shows correctness. The mark of an engineer who has operated an exactly-once system is that they don't trust the green dashboard — they run the audit.

---

## 3. The blameless postmortem

A finding without a postmortem is a finding you'll re-discover the hard way. The postmortem is where a refuted hypothesis becomes a permanent change to the system.

### 3.1 The structure

Copy the Google SRE postmortem skeleton; it's the industry standard for a reason:

1. **Title + date + authors + status.** ("Cart partition convergence loss — 2026-06-12 — draft.")
2. **Summary.** Two or three sentences: what happened, the impact, the resolution. The thing someone reads if they read nothing else.
3. **Impact.** Quantified: how many requests/users/dollars, for how long, against which SLO. "During the 5-minute partition, the east region lost 312 cart-add operations that did not converge on heal — a 0.8% data-loss event for the affected carts." Numbers, not "some."
4. **Timeline.** The scribe's live record, cleaned up. Timestamps, what was observed, what was done. This is the factual spine; everything else is analysis of it.
5. **Detection.** How did you find out? (In a gameday: "the convergence-audit step found 312 missing operations." In real life: "a customer complained" is a *worse* detection story than "the alert fired," and the postmortem should say so.)
6. **Root cause(s) / contributing factors.** Plural (see §4). The honest analysis of *why* — the conditions, decisions, and gaps that, together, produced the outcome.
7. **What went well / what went poorly / where we got lucky.** The "got lucky" section is the most valuable and most-skipped: the things that *didn't* go wrong this time but easily could have.
8. **Action items.** Each with an **owner** and a **due date** and a **type** (prevent / detect / mitigate). "Add a convergence-audit alert (detect) — owner: X — by next sprint." An action item without an owner is a wish.

### 3.2 What "blameless" actually means

Blameless does **not** mean "no cause" or "nobody's responsible." It means: **you analyze the system and the decisions people made *with the information they had at the time*, never the people themselves.** The premise is that engineers act reasonably given what they knew; if the outcome was bad, the system made the wrong action easy or the right action hard, or the information was missing. So instead of "Alice deployed the bad config," you write "the deploy pipeline had no staging gate that would have caught the bad config, and the config's effect wasn't observable until it hit production — so a reasonable engineer following the normal process shipped it."

Why it matters operationally, not just morally: **blame destroys the information you need.** If people are punished for incidents, they hide the near-misses, soften the timeline, and stop volunteering "actually, I wasn't sure about that change." A blameless culture gets you the *true* timeline and the honest "where we got lucky," which is the raw material for fixing the system. The org that blames learns nothing twice; the org that's blameless learns once. This is the single most important cultural property of a team that runs gamedays — and it's why the syllabus grades the *writeup*, not the heroics.

### 3.3 The postmortem template, applied to a gameday finding

Here's a finding from a real-shaped gameday, written up:

> **Title:** Order-path p99 breach under cart→inventory latency — 2026-06-12 — draft
> **Summary:** During gameday experiment #3 (200 ms injected delay on cart→inventory), order-path p99 rose to 1.4 s, breaching the 1 s SLO, because cart's retry budget retried the slow call instead of failing fast. No data was lost; the issue is latency amplification under a slow dependency.
> **Impact:** For the 3-minute experiment, ~6% of order requests exceeded the 1 s SLO. In production at 1k RPS that is ~3,600 slow requests; sustained, it would exhaust the order SLO's error budget in under an hour.
> **Timeline:** 14:22:00 injected 200 ms delay; 14:22:08 order p99 crossed 1 s; 14:22:40 p99 plateaued at 1.4 s; 14:25:00 removed fault; 14:25:20 p99 back to 180 ms.
> **Contributing factors:** (1) cart's retry policy retries `unavailable` *and* slow responses, so a uniformly-slow dependency gets retried, doubling its latency contribution rather than shedding. (2) The per-try timeout (800 ms) is longer than half the SLO budget, so even one retry blows the budget. (3) No circuit breaker opened because the dependency was *slow*, not *erroring*.
> **Where we got lucky:** the delay was uniform; a *bimodal* delay (most fast, some very slow) would have been harder to detect and would have breached the SLO at a lower injected latency.
> **Action items:** (1) Lower per-try timeout to 300 ms and cap retries at 1 on the order path (mitigate, owner: A, this sprint). (2) Add a slow-call circuit breaker (resilience4j-style) that opens on p99, not just error rate (prevent, owner: B, next sprint). (3) Add a gameday experiment to the recurring suite for bimodal latency (detect, owner: C).

That's publishable. It quantifies, it names plural factors, it admits luck, and every action item has an owner and a type.

### 3.4 The action items are the only part that changes the system

A postmortem that ends without owned, dated, typed action items is a diary entry. The action items are where the learning becomes a permanent change, and there are three types, each addressing a different layer:

- **Prevent** — make the failure impossible (or much less likely). "Add a slow-call circuit breaker so a slow dependency sheds instead of cascading." The most valuable type, and the hardest.
- **Detect** — make the failure *visible faster* next time, even if you can't prevent it. "Add a convergence-audit alert that fires when post-heal CRDT state diverges." If you can't prevent it, at least don't be surprised by it.
- **Mitigate** — reduce the *impact* when it does happen. "Lower the per-try timeout so a slow dependency costs less budget." Buys time and reduces blast radius.

A good postmortem usually has at least one of each, because a single incident exposes gaps at all three layers. The anti-pattern is a postmortem with five "prevent" items all owned by "the team" with no date — that's five wishes. One "prevent" owned by a named person with a sprint deadline beats five orphaned aspirations. The test: six months later, can you point at the merged PR for each action item? If not, the postmortem didn't change the system.

### 3.5 Postmortems for the gameday that *held*

A subtlety people miss: **a drill whose hypothesis held still deserves a postmortem.** It feels redundant — "nothing broke, what's to write up?" — but the held drill is exactly where the "where we got lucky" and "what we'd improve" sections earn their keep. The broker-loss drill that held still has a story: redelivery *did* happen (you observed 12 redelivered messages), idempotency absorbed it, recovery took 90 seconds. Document that. Why?

- **It's the evidence.** "Our exactly-once held under broker loss" is a claim; the postmortem with the observed-redelivery count and the audit result is the *proof*. The capstone reviewer wants the proof.
- **It captures the conditions of success.** The drill held *because* `min.insync.replicas=2` and the idempotency keys were in place. Naming the conditions means you'll notice if a future change removes one.
- **It surfaces the near-misses.** Recovery took 90 seconds; the SLO tolerated it, but barely. "Where we got lucky: recovery was 90 s against a 120 s budget — a slower leader election would have breached." That's a future incident, caught in a successful drill.

So Drill A and Drill B both get postmortems regardless of outcome. The capstone *requires* two postmortems; it does not require two *failures*. Hold or refute, you write it up.

---

## 4. The "five whys" debate

The syllabus names the "five whys debate" specifically, and it's worth your judgment, not just your memorization.

### 4.1 What "five whys" is

"Five whys" is a root-cause technique: ask "why?" repeatedly until you reach the *one* underlying cause. "The order p99 breached — why? Because cart retried the slow call — why? Because the retry policy retries slow responses — why? Because we copied a default retry config — why? Because we never reviewed retry policy against SLOs — why? Because we have no retry-policy review step." Root cause: "no retry-policy review step." Fix that one thing.

### 4.2 The critique

The argument against five-whys-as-doctrine (most associated with John Allspaw and the systems-thinking / resilience-engineering crowd): **real incidents in complex systems rarely have a single linear root cause.** They have multiple contributing factors that were *each necessary but only jointly sufficient* — remove any one and the incident doesn't happen, but no single one "is" the cause. The five-whys process forces a tree of causes into a single line, which:

- **Stops too early or arbitrarily.** Why five? Why this chain and not the parallel one? The technique manufactures a single narrative and then declares it complete.
- **Encourages blame.** A single linear chain often terminates at a person ("...why? because Alice didn't review it"), which is exactly the blame the postmortem is supposed to avoid.
- **Hides the system.** The interesting truth — that the timeout, the retry policy, *and* the missing circuit breaker had to align for the breach — gets flattened into "the retry config," and you fix one thing while the other two latent factors wait for the next incident.

The honest alternative is **contributing-factors analysis**: list *all* the conditions that had to be true for the incident, treat them as a set rather than a chain, and address the set. The example postmortem in §3.3 does this: three contributing factors, three action items, no pretense that one of them "is" the root cause.

### 4.3 The balanced position (what to actually do)

Five whys isn't worthless; it's a fine *brainstorming prompt* to dig past the first symptom. The failure is treating its output — a single root cause — as the truth. Use the "keep asking why" reflex to get past "the broker died" to the systemic conditions, but then **branch**: at each "why," ask "what *else* had to be true?" and you turn the line into a tree, which is the contributing-factors picture. Name this nuance in your postmortems — "we used five-whys to dig, but the incident had three contributing factors, not one root cause" — and you'll sound like someone who has actually run incident reviews, because that's exactly the sophistication a staff engineer brings to one.

### 4.4 Counterfactuals and hindsight bias: the two traps in causal analysis

Two cognitive traps poison postmortems, and naming them keeps your analysis honest:

- **Counterfactual reasoning.** "If only Alice had checked the dashboard, she'd have caught it." Counterfactuals describe a world that didn't happen and feel like analysis but aren't — they're a way of assigning blame dressed as a fix. The honest replacement: "the dashboard didn't make the anomaly salient enough to catch during a normal scan — what would have?" That's a *system* question with a real answer (a better alert, a clearer panel), where the counterfactual is a *person* judgment with no fix.
- **Hindsight bias.** After an incident, the cause looks *obvious* — "how did nobody see the disk would fill?" — because you now know the outcome. But the engineers acting *before* the incident didn't have the outcome; they had a normal-looking system and a hundred things competing for attention. The discipline: analyze what the signals looked like *at the time*, not what they obviously meant *in retrospect*. "In hindsight the lag trend was climbing, but at the time it was within the normal daily variation and there was no alert" is the honest framing, and it points at the real fix (an alert on the trend), where "they should have noticed" points at nothing.

Both traps share a tell: they end at a person who "should have." A postmortem that keeps arriving at "should have" is doing blame, not analysis. Redirect every "should have" into "what would have made the right thing easy / the wrong thing hard / the signal louder?" — that's the move from counterfactual blame to systemic fix, and it's the heart of what "blameless" actually requires in practice.

### 4.5 The postmortem is a teaching document

The final reframe: a good postmortem isn't filed and forgotten, it's *read by people who weren't there* — new hires, other teams, your future self. Its job is to transfer the hard-won lesson so the org learns once instead of repeatedly. That's why the structure matters (a reader can skim the summary, then drill into the timeline), why the impact is quantified (a reader needs to gauge severity without having lived it), and why the contributing factors are explicit (a reader on a different team checks whether *their* system has the same latent factors). The danluu/post-mortems corpus exists precisely because public postmortems teach the whole industry. Write yours as if it'll be read by someone who needs the lesson and has none of the context — because in six months, that someone is you.

---

### 3.6 A reusable postmortem skeleton

Copy this into `postmortems/` and fill it in for each finding. Keeping the headings identical across postmortems makes them skimmable and comparable — a reader knows exactly where to look:

```markdown
# Postmortem: <short title>

- **Date:** <incident/drill date>
- **Authors:** <names>
- **Status:** draft | reviewed | published
- **Severity:** SEV-<n> (or "gameday finding")

## Summary
<2-3 sentences: what happened, the impact, how it was resolved.>

## Impact
<Quantified. Requests/users/dollars, duration, which SLO. Extrapolated to
production scale.>

## Timeline (all times <TZ>)
- HH:MM:SS — <fault injected / signal observed / action taken>
- HH:MM:SS — ...
- HH:MM:SS — recovery confirmed; audit result

## Detection
<How was this found? Alert / audit / customer report? Was that a good
detection story?>

## Contributing factors
1. <factor one — necessary but not sufficient alone>
2. <factor two>
3. <factor three>

## What went well
- <...>

## What went poorly
- <...>

## Where we got lucky
- <the thing that didn't go wrong this time but easily could have>

## Action items
| # | Action | Type (prevent/detect/mitigate) | Owner | Due |
|---|--------|--------------------------------|-------|-----|
| 1 | <...>  | prevent                        | <who> | <when> |
| 2 | <...>  | detect                         | <who> | <when> |
| 3 | <...>  | mitigate                       | <who> | <when> |
```

Notice every action item row has an owner and a due date — the table *forces* it, which is why a table beats a bulleted list here. An action item without an owner can't be entered into the table at all, which is exactly the friction you want.

## 5. From gameday to capstone

Everything this week is rehearsal. The capstone (Week 24) requires **two** chaos-drill postmortems:

- **Drill A — Region failover.** Kill the primary region during a 1k-RPS load test; document impact, recovery, lessons. This week's experiment #2 (the partition) and the gameday structure are exactly how you'll run it.
- **Drill B — Kafka broker loss.** Lose a broker mid-traffic; prove the exactly-once consumers don't double-process and the outbox guarantees integrity. This week's §2 drill *is* Drill B, run as a rehearsal.

So treat this week's mini-project as a draft of two of your capstone's six required deliverables. The postmortems you write Friday should be good enough that, two weeks from now, you lightly revise them rather than start over. The gameday muscle — hypothesis, metric, fault, abort, audit, blameless writeup — is the muscle the capstone reviewers test, and the one you'll use on every real on-call rotation for the rest of your career.

### 5.1 The blind gameday: the upgrade that makes it real

Everything so far assumed the people running the experiment know the fault. The next level — and the one worth aspiring to — is the **blind gameday**, where a *game master* knows the injected fault and the *responders* don't. The responders see the symptom (an SLO burning, an alert firing) and have to diagnose it from the outside, exactly as they would in a real incident, while the game master watches and only reveals the fault in the debrief.

This is the single most realistic on-call practice there is, because it tests the thing real incidents test: **can you diagnose an unknown failure from its symptoms under time pressure?** Knowing in advance that "we're going to kill a broker now" removes the hardest part of incident response — the *figuring out what's wrong* part. A blind gameday puts that part back. The responder sees consumer lag climbing and a payment-error alert and has to reason: is it the broker, the consumer, the network, the database? They run `istioctl`, check offsets, read traces, form and discard hypotheses — and the game master learns whether the team's runbooks, dashboards, and instincts actually lead them to the cause.

For your solo capstone rehearsal, you can approximate this: have a teammate plant one of several possible faults and run the drill not knowing which, or write the fault into a branch and run the gameday a day later when you've forgotten the specifics. It's less pure than a true two-team blind gameday, but the diagnostic muscle — symptom to cause, blind — is the one the capstone challenge and every real rotation will exercise.

### 5.2 The debrief: turning a drill into learning

The 5-minute debrief at the end of the gameday is where the value is captured or lost. A good debrief answers four questions for each experiment:

1. **Did the hypothesis hold?** Verdict from the metric, stated plainly. No hedging.
2. **If refuted, is it a bug or a tuning issue?** A refuted hypothesis is a finding, but findings have grades. "The retry budget amplifies latency" is a *bug* (a design flaw to fix). "The HPA scaled but took 90 s, slightly over our 60 s target" is a *tuning* issue (a knob to turn). Both get action items; the bug gets a higher priority.
3. **What surprised us?** The most valuable debrief output. The fault that did something nobody predicted — recovered faster than expected, or took down something unrelated — is pointing at a gap in your mental model of the system. Chase it.
4. **What do we change?** Every finding becomes an owned action item, or it didn't happen. "We'll keep an eye on it" is not an action item.

The discipline that makes debriefs useful: **do them immediately, while the timeline is fresh**, not "next week when we have time." The gameday's findings decay fast; the team that debriefs at minute 85 captures them, the team that schedules the debrief for next Tuesday has forgotten half of them by then. The scribe's live timeline is what makes the immediate debrief possible — you're reading off a record, not straining to remember.

---

## 6. Recap

You should now be able to:

- Run a 90-minute gameday: pre-flight steady state, confirm abort conditions, run experiments one at a time with baseline→inject→observe→rollback→confirm, debrief, and assign postmortems.
- Staff the roles — commander/game master, scribe (live timeline), observer (the verdict) — even solo, by naming the hat you're wearing.
- Execute the broker-loss/exactly-once drill and prove the invariant with an idempotency-key audit, distinguishing "it recovered" from "it recovered *correctly*."
- Write a blameless postmortem with the SRE structure — quantified impact, the scribe's timeline, plural contributing factors, "where we got lucky," and action items with owners and types.
- Explain what "blameless" buys you operationally (the true timeline and honest near-misses) and articulate the five-whys critique (single linear causes are usually fiction; contributing-factors analysis is more honest) — and the balanced "use why-laddering to dig, then branch."
- Connect the week to the capstone's two mandatory drills (region failover, broker loss) and treat this week's postmortems as their drafts.
- Run the pre-flight checklist and the one-experiment-at-a-time discipline; run a blind gameday; debrief immediately while the timeline is fresh; and write owned, typed action items that actually change the system.
- Avoid the counterfactual and hindsight-bias traps, and write the postmortem as a teaching document for someone who wasn't there.

### A closing word on what this week is really for

It's tempting to treat chaos engineering as a stunt — the cool week where you get to break things. It isn't. It's the most honest week in the course, because it's the week your system's resilience *stories* meet a metric and either survive or don't. Every prior week you made a claim: the outbox guarantees exactly-once, the region fails over in sixty seconds, the CRDT converges. This week those claims become falsifiable, and some of them will be false — not because you built badly, but because distributed systems are genuinely hard and the gap between "I designed it to" and "it actually does" is where every real outage lives. The discipline of finding that gap on purpose, on a Tuesday, with a hypothesis and a rollback, is what separates an engineer who *operates* systems from one who merely ships them. Run the gameday like the capstone depends on it, because in two weeks it does — and run it like your future on-call rotations depend on it, because they will.

Next: the exercises put a real Chaos Mesh install, the six experiments, and the broker-loss EOS probe in your hands. Start with [Exercise 1 — Install and your first hypothesis-driven experiment](../03-exercises/exercise-01-install-and-first-experiment.md).

---

## References

- *Google SRE — Postmortem Culture*: <https://sre.google/sre-book/postmortem-culture/>
- *Google SRE — Example Postmortem*: <https://sre.google/sre-book/example-postmortem/>
- *Allspaw — "Each necessary, but only jointly sufficient"* (the five-whys critique): <https://www.kitchensoap.com/2012/02/10/each-necessary-but-only-jointly-sufficient/>
- *PagerDuty — Postmortem process*: <https://response.pagerduty.com/after/post_mortem_process/>
- *Chaos Mesh — Run a Chaos Experiment*: <https://chaos-mesh.org/docs/run-a-chaos-experiment/>
- *danluu/post-mortems* (public corpus): <https://github.com/danluu/post-mortems>
