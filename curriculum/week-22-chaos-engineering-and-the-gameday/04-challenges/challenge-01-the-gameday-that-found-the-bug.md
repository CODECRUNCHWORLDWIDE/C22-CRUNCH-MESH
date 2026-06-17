# Challenge 1 — The Gameday That Found the Bug

**Time estimate:** ~90 minutes.

## Problem statement

You are running the team gameday. The runbook has six experiments; five behave as predicted. The sixth refutes its hypothesis: a steady-state SLI you expected to *hold* breaches its SLO and stays breached. Someone on the call says "that's just noise, the metric is flaky, let's move on." Someone else says "let's loosen the SLO so it passes." Both are wrong. **A refuted hypothesis under a controlled fault is a finding, and a finding is the entire reason the gameday exists.** Your job is to recognize it as real, diagnose the *actual* latent bug from the outside, fix it without weakening the experiment, and write a publishable blameless postmortem.

This mirrors the most valuable real gameday outcome there is. The whole point of injecting controlled failure is to find the gap between designed and actual resilience *before* a real incident does. When the gap shows up, the temptation is to explain it away — because admitting it means work, two weeks before the demo. The engineer who instead says "stop, that's a finding, let's diagnose it" is the one who makes the system actually resilient instead of merely confident.

## The setup — plant one latent bug

To run this challenge honestly, you (or a partner acting as game master) introduce **exactly one** latent bug into your capstone system, then run the gameday blind. Pick one — the more realistic for *your* build, the better:

- **The latency-amplifying retry budget.** The `order`→`inventory` path retries on slow responses with a per-try timeout longer than half the SLO budget. Under experiment #3 (200 ms injected delay), retries *double* the latency contribution and the order p99 blows the 1 s SLO. (This is the worked postmortem in Lecture 2 §3.3 — but you must *discover* it from the metric, not recall it.)
- **The lossy CRDT merge.** The cart "merge" uses last-write-wins on the whole cart instead of an OR-set per item. Under experiment #2 (the 5-minute partition), adds made on both sides during the partition are lost on heal instead of converging. The availability SLI looks fine; the *convergence audit* finds missing items.
- **The HPA on the wrong metric.** The `order` HPA scales on a CPU request set so high it never triggers. Under experiment #4 (CPU stress), the pod browns out, p99 climbs, and no scale-out happens — the SLO is violated silently (latency, not errors).
- **The double-processing consumer.** The "idempotent" consumer commits offsets but its idempotency check has a race (checks-then-inserts without a unique constraint). Under experiment #6 (broker loss), redelivery slips a duplicate through and one order gets charged twice. The dashboard recovers green; the audit finds the double-charge.

If you're solo, write the bug into a branch, *don't look at which one it is for a day*, then run the gameday against it cold. The blind diagnosis is the skill.

## Your task

Run the gameday and produce a diagnosis + fix + postmortem with these parts:

1. **The refutation, caught live.** Which experiment refuted its hypothesis, and the exact metric/audit that showed it. Quote the SLI value crossing the SLO (or the audit finding the duplicate/missing data), with the timestamp. "I noticed p99 climbed" is not enough — *which* metric, by how much, when.
2. **Proof it's real, not noise.** At least **two independent signals** that the breach is a true finding, not metric flakiness: e.g., the SLI breach *and* a trace exemplar showing the slow path; or the convergence audit's missing items *and* the per-side operation logs; or the double-charge row *and* the consumer's redelivery count. One signal is a guess; two is a diagnosis.
3. **The real cause (contributing factors, plural).** Diagnose the latent bug. Resist the single-root-cause reflex: name *all* the conditions that had to align (e.g., the per-try timeout *and* the retry-on-slow policy *and* the missing slow-call breaker). Use why-laddering to dig, then branch into the contributing-factors set (Lecture 2 §4).
4. **The fix, without weakening the experiment.** Fix the *system*, not the test. Lowering the SLO, loosening the abort condition, or removing the experiment are all surrenders — they make the finding disappear without fixing the bug. The valid fix changes the code/config so the *same* experiment now holds. Show the experiment re-run with the hypothesis now HELD.
5. **The blameless postmortem.** A publishable writeup: title/date/authors, summary, quantified impact (extrapolated to production scale), the scribe's timeline, detection, contributing factors, "what went well / poorly / where we got lucky," and action items each with an **owner** and a **type** (prevent/detect/mitigate). It must read as if it analyzes the system, never a person.

## The rules

- You must reach the diagnosis with **at least two** independent signals. The challenge is failed if your postmortem rests on a single observation.
- The fix must make the **same experiment** pass. If you changed the experiment to make it green, you confirmed the bug and then hid it.
- The postmortem must list **contributing factors (plural)**, not a single root cause, and every action item must have an owner and a type.
- You must quantify impact and **extrapolate to production scale** ("6% of order requests breached SLO; at 1k RPS that's ~3,600 slow requests, exhausting the error budget in under an hour"). "Some requests were slow" fails this.

## Acceptance criteria

- [ ] A file `challenges/challenge-01/postmortem.md` with all five parts.
- [ ] The refutation is quoted from the actual metric/audit with a timestamp, not described from memory.
- [ ] Two independent signals support the diagnosis.
- [ ] The cause is stated as contributing factors (plural), reached via why-laddering-then-branching.
- [ ] The fix makes the **same** experiment's hypothesis HELD on re-run, with the before/after metric captured.
- [ ] The postmortem is blameless (analyzes system + decisions-with-information-available, never a person), quantified, extrapolated to scale, with owned + typed action items.
- [ ] Committed to your Week 22 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The three wrong "fixes" you must NOT write:

- **"Loosen the SLO so the experiment passes."** This makes the finding vanish by redefining "working" to include the broken behavior. The next incident is now *inside* your SLO and you won't even page on it. Moving the goalposts to score is not a fix; it's institutionalizing the bug.
- **"The metric is flaky; ignore it."** Sometimes a metric *is* flaky — which is why you require two signals. But "ignore it" without confirming it's flaky (by looking for the second signal) is how real findings get waved off. If the second signal confirms the breach, the metric wasn't flaky; the system was.
- **"Remove the experiment."** Dropping the experiment that found the bug is the gameday equivalent of un-meshing the crash-looping service. You adopted chaos engineering precisely to find this; deleting the experiment that found it throws away the entire practice.

## Stretch

- **Add the regression experiment.** Once fixed, add an experiment to your recurring suite (a `Schedule`) that specifically tests the bug you found, so it can never silently return. This is the "detect" action item, made real.
- **Run it blind for real.** Have a teammate plant a *different* one of the four bugs and run the gameday without knowing which. Diagnosing blind is the actual on-call skill; planting-then-diagnosing-your-own is easier than it looks.
- **The bimodal-latency variant.** If you found the retry bug under uniform delay, re-run with a *bimodal* delay (most calls fast, a few very slow). It's harder to detect and breaches at a lower injected latency — exactly the "where we got lucky" from the Lecture 2 postmortem, made concrete.

## Why this matters

Every system has latent bugs that only show under failure — a retry that amplifies, a merge that loses, a scaler that doesn't, an "idempotent" consumer that races. They are invisible on the happy path and catastrophic at 3 a.m. The gameday is how you find them on a Tuesday with a metric watching and a rollback ready, instead of in production with users watching and a pager going off. When you defend your capstone, "we ran a gameday, found that our retry budget amplified latency under a slow dependency, fixed the timeout and added a slow-call breaker, and here's the postmortem" is the sentence that proves you operated the system, not just built it. This challenge is that sentence, earned. Capstone Drills A and B are this challenge, graded.
