"""Network detectors — REQUIREMENTS.md §9 (#4 fan-in/out, #5 Louvain communities).
Owner: P3.

FUNCTIONAL PLACEHOLDERS. TODO(P3): add temporal windows to fan detection (legit
high-degree accounts shouldn't flag), and score communities by flagged-account density
rather than raw graph density.
"""
from __future__ import annotations

from collections import defaultdict

import networkx as nx


def detect_fan(graph, accounts, transactions, fan: int = 6) -> list[dict]:
    """#4: hubs with many distinct senders (fan-in) or recipients (fan-out)."""
    findings = []
    receivers, senders = defaultdict(set), defaultdict(set)
    for t in transactions:
        receivers[t["dst"]].add(t["src"])
        senders[t["src"]].add(t["dst"])
    for acc, srcs in receivers.items():
        if len(srcs) >= fan:
            findings.append({"detector": "fan_in", "subject_type": "subgraph",
                             "subject_ids": [acc] + sorted(srcs),
                             "score": round(min(1.0, 0.3 + 0.05 * len(srcs)), 2),
                             "evidence": {"hub": acc, "in_degree": len(srcs)}})
    for acc, dsts in senders.items():
        if len(dsts) >= fan:
            findings.append({"detector": "fan_out", "subject_type": "subgraph",
                             "subject_ids": [acc] + sorted(dsts),
                             "score": round(min(1.0, 0.3 + 0.05 * len(dsts)), 2),
                             "evidence": {"hub": acc, "out_degree": len(dsts)}})
    return findings


def detect_communities(graph, accounts, transactions) -> list[dict]:
    """#5: Louvain communities on the weighted undirected projection → ring candidates."""
    findings = []
    try:
        import community as community_louvain  # python-louvain
    except Exception:
        return findings  # not installed yet — P3 wires this; pipeline still runs
    weights = defaultdict(float)
    for t in transactions:
        a, b = sorted((t["src"], t["dst"]))
        weights[(a, b)] += float(t["amount"])
    ug = nx.Graph()
    for (a, b), amt in weights.items():
        ug.add_edge(a, b, weight=amt)
    if ug.number_of_nodes() == 0:
        return findings
    part = community_louvain.best_partition(ug)
    comms = defaultdict(list)
    for node, c in part.items():
        comms[c].append(node)
    for nodes in comms.values():
        if 3 <= len(nodes) <= 15:
            sub = ug.subgraph(nodes)
            density = nx.density(sub) if len(nodes) > 1 else 0.0
            findings.append({"detector": "community", "subject_type": "subgraph",
                             "subject_ids": sorted(nodes), "score": round(min(1.0, density), 2),
                             "evidence": {"size": len(nodes), "density": round(density, 3)}})
    return findings
