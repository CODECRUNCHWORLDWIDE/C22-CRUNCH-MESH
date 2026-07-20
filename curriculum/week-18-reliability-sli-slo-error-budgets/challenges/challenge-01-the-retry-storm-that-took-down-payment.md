# Challenge 1 — The Retry Storm That Took Down Payment

**Time estimate:** ~90 minutes.

## Problem statement

You are on call. At 09:14 the payment service had a 30-second blip — a brief GC pause, a momentary network hiccup, the kind of thing that happens and self-heals. Payment recovered at 09:14:30 entirely on its own. And yet the incident channel shows cart, inventory, and the BFF were *all* throwing errors until 09:34 — twenty full minutes — and the payment dashboard shows payment's CPU and error rate *staying pegged* long after the original blip ended, in a sawtooth pattern: payment comes up, gets slammed, falls over, comes up, gets slammed again. The error budget for cart burned ~15% in twenty minutes. Someone restarted payment three times; it didn't help.

The app team is baffled: "payment recovered in 30 seconds, we saw it healthy at 09:14:30 — why was everything broken for 20 more minutes?" Someone has already noticed that *scaling payment up* eventually ended it, and is now proposing "just run payment at 5× capacity always," which would mask the real problem at enormous cost and still fail under a bigger blip.

Your job: prove that the **outage outlasted the fault** — that the 20-minute outage was not caused by a 20-minute payment problem but by the *system amplifying* a 30-second one — name the exact amplification mechanism, and fix it so the *same* 30-second blip becomes a non-event. "Run payment at 5× forever" is not an answer; it's paying to hide a design flaw that will resurface.

This mirrors the most common real reliability on-call scenario there is: **cascading failure by retry amplification.** A dependency blips. Every caller, on a fixed retry schedule with no jitter, retries at the *same instant* — a synchronized thundering herd. With no retry budget, each failure spawns more retries, multiplying the load on the recovering dependency exactly when it's most fragile. With no circuit breaker, callers keep hammering the dead dependency instead of failing fast and backing off. The blip recovers, but the retry storm it triggered is now *self-sustaining*: the herd keeps re-killing payment every time it stands up. The fault is over; the amplification is not. The fix is never "more capacity" — it's removing the amplification.

## The harness

Reproduce it. You need: a payment dependency you can blip, the cart caller making retries, and the Week 17 metrics to watch. Model the broken caller — fixed-interval retries, no jitter, no retry budget, no circuit breaker:

```python
# broken_caller.py — the WRONG way: synchronized retries, no budget, no breaker.
# Many concurrent callers all run this against payment. Blip payment for 30s and watch.
import time, requests

def call_payment_broken():
    for attempt in range(5):                 # up to 5 retries, ALWAYS
        try:
            r = requests.post("http://payment.shop:8080/charge", timeout=2)
            if r.status_code < 500:
                return r
        except Exception:
            pass
        time.sleep(1.0)                       # FIXED 1s backoff, NO jitter -> all callers
                                              # retry in lockstep: a synchronized herd
    raise RuntimeError("payment failed after 5 retries")
```

Run many concurrent copies of this against payment, then **blip payment for 30 seconds** (kill it, or set it to 100% 503 for 30s, then restore it). Watch the metrics: payment's request rate *spikes* the moment it tries to recover (the herd hits it), it falls back over, and the outage *outlasts* the 30-second blip by many minutes. You now have the storm. Diagnose it from the metrics and traces before reading the fix.

## Your task

Produce a diagnosis and a fix with these parts:

1. **Symptom** — the timeline: the original fault window (09:14:00–09:14:30) versus the *outage* window (09:14–09:34), proven from the metrics. Quote payment's request-rate and error-rate graphs showing the rate *spiking* after the blip (the herd) and the sawtooth recovery pattern.
2. **Proof the outage outlasted the fault** — the load-bearing evidence. Show that payment's *upstream* fault lasted 30 s but payment's *error rate* stayed high for 20 minutes, and that payment's *incoming request rate* during those 20 minutes was far *above* normal (the retries piling on). The fault was brief; the load that kept it down was the system's own retries. A trace from Week 17 showing one user request spawning a fan of retried payment calls is strong corroboration.
3. **The mechanism** — name it precisely: (a) **no jitter** → all callers retried in lockstep, hitting recovering payment in synchronized waves; (b) **no retry budget** → each failure multiplied into more retries, so the load *grew* with the failure rate instead of being capped; (c) **no circuit breaker** → callers kept calling dead payment (burning timeouts, adding load) instead of failing fast and giving it room to recover. Together: a self-sustaining retry storm.
4. **The fix** — apply all three (Exercise 2's patterns): **full jitter** on the backoff (de-synchronize the herd), a **retry budget** (cap retries at ~10% of traffic so they can't amplify a widespread failure), and a **circuit breaker** (fail fast when payment is clearly down, giving it room to recover via half-open probes). Re-run the *same* 30-second blip and show it now recovers in ~30 seconds, not 20 minutes.
5. **Prevention** — one systemic change so a blip never storms again (e.g. "all dependency calls go through a shared resilience wrapper with jitter + budget + breaker, so no caller can wire a raw retry loop," or "mesh-level retry budgets via Istio/Envoy as a backstop even if an app gets it wrong").

