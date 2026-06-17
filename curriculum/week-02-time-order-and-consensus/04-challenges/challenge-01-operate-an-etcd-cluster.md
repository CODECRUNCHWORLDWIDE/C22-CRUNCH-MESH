# Challenge 1 — Operate a 3-Node etcd Cluster

**Time estimate:** ~90 minutes.

## Problem statement

You will stand up a real 3-node etcd cluster on a local Kind cluster, then exercise its Raft consensus by killing nodes and watching it elect leaders and (eventually) lose quorum. The goal is to *see* the Week 2 theory happen: terms incrementing, leaders changing on a majority vote, the cluster staying available with 2 of 3 nodes, and going write-unavailable when only 1 of 3 remains. You will document each transition with `etcdctl` output, the way you would in a real incident report.

This rehearses the capstone's region-failover drill in miniature: kill the thing that holds the cluster together and document — with metrics, not vibes — exactly what happened and when service was restored.

## Setup

You need: Docker/Podman, Kind, kubectl, and `etcdctl`. Install Kind and create a cluster:

```bash
kind create cluster --name mesh-w2
kubectl cluster-info --context kind-mesh-w2
```

Deploy a 3-node etcd. The simplest path is the Bitnami etcd Helm chart with 3 replicas, or a 3-replica StatefulSet. A minimal StatefulSet approach:

```bash
# Using the bitnami chart (clusterDomain + 3 replicas, no auth for a lab):
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install etcd bitnami/etcd \
  --set replicaCount=3 \
  --set auth.rbac.create=false \
  --set persistence.enabled=false
kubectl get pods -l app.kubernetes.io/name=etcd -w   # wait for 3/3 Running
```

