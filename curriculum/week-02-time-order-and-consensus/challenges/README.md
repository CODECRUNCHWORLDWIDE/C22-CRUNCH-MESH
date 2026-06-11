# Week 2 — Challenges

The exercises drill the mechanics. **The challenge makes you the operator.** You stand up a real Raft-backed coordination service, break it on purpose, and document how it heals — the way you'll actually meet consensus in production: not as a paper, but as a cluster that just lost a node at 3 a.m.

## Index

1. **[Challenge 1 — Operate a 3-node etcd cluster](challenge-01-operate-an-etcd-cluster.md)** — stand up a 3-node etcd cluster on Kind, find the leader, kill it, watch the election and failover, observe that the cluster stays available (it kept a majority), then kill a second node and watch it lose quorum and stop accepting writes. Document each transition with `etcdctl` output. (~90 min)

Challenges are optional for passing the week, but this one is the single best preparation for the **capstone's region-failover chaos drill** (Drill A), where you kill a whole region and document the recovery. Running etcd through elections by hand is the rehearsal. The skill — reading `etcd_server_leader_changes_seen_total` and `endpoint status` to know exactly what your consensus layer is doing during a failure — is what separates an engineer who "knows Raft" from one who can keep a coordination service alive during an incident.
