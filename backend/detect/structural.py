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


CIRC_WINDOW_H = 72        # whole loop must close within this many hours
CIRC_MIN_RETENTION = 0.8  # money returning to origin / money that left it (§9 #2)
CIRC_MAX_RETENTION = 1.25  # laundering skims value; it doesn't grow. Above this = coincidence.


def _trace_money_loop(cyc, tx_by_pair):
    """Given a node cycle [n0, n1, ... nk-1] (edges n0->n1, ..., n_{k-1}->n0), try to
    pick ONE real transaction per hop so that timestamps strictly increase around the
    loop and the whole thing closes within the window. Returns the winning chain or None.

    Why this matters: `nx.simple_cycles` finds cycles in the *topology* — it doesn't know
    when money moved. Three unrelated payments can form a triangle by accident. Real
    laundering is a chain *in time*: A pays B, THEN B pays C, THEN C pays back A. So we
    look for an ordering of actual transactions whose timestamps go forward, hop by hop.
    """
    k = len(cyc)
    # candidate transactions on each directed hop, earliest first
    hops = []
    for i in range(k):
        src, dst = cyc[i], cyc[(i + 1) % k]
        cands = sorted(tx_by_pair.get((src, dst), []), key=lambda t: _ts(t["timestamp"]))
        if not cands:
            return None  # a hop has no real transaction → not a money loop at all
        hops.append(cands)

    # The cycle networkx gives us can start at any node, but a real loop has a definite
    # starting hop (where the money first leaves). Try every rotation as the start.
    for start in range(k):
        order = [hops[(start + i) % k] for i in range(k)]
        chain, prev_ts, ok = [], None, True
        for cands in order:
            pick = next((t for t in cands if prev_ts is None
                         or _ts(t["timestamp"]) > prev_ts), None)
            if pick is None:        # nothing on this hop happens after the previous hop
                ok = False
                break
            chain.append(pick)
            prev_ts = _ts(pick["timestamp"])
        if not ok:
            continue
        span = _ts(chain[-1]["timestamp"]) - _ts(chain[0]["timestamp"])
        if span > timedelta(hours=CIRC_WINDOW_H):
            continue                # loop took too long → probably coincidence
        out0 = chain[0]["amount"]   # money that LEFT the origin on the first hop
        back = chain[-1]["amount"]  # money that RETURNED to the origin on the last hop
        retention = back / out0 if out0 else 0.0
        if not (CIRC_MIN_RETENTION <= retention <= CIRC_MAX_RETENTION):
            continue                # too much leaked, or grew → not the same money looping
        return chain, span, retention
    return None


def detect_circular(graph, accounts, transactions) -> list[dict]:
    """#2 Circular flow: money leaves an account and loops back to it through a short
    chain, keeping most of its value, within 72h. We flag the cycle ONLY when a real
    sequence of transactions proves the loop happened in time with the value retained —
    not just because the accounts form a topological cycle. Score = retention × tightness.
    """
    # one directed edge per (src,dst) for cycle topology; keep the real txs for the proof
    dg = nx.DiGraph()
    tx_by_pair = defaultdict(list)
    for t in transactions:
        dg.add_edge(t["src"], t["dst"])
        tx_by_pair[(t["src"], t["dst"])].append(t)

    findings, seen = [], set()
    try:
        gen = nx.simple_cycles(dg, length_bound=5)  # §9 #2: cycles of length 2–5
        cycles = list(itertools.islice(gen, 0, 2000))
    except Exception:
        cycles = []

    for cyc in cycles:
        if len(cyc) < 3:
            continue  # 2-cycles are reciprocal payments, not laundering loops (need a relay)
        key = frozenset(cyc)
        if key in seen:
            continue
        proof = _trace_money_loop(cyc, tx_by_pair)
        if proof is None:
            continue  # topological cycle with no time-ordered, value-retaining money loop
        seen.add(key)
        chain, span, retention = proof
        hours = span.total_seconds() / 3600
        tightness = 1.0 - min(1.0, hours / CIRC_WINDOW_H)  # faster loop = more suspicious
        score = round(min(1.0, 0.5 * retention + 0.5 * tightness), 2)
        findings.append({
            "detector": "circular", "subject_type": "subgraph",
            "subject_ids": list(cyc), "score": score,
            "evidence": {
                "cycle": list(cyc), "length": len(cyc),
                "retention": round(retention, 2), "hours": round(hours, 1),
                "tx_ids": [t["tx_id"] for t in chain],
            },
            "window": {"start": chain[0]["timestamp"], "end": chain[-1]["timestamp"]},
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
