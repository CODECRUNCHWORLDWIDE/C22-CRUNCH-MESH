# Week 8 — Challenges

The exercises drill the mechanics. **The challenge makes you the on-call engineer.** A service that worked perfectly un-meshed is crash-looping the moment it joins the mesh, the app team swears their code didn't change, and "just remove the sidecar" makes it work — which tells you exactly nothing about how to keep the sidecar. You have to find the real cause from the outside, with `istioctl`, the way it always happens.

## Index

1. **[Challenge 1 — The sidecar that wouldn't start](./challenge-01-the-sidecar-that-wouldnt-start.md)** — a deployment that ran fine before meshing now crash-loops, because the app container makes a network call at startup before the sidecar Envoy is ready to proxy it. Using only `istioctl proxy-status`, `istioctl x describe`, the sidecar logs, and the pod events, you must (a) prove the failure is a sidecar startup-ordering race and not an app bug, (b) name the exact mechanism, and (c) fix it correctly — without disabling the mesh. (~90 min)

Challenges are optional for passing the week, but this one is the single most realistic Istio on-call scenario there is. The startup race is the number-one "my app broke when we meshed it" cause, and the tempting "fix" (remove the sidecar) throws away the entire reason you adopted the mesh. The engineer who can look at a crash-loop, run `istioctl x describe`, and say "the app is racing the proxy — set `holdApplicationUntilProxyStarts`" in five minutes is the one who makes a mesh rollout survivable instead of a revolt.
