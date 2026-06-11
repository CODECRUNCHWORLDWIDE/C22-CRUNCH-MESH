# Lecture 1 — SLIs, SLOs, Error Budgets, and Burn-Rate Alerting

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can define an SLI that reflects user pain, set an SLO and compute its error budget as a spendable resource, derive multi-window multi-burn-rate alerts from first principles, and defend the whole framing — including why 100% is the wrong target — against product pressure.

If you remember one sentence from this lecture, remember this one:

> **An SLO is a budget, not a ceiling — the error budget (1 − SLO) is permission to fail that you spend deliberately on velocity and risk, and burn-rate alerting is just watching how fast you're spending it.**

Last week you made the system measurable. This week you decide what "reliable enough" means and turn it into arithmetic. The whole edifice — SLI, SLO, error budget, burn rate — is built on the metrics you already have (Week 17's `istio_requests_total` and your app RED histograms). An SLI is a PromQL ratio. An SLO is a number you compare it to. An error budget is the gap. A burn rate is a derivative. None of it is exotic; the skill is choosing the *right* SLI and defending the *right* SLO, because the math is only as good as those two judgments.

---

## 1. SLIs: measuring the right thing

### 1.1 The shape of a good SLI

A **Service Level Indicator** is a ratio:

```
SLI = good events / valid events
```

That's it — the fraction of events that were "good," over the events that "count." For an availability SLI, good = non-error responses, valid = all responses:

```promql
# Availability SLI for cart: the fraction of requests that did NOT 5xx.
sum(rate(http_server_requests_total{service="cart", code!~"5.."}[28d]))
/
sum(rate(http_server_requests_total{service="cart"}[28d]))
```

For a **latency** SLI, good = requests served faster than a threshold, valid = all requests:

```promql
# Latency SLI: the fraction of requests served in under 250ms (good), over all requests.
sum(rate(http_server_request_duration_seconds_bucket{service="cart", le="0.25"}[28d]))
/
sum(rate(http_server_request_duration_seconds_count{service="cart"}[28d]))
```

Notice the latency SLI uses the `le="0.25"` *bucket* directly — the count of requests at-or-under 250 ms — which is *exactly* why last week's SLO-aligned histogram buckets matter: you can only build a latency SLI at a threshold you have a bucket boundary at. If you promised p99 < 250 ms but have no `le="0.25"` bucket, you literally cannot express the SLI. The two weeks lock together.

### 1.2 The four categories, and choosing the one that hurts

SLIs come in a few flavors; pick the one(s) that track what your users actually feel:

- **Availability** — did the request succeed? (The default, but beware: a 200 with a wrong body is "available.")
- **Latency** — was it fast enough? (Almost always needed; users feel slow as much as down.)
- **Correctness / quality** — was the answer *right*? (The hard one — the mesh can't measure it; only your app can. A cart that returns a stale total is "available and fast" and *wrong*.)
- **Freshness** — for data/read-models, how stale is it? (Your Debezium/CQRS read model from Week 14: "the search index is at most 5 s behind the source.")

The cardinal rule: **a badly-chosen SLI is worse than none, because it's green while users suffer.** The classic trap is the mesh-level availability SLI alone (recall Week 8 §2.3): `istio_requests_total` sees *network* success, so a service returning HTTP 200 with `"sorry, out of stock"` for every request scores 100% available while every user is failing. So you combine: a network-availability SLI (cheap, from the mesh), *plus* an app-level correctness SLI (your code emits a `cart_total_correct` signal), *plus* a latency SLI. Each covers a blind spot of the others. The SLI you *don't* have is the outage you won't see coming.

### 1.3 Request-based vs window-based SLIs

Two ways to count:

- **Request-based:** good requests / total requests, over the window. Simple, directly a probability. The PromQL above is request-based. This is the default and the one we use.
- **Window-based:** count the *time windows* (e.g. 1-minute buckets) that were "good" (met a per-window threshold), over all windows. Useful when you care about *sustained* badness (e.g. "no more than X bad minutes"), and it's how some SLAs are written. It's less sensitive to a single bad request and more sensitive to duration.

Request-based is the right default for the cart system and the one the burn-rate math below assumes. Know window-based exists, because some contractual SLAs (and some dashboards) speak in "bad minutes," and conflating the two gives wrong budget numbers.

### 1.4 The "valid events" question — what counts?

The denominator ("valid events") is where SLIs go subtly wrong, and it's worth dwelling on because the wrong denominator quietly poisons every number downstream. Some events should *not* count against you:

- **Client errors (4xx).** A `400 Bad Request` or `404` is usually the *client's* fault, not a failure of *your* availability — counting them makes you look unreliable for serving exactly the error you should. The common choice: exclude 4xx from the bad-event count (they're "valid but the client asked wrong"), or exclude them from valid events entirely. Be deliberate: a `429 Too Many Requests` *is* arguably your load-shedding (and might count), while a `404` is not.
- **Health checks and synthetic traffic.** Your own probes and load tests shouldn't inflate or deflate the SLI — filter them out by label, or you're measuring your monitoring, not your users.
- **Excluded endpoints.** A debug endpoint or an admin path may not be part of the user-facing SLO at all.

The discipline: write down *exactly* what your good-events and valid-events sets are, with the PromQL label selectors that implement them, in the SLO document. "Availability = non-5xx / (all requests except health checks and 4xx-from-malformed-input)" is a *specification*, and an SLI without that specification is an argument waiting to happen ("does that count?"). The denominator is a policy decision, not a technicality — and getting it wrong is how a team either flatters itself (excluding real failures) or flagellates itself (counting the client's mistakes as its own).

---

## 2. SLOs and error budgets

### 2.1 The SLO and the budget it creates

An **SLO** is a target for the SLI over a window: "99.9% of cart requests succeed, measured over 28 days." The window matters (28 days — a rolling 4 weeks — is the common choice; it's long enough to smooth noise, short enough to be actionable). The **error budget** is the complement:

```
error budget = 1 − SLO = 1 − 0.999 = 0.001 = 0.1%
```

That 0.1% is your *allowance* for failure. Translate it to something concrete:

- **As time** (for an always-on availability SLO): 0.1% of 28 days ≈ **40 minutes** of total downtime-equivalent budget per window. (Of 30 days: ~43 minutes. This is where the famous "three nines = ~43 min/month" comes from.)
- **As events:** if cart serves 100 M requests in the window, 0.1% = **100,000** requests are *allowed* to fail before you breach.

| SLO | Error budget | ≈ downtime / 30 days | ≈ downtime / year |
|---|---|---|---|
| 99% (two nines) | 1% | ~7.2 hours | ~3.65 days |
| 99.9% (three nines) | 0.1% | ~43 minutes | ~8.76 hours |
| 99.95% | 0.05% | ~22 minutes | ~4.38 hours |
| 99.99% (four nines) | 0.01% | ~4.3 minutes | ~52.6 minutes |
| 99.999% (five nines) | 0.001% | ~26 seconds | ~5.26 minutes |

Read that table as a *cost curve*. Each nine cuts the budget by 10× — and the engineering to earn it costs far more than 10× more (redundancy, faster failover, more testing, more on-call). Five nines means 26 seconds of budget a month: a single bad deploy blows the whole month. This is the quantitative backbone of §4's "100% is wrong."

### 2.2 The error budget as a resource you spend

Here is the reframing that is the whole point of the week. The error budget is not a line you must never cross — it is a **resource you spend deliberately**. You spend it on:

- **Risky deploys.** Shipping fast means occasionally shipping a regression. Budget is what lets you ship without fear; you spend a little budget on each deploy's risk.
- **Chaos drills** (Week 22). Deliberately breaking the system to learn costs budget — and it's *worth it*, because the budget you spend in a controlled drill is budget you don't lose in an uncontrolled outage.
- **Experiments, migrations, dependency upgrades** — anything that trades a little reliability for velocity or learning.

The dynamic this creates is the magic: **a team with budget left can take risks; a team that's burned its budget freezes and stabilizes.** That's the **error-budget policy** — the pre-agreed rule for what happens when the budget is spent. A typical policy: "while the budget is exhausted, the team halts feature launches and works only on reliability until the SLO recovers." This takes the reliability-vs-velocity fight *out of the meeting room* and hands it to the data: you don't argue about whether to slow down; you check the budget. When it's gone, you slow down — automatically, by prior agreement. That's why the policy must be written and signed off *before* the budget is spent, by both engineering and product. Negotiated in the calm, enforced in the storm.

### 2.3 SLI vs SLO vs SLA

Three letters people conflate:

- **SLI** — the *measurement* (the ratio).
- **SLO** — your *internal target* for it.
- **SLA** — a *contractual* promise to a customer, with consequences (refunds, credits) if missed.

The discipline: your **SLO is stricter than your SLA**. If you promise customers 99.9% (the SLA), you target 99.95% internally (the SLO), so you have a margin to catch a problem and fix it *before* you breach the contract and owe refunds. The SLA is the cliff; the SLO is the guardrail set back from it. A team whose SLO equals its SLA has no warning before it's paying penalties.

---

## 3. Burn-rate alerting from first principles

### 3.1 What burn rate means

You have a budget for the window. **Burn rate** is *how fast you're spending it, relative to the rate that would spend exactly all of it over the window.*

- Burn rate **1** = spending the budget exactly evenly; at this rate you'd exhaust it precisely at the end of the window and breach the SLO by a hair. Sustainable, just barely.
- Burn rate **2** = spending twice as fast; you'd run out in *half* the window.
- Burn rate **14.4** = you'd exhaust a 28-day budget in roughly 2 days.

The formula is just "current error ratio, divided by the budget":

```
burn rate = (current error ratio over a short window) / (1 − SLO)
```

```promql
# Burn rate over the last 1 hour, for a 99.9% SLO (budget = 0.001):
(
  1 - (
    sum(rate(http_server_requests_total{service="cart", code!~"5.."}[1h]))
    / sum(rate(http_server_requests_total{service="cart"}[1h]))
  )
) / (1 - 0.999)
```

If the error ratio over the last hour is 1.44% and the budget is 0.1%, the burn rate is 14.4 — you're spending the month's budget 14.4× too fast. That's a fire.

### 3.2 Why a static threshold fails, and what multi-window fixes

The naive alert is a static threshold: "page if error rate > 1%." It fails two ways at once:

- **Too sensitive** → false pages. A brief 1.5% blip that self-heals in 30 seconds pages you at 3 a.m. for nothing. You learn to ignore the pager. (Bad recall via alert fatigue.)
- **Too insensitive** → missed slow burns. A steady 0.5% error rate never trips the 1% threshold, but it *quietly exhausts your entire budget over a week* and you never get paged until you've breached. (Bad detection of the simmer.)

The fix is **multi-window multi-burn-rate alerting** (the Google SRE workbook pattern), and the insight is: *the severity of a budget threat is the product of how fast it's burning and how long it's been burning.* So you alert on **burn rate over multiple windows at once**:

- **Fast burn (the page):** a *high* burn rate sustained over a *short* window. "Burning 14.4× over the last 1 hour (and confirmed over the last 5 minutes)" → this exhausts the budget in ~2 days → **page now**.
- **Slow burn (the ticket):** a *lower* burn rate sustained over a *long* window. "Burning 3× over the last 6 hours (and confirmed over 30 minutes)" → this quietly eats the budget over weeks → **open a ticket**, no page.

Both come off the *same* error budget; they differ only in urgency. The canonical workbook configuration:

| Severity | Long window | Short window | Burn-rate threshold | Budget consumed if sustained | Action |
|---|---|---|---|---|---|
| Page (fast) | 1 hour | 5 min | 14.4 | 2% of budget in 1h | Page immediately |
| Page (medium) | 6 hours | 30 min | 6 | 5% of budget in 6h | Page |
| Ticket (slow) | 24 hours | 2 hours | 3 | 10% of budget in 24h | Ticket |
| Ticket (slow) | 72 hours | 6 hours | 1 | 10% of budget in 72h | Ticket |

### 3.3 The two-window trick: why each alert uses a long AND a short window

Each row has *two* windows (e.g. "1 hour" and "5 min"), and the alert fires only when *both* exceed the burn-rate threshold. Why two?

- The **long window** (1h) gives the alert its *meaning*: a high burn rate over an hour genuinely threatens the budget. But a long window alone is *slow to fire* (it takes time to accumulate) and *slow to reset* (it keeps firing long after the problem is fixed, because the hour-long average is still elevated).
- The **short window** (5 min) makes the alert *fast to fire* and, crucially, *fast to reset*: once the problem is fixed, the 5-minute average drops in 5 minutes, so the alert clears promptly instead of paging you for an hour after you've already fixed it.

So the long window provides precision (this is a real budget threat, not a blip), and the short window provides responsiveness (fire fast, clear fast). Requiring *both* is what gives you a page that's neither a false alarm nor a stuck alert. The PromQL is a recording rule per window (Week 17 §1.5 — precompute the per-window error ratios) and an alert that ANDs them:

```yaml
# A fast-burn page: 14.4x over 1h AND 14.4x over 5m must BOTH hold.
- alert: CartErrorBudgetFastBurn
  expr: |
    (
      cart:error_ratio:1h / (1 - 0.999) > 14.4
    )
    and
    (
      cart:error_ratio:5m / (1 - 0.999) > 14.4
    )
  labels: { severity: page }
  annotations:
    summary: "cart is burning its error budget 14.4x (fast burn) — ~2 days to exhaustion"
```

The recording rules (`cart:error_ratio:1h`, `cart:error_ratio:5m`) are precomputed exactly as in Week 17, both because the live expression is expensive and because you want the *same* numbers feeding the alert and the dashboard. This is the concrete reason last week taught recording rules: the burn-rate alert is their first real customer.

### 3.3.5 Choosing the windows and reading budget recovery

Two practical points operators ask about the moment they deploy these alerts.

**Where do 14.4 and 6 and 3 come from?** They're chosen so each alert, *if sustained*, consumes a meaningful, named fraction of the budget over its window — they're not magic. 14.4× over 1 hour burns 2% of a 28-day budget in that hour (1 hour is 1/672 of 28 days; 14.4 × 1/672 ≈ 2%). A page at "2% of the month's budget in one hour" is a genuine emergency. 6× over 6 hours burns ~5%; 3× over a day burns ~10%. The pattern is "page when a *short* burst would, if it continued, eat a *scary* fraction fast; ticket when a *slow* burn would eat a *concerning* fraction over days." You can tune the exact multipliers to your budget and risk tolerance, but the *structure* — fast/high pages, slow/low tickets, both as a fraction-of-budget — is the durable part.

**How do you know when it's over?** The SLI is a *rolling* window, so the budget *recovers* on its own as the bad period ages out of the 28-day window — you don't "refill" it manually. This matters for the error-budget policy (§2.2): after an incident burns budget, the team isn't frozen forever; the budget heals as the rolling window moves past the incident, and the freeze lifts when the SLI climbs back above target. A useful companion metric is **budget remaining** — `1 − (error events in window) / (allowed error events)` — which you graph alongside the burn rate so the team can *see* how much runway is left and how fast it's recovering. "We have 35% of the budget left and it's recovering" is a calmer on-call posture than staring at a binary alert; the budget-remaining graph turns reliability into a fuel gauge.

### 3.4 Alerting on the symptom, not the cause

A principle that ties the burn-rate approach together: **alert on the SLO (the user-facing symptom), not on every internal cause.** The old way pages on "CPU > 80%," "disk 90% full," "pod restarted" — dozens of cause-based alerts, most of which don't actually hurt a user, all of which page someone. The SLO way pages on *one thing*: "we're burning the error budget too fast." High CPU that *isn't* hurting the SLI is not an emergency; it's a capacity ticket. A pod restart that the system absorbed with zero user impact is not a page. By alerting on the budget burn — the actual user-facing symptom — you page only when users are actually being harmed fast enough to matter, which is the cure for alert fatigue. (You still *monitor* the causes; you just don't *page* on them. Causes go on dashboards and into the trace you jump to *after* the SLO alert fires — the Week 17 trace-to-log jump is what you do *after* the burn-rate page.)

---

### 3.5 The full alert set, as you'd actually deploy it

To make this concrete, here is the complete picture an on-call team runs — the recording rules that precompute every window's error ratio, and the four alerts (two page, two ticket) that watch them. This is the artifact Exercise 1 has you build and `promtool`-check:

```yaml
# recording rules: one per window, precomputed (Week 17 §1.5). Cheap + consistent.
groups:
  - name: cart-slo-windows
    interval: 30s
    rules:
      - record: cart:error_ratio:5m
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[5m]))
               / sum(rate(http_server_requests_total{service="cart"}[5m])))
      - record: cart:error_ratio:30m
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[30m]))
               / sum(rate(http_server_requests_total{service="cart"}[30m])))
      - record: cart:error_ratio:1h
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[1h]))
               / sum(rate(http_server_requests_total{service="cart"}[1h])))
      - record: cart:error_ratio:6h
        expr: |
          1 - (sum(rate(http_server_requests_total{service="cart",code!~"5.."}[6h]))
               / sum(rate(http_server_requests_total{service="cart"}[6h])))
```

```yaml
# the four-alert ladder (SLO = 0.999, budget = 0.001):
groups:
  - name: cart-slo-burn
    rules:
      # PAGE: 14.4x over 1h AND 5m -> ~2% of budget/hour -> exhausts in ~2 days
      - alert: CartBudgetFastBurn
        expr: (cart:error_ratio:1h / 0.001 > 14.4) and (cart:error_ratio:5m / 0.001 > 14.4)
        labels: { severity: page }
      # PAGE: 6x over 6h AND 30m -> ~5% of budget/6h
      - alert: CartBudgetMediumBurn
        expr: (cart:error_ratio:6h / 0.001 > 6) and (cart:error_ratio:30m / 0.001 > 6)
        labels: { severity: page }
      # TICKET: 3x over 24h AND 2h (recording rules for those windows omitted for brevity)
      - alert: CartBudgetSlowBurn
        expr: (cart:error_ratio:6h / 0.001 > 3) and (cart:error_ratio:30m / 0.001 > 3)
        labels: { severity: ticket }
```

Read the ladder top to bottom: the fastest, highest-burn condition pages immediately; progressively slower, lower-burn conditions either page (medium) or ticket (slow). A single incident may trip several rungs as it develops — that's fine; the routing (Alertmanager) deduplicates so you get one page, not four. The discipline this encodes: **the urgency of your response should match how fast the budget is actually draining**, and the ladder makes that automatic instead of a judgment call at 3 a.m.

## 4. Defending the SLO: why 100% is the wrong target

### 4.1 The cost curve and the weakest link

When product says "make it 100% reliable," the answer is not "yes." It's the §2.1 table: each nine costs exponentially more, and **100% is unattainable and not even desirable.** Two arguments:

- **The cost curve.** Going from 99.9% to 99.99% might 10× your infrastructure and on-call cost for a 9× smaller budget that users *cannot perceive* — nobody notices the difference between 43 minutes and 4 minutes of monthly downtime on a shopping cart, but the bill and the burnout are real. The marginal nine has to be *worth* its cost, and past a point it never is.
- **The weakest link.** Your service's reliability is *capped by its dependencies*. If cart depends on payment (99.9%) and inventory (99.9%) and the network (99.95%), cart *cannot* be more reliable than the product of those — roughly 99.75% — no matter how perfect cart's own code is. Promising 99.99% for a service sitting on 99.9% dependencies is promising something physically impossible. The SLO must account for the chain.

### 4.2 The error budget as the negotiation tool

This is the lecture's title made operational. When product wants more features faster and SRE wants more stability, the *old* fight is endless and political. The error budget *ends the fight* by making it quantitative: 

- **Budget left** → product wins the argument: "ship it, we have budget for the risk."
- **Budget spent** → SRE wins the argument, automatically, by the pre-signed error-budget policy: "we're out of budget; per the policy we stabilize until it recovers."

Neither side is appealing to opinion or authority; both are reading the same number. That's why "SLOs are a negotiation tool, not a ceiling" is the lecture's banner: the SLO doesn't just *measure* reliability, it *governs the conversation* about reliability, replacing the loudest voice with shared data. The senior skill is walking into the room with the budget number and the policy, so the decision is already made by the framework you all agreed to — not relitigated under pressure every sprint.

> **The trap to avoid:** setting the SLO so high (e.g. 99.99% on a service that genuinely needs 99.9%) that the budget is *always* effectively zero, so the team is *always* in stabilize mode and never ships. An over-tight SLO is as dysfunctional as no SLO — it just fails in the opposite direction (paralysis instead of recklessness). The SLO must be set to what the business *actually needs*, which is usually lower than the first instinct, so there's real budget to spend on velocity. Calibrating the SLO to genuine user need — not to a vanity number of nines — is itself a senior judgment.

---

## 4.3 SLI/SLO anti-patterns to avoid

A checklist of the ways teams get this wrong, so you can spot them in a review:

- **The vanity SLO.** Picking a number of nines because it sounds impressive, not because users need it or dependencies can support it. Always-zero budget, permanent freeze.

- **The unmeasurable SLI.** An SLO with no PromQL behind it — "the system should be fast" — which can't be evaluated, alerted on, or defended. An SLI you can't query isn't an SLI; it's an aspiration.

- **The mean-based SLI.** "Average latency < 200 ms" hides the tail (Lecture 2 §3.3) — half your users could be miserable while the average looks fine. SLIs are about the *distribution* (a percentile or a good-events ratio), never the mean.

- **The cause-based alert masquerading as an SLO.** "CPU < 80%" is a cause, not a user-facing symptom; alerting on it pages you for non-problems and misses real ones. Alert on the budget burn (§3.4).

- **The SLO nobody agreed to.** An SLO engineering set unilaterally, with no error-budget policy product signed. When the budget is spent, the freeze gets relitigated under pressure and the SLO becomes decorative. The policy must be pre-negotiated.

- **The forever-burning budget with no recovery.** Treating a spent budget as a permanent state instead of a rolling window that heals (§3.3.5). The budget recovers as the bad period ages out; the policy lifts when it does.

- **Counting the client's mistakes.** A denominator that includes 4xx-from-malformed-input flagellates you for serving exactly the error you should (§1.4). Specify the valid-events set precisely.

- **One SLI for everything.** A single availability SLI with no latency or correctness companion has blind spots (§1.2) — fast-but-wrong and up-but-slow both score perfectly. Cover the dimensions users actually feel.

- **The SLO measured over the wrong window.** A 1-hour window is too jumpy to be a contract and too short to spend a budget against; a 90-day window is too slow to act on. The 28-day rolling window is the default for a reason — actionable but not noisy.

Spotting any of these in a design review — and naming the fix — is the senior-SRE literacy this lecture builds. Most "our SLOs don't work" complaints trace to one of these seven.

## 5. Recap

You should now be able to:

- Define an SLI as good-events / valid-events, build availability and latency SLIs in PromQL (the latency one riding last week's SLO-aligned buckets), and choose the SLI(s) that reflect real user pain — including the app-level correctness SLI the mesh can't provide.
- Set an SLO over a window and compute the error budget as time and as events, and read the nines-cost-curve table.
- Treat the error budget as a spendable resource, governed by a pre-signed error-budget policy that takes the reliability-vs-velocity decision out of the meeting and hands it to the data.
- Distinguish SLI / SLO / SLA and keep the SLO stricter than the SLA.
- Derive multi-window multi-burn-rate alerting from first principles: burn rate as budget-spend-speed, the fast-burn page vs slow-burn ticket, and the long-window-AND-short-window trick for precision + responsiveness.
- Defend the SLO against "make it 100%": the exponential cost of each nine, the weakest-dependency cap, and the error budget as the tool that turns the reliability argument into shared arithmetic.

Next: the patterns that *keep* the system inside the budget — circuit breakers, bulkheads, timeouts, retries with jitter, backpressure, load shedding, autoscaling — and the capacity math (Little's law, the USL) that tells you where the system saturates. Continue to [Lecture 2 — Resilience Patterns, Autoscaling, and the Saturation Point](./02-resilience-patterns-autoscaling-and-the-saturation-point.md).

---

## References

- *Google SRE Book — Service Level Objectives*: <https://sre.google/sre-book/service-level-objectives/>
- *Google SRE Workbook — Implementing SLOs*: <https://sre.google/workbook/implementing-slos/>
- *Google SRE Workbook — Alerting on SLOs*: <https://sre.google/workbook/alerting-on-slos/>
- *Google SRE Book — Embracing Risk (error budgets)*: <https://sre.google/sre-book/embracing-risk/>
- *Google SRE Workbook — Error Budget Policy*: <https://sre.google/workbook/error-budget-policy/>
- *Sloth — Prometheus SLO generator*: <https://sloth.dev/>
