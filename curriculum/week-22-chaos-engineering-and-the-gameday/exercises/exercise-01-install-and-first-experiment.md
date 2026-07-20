# Exercise 1 — Install Chaos Mesh and Run Your First Hypothesis-Driven Experiment

**Goal:** Install Chaos Mesh on your Kind cluster, hold your `cart` service at a steady load, write a falsifiable hypothesis with a steady-state metric, inject a *scoped* `PodChaos`, and let the dashboard render the verdict. You will train the single most important chaos habit of the week: the hypothesis and the metric come *before* the fault, so the experiment can come back and tell you "no."

**Estimated time:** 75 minutes. Guided.

---

## Setup

You need `kubectl`, `helm`, a Kind cluster with your `cart` service (or a stand-in), and Prometheus + Grafana from Week 17.

```bash
kubectl get nodes            # Ready
kubectl get pods -n monitoring   # Prometheus + Grafana up (Week 17)
helm version                 # client present
```

**Fallback if your capstone `cart` isn't ready.** Deploy any 3-replica HTTP deployment with a Service and a `/metrics` endpoint (the Istio `httpbin` sample, or a tiny nginx with 3 replicas) labeled `app: cart`. Wherever this exercise says `cart`, substitute it. You just need something replicated, behind a Service, with an error/latency metric.

---

## Step 1 — Install Chaos Mesh

```bash
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update
kubectl create ns chaos-mesh
# Kind uses containerd; point the daemon at the right socket:
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock \
  --version 2.6.3
```

Confirm the control plane and the per-node daemon are up:

```bash
kubectl get pods -n chaos-mesh
# chaos-controller-manager-xxxxx   Running    <-- the brain
# chaos-daemon-xxxxx               Running    <-- one per node (DaemonSet); does the injecting
# chaos-dashboard-xxxxx            Running    <-- the UI
```

`chaos-daemon` as a DaemonSet (one per node) is the proof the data plane is in place — that's the privileged agent that enters target pods' namespaces to inject faults.

---

## Step 2 — Establish steady state

A chaos experiment needs a system *doing something*. Hold `cart` at a steady load and open its RED dashboard.

```bash
# Hold ~50 RPS against cart for the duration of the exercise:
kubectl run k6 --image=grafana/k6 -n shop --restart=Never -- \
  run - <<'EOF'
import http from 'k6/http'; import { sleep } from 'k6';
export const options = { vus: 4, duration: '15m' };
export default function () { http.get('http://cart.shop.svc.cluster.local:8080/'); sleep(0.08); }
EOF
```

Open Grafana and confirm your **steady-state metric** is live and in band. Identify it as a *specific query*:

```promql
# the steady-state SLI — error ratio over the cart Service:
sum(rate(cart_read_errors_total[1m])) / sum(rate(cart_read_total[1m]))
# baseline should sit ~0.001 (well under the 1% SLO).
```

If you can't see this number move in real time, **stop and fix observability first.** You cannot judge an experiment you can't measure.

---

## Step 3 — Write the hypothesis (before touching the cluster)

Write this down — in your repo, in `notes/week-22/exp-01.md` — *before* you inject anything:

> **Hypothesis:** "Killing one of the three `cart` pods keeps the cart error ratio below the 1% SLO and p99 below 200 ms, because the Service load-balances to the two survivors and the Deployment reschedules the killed pod within its readiness window."
> **Steady-state metric:** the error-ratio query above, plus the p99 histogram.
> **Abort condition:** error ratio > 5% sustained for 60 s.
> **Rollback:** `kubectl delete podchaos cart-pod-kill -n shop`; recovery = metric back to baseline.

The reason ("because the Service load-balances...") is load-bearing: if the hypothesis is refuted, the reason is the first thing that was wrong.

---

## Step 4 — Inject a scoped PodChaos

```yaml
# cart-pod-kill.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata: { name: cart-pod-kill, namespace: shop }
spec:
  action: pod-kill
  mode: one                       # BLAST RADIUS: exactly one pod
  selector:
    namespaces: [shop]
    labelSelectors: { app: cart }
  duration: "60s"                 # TIME-BOXED
```

```bash
kubectl apply -f cart-pod-kill.yaml
kubectl get pods -n shop -w
# one cart pod is killed; the Deployment schedules a replacement.
```

Watch the steady-state metric the *whole* time. Note the exact second the fault landed and the exact second the metric (if it moved) returned to baseline — that's the scribe's timeline.

---

## Step 5 — Render the verdict from the metric

The verdict is the dashboard, not your opinion:

```promql
# during the 60s fault, did the error ratio stay under 1%?
sum(rate(cart_read_errors_total[1m])) / sum(rate(cart_read_total[1m]))
```

- **HELD:** the ratio blipped (a few in-flight requests to the killed pod failed) but stayed under the SLO, and p99 stayed bounded. The hypothesis held — your replication delivers availability.
- **REFUTED:** the ratio crossed the SLO and stayed there — e.g., the Service kept routing to the dead pod (no readiness gate), or the replacement took traffic before it was ready, or `cart` wasn't actually replicated. **That refutation is a finding.** Write it up (it's homework Problem 1).

```bash
kubectl get podchaos -n shop
# NAME            ACTION     DURATION   ... STATUS
# cart-pod-kill   pod-kill   60s            Finished   <-- Chaos Mesh enforced the duration and stopped
```

---

## Step 6 — Roll back and confirm recovery

```bash
kubectl delete -f cart-pod-kill.yaml     # idempotent even after it Finished
kubectl get podchaos -n shop             # empty — no chaos left running
# confirm the metric is back at baseline and all three cart pods are Ready.
```

**"Recovered" means the metric is back in band and the pods are healthy — not just that the CRD is gone.** Record the recovery time in your timeline.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `kubectl get pods -n chaos-mesh` shows `chaos-controller-manager` and `chaos-daemon` (a DaemonSet) Running.
- [ ] You wrote the hypothesis, steady-state metric, and abort condition in `notes/week-22/exp-01.md` *before* injecting.
- [ ] The steady-state metric was live in Grafana during the entire experiment.
- [ ] The `PodChaos` was scoped (`mode: one`) and time-boxed (`duration: 60s`) — you did not kill all pods forever.
- [ ] You recorded the verdict (HELD or REFUTED) from the metric, with the timeline of when the fault landed and when the metric recovered.
- [ ] You deleted the chaos CRD and confirmed no chaos resources remain (`kubectl get podchaos -n shop` is empty) and the metric returned to baseline.

---

## Stretch

- Re-run with `mode: percent, value: "67"` to kill two of three pods. Re-state the hypothesis first (does availability survive losing the majority?), then test. This is how you widen blast radius *deliberately* after the small version held.
- Add a `Schedule` resource so the pod-kill fires every 10 minutes — the "continuous chaos" posture. Watch a day's worth and see if any run refutes the hypothesis (a regression you'd otherwise find in production).
- Wire a Prometheus alert on the abort condition (`error ratio > 5% for 60s`) and confirm it fires under a `percent: 100` kill — the dead-man's switch that makes production chaos safe.

---

When this feels comfortable, move to [Exercise 2 — The six canonical experiments](exercise-02-six-experiments.yaml).