(If the chart's defaults change, any reliable 3-node etcd on Kind is acceptable — the exercise is about operating it, not the install method. Document whatever you used.)

Get a shell with `etcdctl` available (either `kubectl exec` into an etcd pod, or run a client pod):

```bash
kubectl exec -it etcd-0 -- bash
# inside, set the endpoints to all three members:
export ENDPOINTS=etcd-0.etcd-headless:2379,etcd-1.etcd-headless:2379,etcd-2.etcd-headless:2379
```

## Part A — Find the leader and baseline the cluster

```bash
etcdctl --endpoints=$ENDPOINTS endpoint status --write-out=table
etcdctl --endpoints=$ENDPOINTS member list --write-out=table
```

Record: which member is the leader (`IS LEADER` column), the current **Raft term**, and the **Raft index**. Write a value and read it back to confirm the cluster works:

```bash
etcdctl --endpoints=$ENDPOINTS put /mesh/canary "alive-$(date +%s)"
etcdctl --endpoints=$ENDPOINTS get /mesh/canary
```

## Part B — Kill the leader, watch the election

Delete the leader pod (say it's `etcd-1`):

```bash
kubectl delete pod etcd-1      # kill the current leader
```

Immediately and repeatedly run `endpoint status` against the *surviving* endpoints:

```bash
etcdctl --endpoints=etcd-0.etcd-headless:2379,etcd-2.etcd-headless:2379 \
  endpoint status --write-out=table
```

Record: the **new leader**, the **new (higher) Raft term**, and confirm the cluster **still accepts writes** (it has 2 of 3 = a majority):

```bash
etcdctl --endpoints=etcd-0.etcd-headless:2379,etcd-2.etcd-headless:2379 \
  put /mesh/canary "after-failover-$(date +%s)"   # should SUCCEED
```

This is the CP-but-available case: one node lost, majority intact, service continues. The term incremented because an election happened — that is the Lecture 1 logical clock and the Lecture 2 election in action.

## Part C — Kill a second node, watch quorum loss

Now delete a *second* node so only one remains (this loses the majority):

```bash
kubectl delete pod etcd-0      # now only etcd-2 (or one node) remains briefly
```

Against the single survivor, try a write:

```bash
etcdctl --endpoints=etcd-2.etcd-headless:2379 \
  put /mesh/canary "should-fail-$(date +%s)"
```

Record what happens. With only 1 of 3 nodes, there is **no majority**, so the cluster **cannot commit** — the write should **fail or hang/timeout** (`context deadline exceeded` or a leader-election error). This is the CP choice: rather than accept a write it cannot safely replicate, etcd refuses. **It sacrifices availability to preserve consistency** — exactly Week 1's CAP, in your terminal.

## Part D — Heal and confirm recovery

Let Kubernetes reschedule the deleted pods (StatefulSets recreate them). Watch them rejoin:

```bash
kubectl get pods -l app.kubernetes.io/name=etcd -w
etcdctl --endpoints=$ENDPOINTS endpoint status --write-out=table   # all 3 back
etcdctl --endpoints=$ENDPOINTS put /mesh/canary "recovered-$(date +%s)"  # SUCCEEDS
etcdctl --endpoints=$ENDPOINTS get /mesh/canary
```

Confirm: quorum restored, writes accepted again, and the value you wrote in Part B (`after-failover`) survived the whole ordeal (it was committed on a majority before the second kill).

## The writeup (the deliverable)

Write `challenge-01-failover-report.md` documenting the timeline, structured like an incident report:

1. **Baseline** — initial leader, term, member list (paste the `endpoint status` table).
2. **Failover (Part B)** — leader killed, new leader, new term, and proof the cluster stayed available.
3. **Quorum loss (Part C)** — second node killed, the failed write, and the exact error. Explain *why* 1 of 3 cannot make progress.
4. **Recovery (Part D)** — quorum restored, writes resume, no data lost.
5. **The CAP/Raft mapping** — one paragraph connecting what you observed to Week 1 (CP: minority refuses) and Week 2 (term = logical clock; majority = quorum; election restriction kept the committed value safe).

## Acceptance criteria

- [ ] A 3-node etcd cluster ran on Kind; `member list` showed 3 members.
- [ ] `challenge-01-failover-report.md` contains the five sections with **real `etcdctl` output** pasted in (tables, not paraphrase).
- [ ] Part B shows the Raft **term incremented** and a **new leader** after the kill, with a successful write proving continued availability on a majority.
- [ ] Part C shows a write **failing/timing out** with only 1 of 3 nodes, and you explain the no-majority reason.
- [ ] Part D shows recovery and confirms the Part-B value survived.
- [ ] Committed to your Week 2 repo under `challenges/challenge-01/`.

## The trap (read after a first attempt)

The common mistake is killing nodes too fast and concluding "etcd is broken" when you've actually just removed the majority (Part C) — which is *correct* behavior, not a bug. etcd refusing writes with 1 of 3 nodes is the **CP choice working as designed**: it would rather be unavailable than risk a split-brain write that can't be safely committed. If you expected it to "keep working," re-read Week 1 — you were expecting AP behavior from a CP system. The whole point of the challenge is to *feel* the CP choice: the cluster chooses consistency (refuse) over availability (accept and risk divergence) the moment it loses quorum.

## Stretch

- Watch the metric directly: `etcdctl endpoint status` exposes the Raft term, but the Prometheus metric `etcd_server_leader_changes_seen_total` counts elections. Port-forward etcd's metrics endpoint and watch it climb each time you kill the leader.
- Use `etcdctl move-leader <member-id>` to **transfer leadership gracefully** (no election needed) and note the difference from a kill: a clean handoff vs an election timeout. Relate it to Lecture 2 §3.3b.
- Scale to **5 nodes** and confirm it now tolerates **2** failures (kill two, stay available; kill three, lose quorum). Prove the `2f+1` fault-tolerance formula on a running cluster.
- Run the cluster on **slow storage** (a throttled volume) and observe election churn — the disk-latency-is-consensus-latency lesson from Lecture 2, live.

## Why this matters

In the capstone, you kill an entire region during a 1k-RPS load test and document the recovery. The coordination layer (etcd, or whatever holds your cluster state) failing over is the load-bearing event of that drill. Running etcd through elections and a quorum loss *by hand* is the rehearsal — and the `etcdctl endpoint status` muscle you build here is exactly what you reach for when a real cluster loses a node and you have ninety seconds to know whether you still have a quorum.