You must reach the diagnosis with **at least two** independent signals — e.g., the outage-outlasts-fault timeline *and* the elevated-request-rate-during-recovery (the herd), or the synchronized retry waves in the rate graph *and* a trace showing the retry fan-out. One signal is a guess; two is a diagnosis.

## The fix, applied

Wrap the payment call in the Exercise 2 pattern — breaker + timeout + jittered, budgeted retry:

```python
# fixed_caller.py — jitter + budget + breaker. The same blip is now a non-event.
import random, time
# (a) FULL JITTER: random in [0, exp cap] de-synchronizes the herd
def backoff(attempt, base=0.05, cap=1.0):
    return random.uniform(0, min(cap, base * (2 ** attempt)))
# (b) a retry BUDGET caps retries at ~10% of calls (suppressed when failures are widespread)
# (c) a CIRCUIT BREAKER (e.g. pybreaker / sony-gobreaker-equivalent) fails fast when payment
#     is down, so callers stop hammering it and it can recover through half-open probes.
```

Re-run the blip:

```
# BEFORE: 30s blip -> 20min outage (the storm). payment req-rate SPIKES on recovery.
# AFTER:  30s blip -> ~30s degraded, then recovered. breaker OPENED (fail-fast, no herd),
#         jitter spread the probe load, budget refused to amplify -> payment recovered cleanly.
```

## Acceptance criteria

- [ ] A file `challenge-01-diagnosis.md` with all five parts above.
- [ ] You prove the **outage window outlasted the fault window** with the metrics (the central insight), and show payment's incoming request rate was *elevated* (the herd) during the recovery.
- [ ] You name all three contributing mechanisms (no jitter, no budget, no breaker) and explain how each amplified the fault.
- [ ] Your fix applies **all three** patterns and demonstrates the *same* 30-second blip now recovers in ~30 seconds — quantified, before/after.
- [ ] Your fix is NOT "add capacity" — you explicitly reject that as masking the amplification, and can explain why it fails under a larger blip.
- [ ] Committed to your Week 18 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The two wrong "fixes" you must NOT write:

- **"Run payment at 5× capacity."** This *masks* the amplification by brute force: more capacity absorbs the storm *this time*, at 5× the cost forever, and still falls over under a blip big enough that 5× isn't enough. It treats the symptom (payment overloaded) instead of the cause (the system manufacturing that overload from a tiny fault). You'd be paying continuously to hide a design flaw that's one bad day from resurfacing. Capacity is not a substitute for removing the amplification.
- **"Remove the retries entirely."** Over-correction. Retries are *good* — they recover the genuine transient (a single dropped packet) that the user would otherwise see as an error. The problem was never retries; it was *un-jittered, unbudgeted, breaker-less* retries. Removing them trades a rare amplified-failure mode for a common un-recovered-transient mode — more user-visible errors in the normal case. The fix makes retries *safe* (jitter + budget + breaker), not absent.

A related real-world cousin worth naming in your writeup: the **synchronized-cron thundering herd** — every instance refreshing a cache or token at the top of the hour, hammering the backend in lockstep. Same root cause (synchronization), same fix (jitter the schedule). Whenever many actors do the same thing at the same time, you have a herd waiting to happen, and jitter is the antidote.

## Stretch

- Add the **mesh backstop**: configure an Istio/Envoy retry budget (Week 7/8) on the payment route so that *even if* an app wires a raw retry loop, the mesh caps the aggregate retry fraction. Demonstrate the mesh suppressing the storm when the app-level fix is (deliberately) removed — defense in depth.
- Measure the **blast radius reduction**: with the broken caller, quantify how much error budget the blip burned; with the fixed caller, quantify it again. The difference is the dollar value of the patterns.
- Reproduce the **half-open stampede**: a naive breaker that lets *all* traffic through the instant it half-opens just re-storms payment. Show why the breaker must trickle only a *few* probe requests in half-open (Exercise 2's `MaxRequests`), and what happens if it doesn't.

## Why this matters

Every distributed system hits this wall: a small, brief fault becomes a large, long outage, and the team's first instinct ("the dependency was down") is *wrong* — the dependency recovered; the *system* kept it down. The difference between a system that shrugs off a blip and one that amplifies it into an incident is whether *someone* designed in jitter, retry budgets, and circuit breakers — and whether *someone* on call can look at "a 30-second blip caused a 20-minute outage" and immediately suspect amplification rather than chasing the (already-recovered) dependency. When you defend your `cart-reliable` mini-project — and when Week 22's gameday deliberately blips your payment dependency to see if your system storms — "I know exactly how a transient becomes a cascade and how to stop the amplification" is the line that says you've engineered reliability, not just hoped for it.
