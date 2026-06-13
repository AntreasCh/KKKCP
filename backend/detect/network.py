"""Network detectors — REQUIREMENTS.md §9 (#4 fan-in/out, #5 Louvain communities).
Owner: P3 (Andreas).

#4 fan now uses a TEMPORAL WINDOW: a mule hub gathers/spreads to many counterparties in a
short burst, whereas a legit account accumulates the same degree spread over weeks. Emitting
the hub as the subject (counterparties in evidence) concentrates risk on the hub, not the spokes.

#5 community detection is kept as low-weight context only — ring assembly happens in
scoring.build_rings from the flagged-account subgraph (see scoring.py), which is effectively
community detection on the *risky* subgraph.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import networkx as nx

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ts(s: str) -> datetime:
    return datetime.strptime(s, TS_FMT)


def _max_window_counterparties(events, window_hours: int):
    """events: list of (datetime, counterparty). Return the largest set of distinct
    counterparties seen within any window of `window_hours`."""
    events = sorted(events, key=lambda e: e[0])
    win = timedelta(hours=window_hours)
    best: set[str] = set()
    n = len(events)
    for i in range(n):
        cps = set()
        for j in range(i, n):
            if events[j][0] - events[i][0] <= win:
                cps.add(events[j][1])
            else:
                break
        if len(cps) > len(best):
            best = cps
    return best


def _legit_hub_factor(acc_rec: dict | None) -> float:
    """Legit high-degree accounts (payroll / merchants / utilities) are ESTABLISHED BUSINESS
    accounts with LOW KYC risk; mule hubs are fresh PERSONAL accounts with elevated KYC. Return
    a multiplier <= 1 that suppresses the fan score for the legit-hub profile, so a payroll
    fan-out stops masquerading as a mule ring. Unknown account → no change (1.0)."""
    if not acc_rec:
        return 1.0
    f = 1.0
    if acc_rec.get("account_type") == "business":
        f *= 0.35          # a business legitimately pays/collects from many counterparties
    kyc = acc_rec.get("kyc_risk")
    if kyc == "low":
        f *= 0.5
    elif kyc == "high":
        f *= 1.1           # elevated KYC risk → lean in
    return min(1.0, f)


def detect_fan(graph, accounts, transactions, fan: int = 5, window_hours: int = 48) -> list[dict]:
    """#4: a hub with >= `fan` distinct counterparties within a `window_hours` burst. The score
    is down-weighted for legit-hub account profiles (see _legit_hub_factor) so established
    businesses (payroll/merchants) stop flagging while fresh personal mule hubs still do."""
    acc_by_id = {a["account_id"]: a for a in (accounts or [])}
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for t in transactions:
        ts = _ts(t["timestamp"])
        incoming[t["dst"]].append((ts, t["src"]))
        outgoing[t["src"]].append((ts, t["dst"]))

    findings = []
    for acc, events in incoming.items():
        cps = _max_window_counterparties(events, window_hours)
        if len(cps) >= fan:
            factor = _legit_hub_factor(acc_by_id.get(acc))
            findings.append({"detector": "fan_in", "subject_type": "account",
                             "subject_ids": [acc], "score": round(min(1.0, 0.4 + 0.05 * len(cps)) * factor, 2),
                             "evidence": {"hub": acc, "in_degree_window": len(cps),
                                          "window_hours": window_hours, "legit_hub_factor": round(factor, 2),
                                          "counterparties": sorted(cps)}})
    for acc, events in outgoing.items():
        cps = _max_window_counterparties(events, window_hours)
        if len(cps) >= fan:
            factor = _legit_hub_factor(acc_by_id.get(acc))
            findings.append({"detector": "fan_out", "subject_type": "account",
                             "subject_ids": [acc], "score": round(min(1.0, 0.4 + 0.05 * len(cps)) * factor, 2),
                             "evidence": {"hub": acc, "out_degree_window": len(cps),
                                          "window_hours": window_hours, "legit_hub_factor": round(factor, 2),
                                          "counterparties": sorted(cps)}})
    return findings


def detect_communities(graph, accounts, transactions) -> list[dict]:
    """#5: Louvain communities — kept as LOW-WEIGHT context. Real ring assembly is in
    scoring.build_rings (flagged-account subgraph). Returns small dense communities only."""
    findings = []
    try:
        import community as community_louvain  # python-louvain
    except Exception:
        return findings
    weights = defaultdict(float)
    for t in transactions:
        a, b = sorted((t["src"], t["dst"]))
        weights[(a, b)] += float(t["amount"])
    ug = nx.Graph()
    for (a, b), amt in weights.items():
        ug.add_edge(a, b, weight=amt)
    if ug.number_of_nodes() == 0:
        return findings
    part = community_louvain.best_partition(ug, random_state=42)  # deterministic for the demo
    comms = defaultdict(list)
    for node, c in part.items():
        comms[c].append(node)
    for nodes in comms.values():
        if 3 <= len(nodes) <= 12:
            sub = ug.subgraph(nodes)
            density = nx.density(sub) if len(nodes) > 1 else 0.0
            if density >= 0.5:  # only genuinely dense little clusters
                findings.append({"detector": "community", "subject_type": "subgraph",
                                 "subject_ids": sorted(nodes), "score": round(min(1.0, density), 2),
                                 "evidence": {"size": len(nodes), "density": round(density, 3)}})
    return findings
