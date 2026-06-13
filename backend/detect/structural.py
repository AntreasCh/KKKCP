"""Structural detectors — REQUIREMENTS.md §9 (#1 structuring, #2 circular, #3 pass-through).
Owner: P2.

These are FUNCTIONAL PLACEHOLDERS so the pipeline runs end-to-end today. Each returns
valid Findings (schemas.py §7). TODO(P2): tune thresholds and use timestamps/amounts to
cut false positives — measure against the eval harness (§12).
"""
from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import datetime, timedelta

import networkx as nx

from backend.schemas import REPORTING_THRESHOLD as T

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ts(s: str) -> datetime:
    return datetime.strptime(s, TS_FMT)


def detect_structuring(graph, accounts, transactions) -> list[dict]:
    """#1: many sub-threshold deposits into one account within 72h summing >= T."""
    findings = []
    incoming = defaultdict(list)
    for t in transactions:
        if 0.7 * T <= t["amount"] < T:
            incoming[t["dst"]].append(t)
    for acc, txs in incoming.items():
        if len(txs) < 3:
            continue
        txs.sort(key=lambda t: _ts(t["timestamp"]))
        for i in range(len(txs)):
            window = [txs[i]]
            for j in range(i + 1, len(txs)):
                if _ts(txs[j]["timestamp"]) - _ts(txs[i]["timestamp"]) <= timedelta(hours=72):
                    window.append(txs[j])
            total = sum(t["amount"] for t in window)
            if len(window) >= 3 and total >= T:
                findings.append({
                    "detector": "structuring", "subject_type": "account",
                    "subject_ids": [acc], "score": round(min(1.0, 0.4 + 0.1 * len(window)), 2),
                    "evidence": {"count": len(window), "total": round(total, 2), "threshold": T},
                    "window": {"start": window[0]["timestamp"], "end": window[-1]["timestamp"]},
                })
                break
    return findings


def detect_circular(graph, accounts, transactions) -> list[dict]:
    """#2: directed cycles of length 2–4 (money returns toward origin).
    TODO(P2): require increasing timestamps + amount retention around the loop."""
    dg = nx.DiGraph()
    for t in transactions:
        dg.add_edge(t["src"], t["dst"])
    findings, seen = [], set()
    try:
        gen = nx.simple_cycles(dg, length_bound=4)
        cycles = list(itertools.islice(gen, 0, 500))
    except Exception:
        cycles = []
    for cyc in cycles:
        if len(cyc) < 2:
            continue
        key = frozenset(cyc)
        if key in seen:
            continue
        seen.add(key)
        findings.append({
            "detector": "circular", "subject_type": "subgraph",
            "subject_ids": list(cyc), "score": 0.7,
            "evidence": {"cycle": list(cyc), "length": len(cyc)},
        })
    return findings


def detect_passthrough(graph, accounts, transactions) -> list[dict]:
    """#3: account receives X then forwards >=0.8X within 24h (mule relay / layering)."""
    findings = []
    ins, outs = defaultdict(list), defaultdict(list)
    for t in transactions:
        ins[t["dst"]].append(t)
        outs[t["src"]].append(t)
    for acc in set(ins) | set(outs):
        hit = None
        for ti in ins.get(acc, []):
            if ti["amount"] < 5000:
                continue
            for to in outs.get(acc, []):
                dt = _ts(to["timestamp"]) - _ts(ti["timestamp"])
                if timedelta(0) <= dt <= timedelta(hours=24) and to["amount"] >= 0.8 * ti["amount"] and to["dst"] != ti["src"]:
                    hit = (ti, to, dt)
                    break
            if hit:
                break
        if hit:
            ti, to, dt = hit
            findings.append({
                "detector": "passthrough", "subject_type": "account",
                "subject_ids": [acc], "score": 0.6,
                "evidence": {"in": round(ti["amount"], 2), "out": round(to["amount"], 2),
                             "hours": round(dt.total_seconds() / 3600, 1)},
                "window": {"start": ti["timestamp"], "end": to["timestamp"]},
            })
    return findings
