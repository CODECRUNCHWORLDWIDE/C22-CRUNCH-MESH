# Week 6 — Challenges

The exercises drill each hardening technique in isolation. **The challenge makes you the reviewer.** You're handed a service that "works on the developer's laptop" and asked to take it through a real production-readiness review — find every gap, fix it, and *prove* the service is now production-grade against a checklist, ending with the zero-dropped-requests-on-deploy demonstration.

## Index

1. **[Challenge 1 — Pass the production-readiness review](challenge-01-pass-the-readiness-review.md)** — take a deliberately un-hardened service from "runs" to "passes a readiness review": close every gap (logs, probes, shutdown, limits, tracing, secrets, runbook) and demonstrate a rolling deploy under load that drops zero requests. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the Phase 1 architecture review in Week 12, where you defend that your `cart` system is production-ready — and for the capstone, which is graded partly on operability. The skill — looking at a running service and naming, against a checklist, exactly what would page someone and why — is what separates an engineer who "ships features" from one who ships features the team can run without them. The zero-drop deploy demonstration is the proof that you didn't just check boxes; you made the service genuinely safe to deploy.
