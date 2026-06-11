# Challenge 1 — Deliver the Capstone Defense Live

**Time estimate:** the full Friday slot (~60-minute review + preparation).

## Problem statement

It is Friday. The cohort is in the room. Two external reviewers — staff-or-principal engineers who did not take this course and owe you nothing — are here to decide whether your Polyglot Marketplace Backbone is a system you can defend or a demo you can describe. You have one hour. Your running two-region active-active system needs to be healthy *now*, your six artifacts need to be on the table, and you need to walk one order through the live system, run the failure-mode discussion, and survive the staff-engineer question bank.

This is not a slide deck you read. It is the architecture review from Lecture 1, run for real, with reviewers who will interrupt. Your job: deliver it end to end, defend every choice on the *requirement* (not on taste), name your own biggest risk before they find it, and walk out with a risk list you turn into your portfolio's "known limitations." "It works on my machine" is not a defense. "Here is one order traced through the live system, here are the two drills I ran with their postmortems, and here is the one thing I'd fix first with money" is.

## What you must deliver in the hour

Run the Lecture 1 §1.3 agenda. Concretely, you must hit every one of these, live:

1. **Context (5 min).** One sentence each: what the system is for, its scale (steady 200 rps, flash-sale peak 1k), and its consistency requirement (cart eventually-consistent CRDT, payment exactly-once strong). No architecture yet.

2. **The C4 container walk (10 min).** Your container diagram on screen. Walk the shape: BFFs → order → cart/inventory/payment → Kafka spine → Temporal → Postgres + Debezium → search/analytics. Establish the flow, not the mechanism.

3. **Trace one order live (20 min).** The heart. Place one order with a known idempotency key and follow it through every hop on the *live* system, ending in a trace-to-log jump (Exercise 1). Let the reviewers interrupt with the hard questions. This is where you prove the system is observable enough to operate.

4. **The two chaos drills (13 min).** Walk Drill A (region failover) and Drill B (broker loss) from their *measured* postmortems: the RTO, the zero-data-loss, the empty double-charge query. Not "it should fail over" — "it failed over in 47 seconds, zero double-charges, here's the postmortem."

5. **Cost, capacity, and consistency (7 min).** The order-service capacity memo, the per-order cost (fixed vs per-order), and the per-field consistency model — which data is CRDT, which is strongly consistent, and *why each*.

6. **The risk list and sign-off (5 min).** The reviewers name the risks; you tag each accept/mitigate-now/mitigate-later and assign an owner. You write them down. That list becomes your README's known-limitations section.

## Your preparation tasks

Before the hour, you must:

1. **Bring the system up healthy and warm.** Both regions, all services Ready, the observability pipeline live, the Pact broker green. Do this *before* the room sits down, not during. A cold start mid-defense is the most common avoidable disaster.

2. **Rehearse the trace-an-order walk three times.** It involves a live system that can misbehave. Rehearse until it's under three minutes of clicking, with the narration ("this event cleared the BFF, the lease was acquired here, the Temporal workflow charged exactly once") automatic.

3. **Prepare a fallback recording.** Networks fail during demos. Have a screen recording of a successful trace-an-order walk ready to cut to if the live system hiccups. "The live system is having a moment, here's a recording of the same walk from an hour ago" is completely acceptable and far better than freezing.

4. **Pre-load your own three biggest risks** (Lecture 1 §1.6). Name them before the reviewers do: the shared Temporal failure domain, the deliberate eventual-consistency of the cart, the cross-region coherency cost of active-active. Naming them first sets the agenda and reads as senior.

5. **Have an answer to every question in the bank** (Lecture 1 §1.4), so the five the reviewers pick are easy. Especially: "which parts are strong vs eventual and why," "prove the cart converges," "what happens on broker loss," "show me mTLS is enforced," and "what does one order cost."

## Acceptance criteria

- [ ] The two-region system is healthy and warm at defense time; all services Ready, the Pact broker green, the observability pipeline live.
- [ ] You trace one order through every hop on the *live* system, ending in a trace-to-log jump, in under three minutes.
- [ ] You present both chaos-drill postmortems with *measured* numbers (RTO, zero-double-charge query result), not estimates.
- [ ] You defend the per-field consistency model: which data is CRDT, which is strongly consistent, and the requirement-based reason for each.
- [ ] You name your own three biggest risks before the reviewers ask.
- [ ] You answer at least five questions from the staff-engineer bank without claiming a number you can't show.
- [ ] You walk out with a risk list, each item tagged and owned, and turn it into the README's "Known limitations and next steps" section.
- [ ] A `challenge-01-defense-notes.md` capturing: the questions you were asked, the ones you answered well, the one you fumbled, and what you'd say differently — the retrospective that makes the *next* review better.

## The trap (read after a first attempt)

The ways a capstone defense goes wrong, each avoidable:

- **Reading the diagram instead of walking the order.** "This is order, this is cart, this is Kafka." Boxes without flow or failure modes. Walk the *order*, name the failure at each hop. The order is the protagonist; the boxes are scenery.
- **Defending a choice on taste.** "I used Istio because it's the best mesh" tells a reviewer you don't know the tradeoff. "I used a mesh because I need uniform mTLS across a polyglot fleet without each of five teams implementing TLS, and the sidecar tax I measured is X" is a defense.
- **Claiming numbers you didn't measure.** "Failover is about a minute." "Show me." Silence. Every number you stated is now suspect. Run the drills (Exercises 2, 3), then claim — with the postmortem open.
- **Hiding the weakness.** Pretending the single Temporal cluster is fine. They notice, and now it looks like you didn't know or tried to slip it past. Name it first.
- **Treating "everything is strongly consistent" as the safe answer.** It's the *wrong* answer — it says you didn't think about CAP per data type, which is the entire premise of this course. The cart is eventually consistent *on purpose*, and you defend *why*.
- **Freezing when the live demo breaks.** Cut to the fallback recording, narrate calmly, move on. Composure under a misbehaving demo *is* the senior signal; panic is the junior one.

A related real-world truth worth naming: the capstone defense and a staff-engineer interview loop are the *same skill* wearing two hats. The defense argues for a system you built; the interview asks you to design one on the spot. Both reward the same muscles — tracing data flow, naming failure modes, defending tradeoffs with numbers, and being honest about what you don't know. The mock interview you did last week was the rehearsal; this is the performance.

## Stretch

- Deliver the defense with the canary rollback driven by **Flagger** live — induce a bad v2 and let the controller roll it back automatically on the SLO breach, on camera, without touching a weight.
- Run the defense against **two real cloud clusters** (GKE/EKS) instead of two Kind clusters, and field the "what's the real cross-region replication lag" question with a measured number.
- Invite a reviewer to **pick the order's failure**: let them choose which component you kill mid-trace (a broker, the primary region, a Temporal worker) and trace the order *through* that failure live. Surviving an unscripted failure on camera is the strongest possible close.

## Why this matters

This hour is what the entire course was for. Anyone can follow a tutorial and stand up Istio, or Kafka, or a CRDT. The thing that's rare — the thing that gets the staff offer and the platform-lead role — is the ability to stand in a room full of skeptics, bring a real distributed system up, walk a real request through it, distinguish the failure domains, defend every consistency choice on its requirement, name the risks you already know about, and run the room while you do it. That is not a tutorial skill; it is a *judgment* skill, and judgment is what twenty-four weeks of theory-before-code, single-service-before-multi-service, and multi-service-before-multi-region were quietly building. Deliver this defense and you have proven, to two external reviewers who owe you nothing, that you can own a backend platform and defend it under cross-examination. That's the graduation line. Cross it.
