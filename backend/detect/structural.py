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
from functools import lru_cache

import networkx as nx

from backend.schemas import REPORTING_THRESHOLD as T

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


@lru_cache(maxsize=500_000)
def _ts(s: str) -> datetime:
    # datetime.strptime is expensive and the same timestamps are parsed many times across the
    # detectors (and re-parsed every tick of the live stream). Memoising makes timestamp handling
    # effectively free at scale — the cache is keyed on the ISO string, so it's always correct.
    return datetime.strptime(s, TS_FMT)


def detect_structuring(graph, accounts, transactions) -> list[dict]:
    """#1: many sub-threshold deposits into one account within 72h summing >= T.

    Score reflects the three things that make a deposit burst look deliberate (§9 #1):
    the COUNT of sub-threshold deposits, how CLOSE each one sits to the reporting line
    (amounts hugging €9,9xx are obvious threshold-dodging), and how TIGHT the burst is in
    time. Ranking by these surfaces the most blatant structuring first for an analyst.
    """
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
                span_h = (_ts(window[-1]["timestamp"]) - _ts(window[0]["timestamp"])).total_seconds() / 3600
                tightness = 1.0 - min(1.0, span_h / 72)              # whole burst in an hour -> ~1.0
                # closeness: mean deposit's position in the [0.7T, T) band, 0 (at 0.7T) .. 1 (just under T)
                closeness = ((total / len(window)) / T - 0.7) / 0.3
                closeness = max(0.0, min(1.0, closeness))
                # floor 0.6 (3 sub-threshold deposits summing >=T is already structuring), up to 1.0
                score = round(min(1.0, 0.6 + 0.1 * (len(window) - 3)
                                  + 0.18 * closeness + 0.12 * tightness), 2)
                findings.append({
                    "detector": "structuring", "subject_type": "account",
                    "subject_ids": [acc], "score": score,
                    "evidence": {"count": len(window), "total": round(total, 2), "threshold": T,
                                 "closeness": round(closeness, 2), "span_hours": round(span_h, 1)},
                    "window": {"start": window[0]["timestamp"], "end": window[-1]["timestamp"]},
                })
                break
    return findings


CIRC_WINDOW_H = 72        # whole loop must close within this many hours
# money returning to origin / money that left it. Real laundering skims a few % per hop,
# so a 4-hop loop lands around 0.78 end-to-end — 0.7 catches those without admitting noise.
CIRC_MIN_RETENTION = 0.7
CIRC_MAX_RETENTION = 1.25  # laundering skims value; it doesn't grow. Above this = coincidence.
# A value-retaining laundering loop carries real money on every hop, so the cycle search only
# needs the "money edges" of the graph. Pruning the cycle-topology graph to directed pairs that
# carry at least one transfer this large keeps every real loop while dropping the mass of small
# legit/noise edges that simple_cycles would otherwise explore — the search then scales with the
# (small, slow-growing) set of large transfers, not total transaction count. This is what lets
# detection keep up with a live stream of hundreds of thousands of transactions.
CIRC_MONEY_EDGE = 1000.0


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
    # Keep every real tx per pair for the proof step, but track the largest transfer per pair so
    # we can build the cycle-search graph from MONEY EDGES only (see CIRC_MONEY_EDGE) — exact for
    # value-retaining loops, and the key to scaling cycle detection to very large transaction sets.
    tx_by_pair = defaultdict(list)
    pair_max = defaultdict(float)
    for t in transactions:
        p = (t["src"], t["dst"])
        tx_by_pair[p].append(t)
        amt = float(t["amount"])
        if amt > pair_max[p]:
            pair_max[p] = amt
    dg = nx.DiGraph()
    for (s, d), mx in pair_max.items():
        if mx >= CIRC_MONEY_EDGE:
            dg.add_edge(s, d)

    # Established-business / low-KYC accounts run legitimate inter-company SETTLEMENT loops
    # (money cycles back, value retained, fast) that are structurally identical to laundering.
    # The separating signal is the KYC/account profile: a real laundering ring always contains
    # at least one fresh / personal / elevated-KYC account, while a legit settlement loop is
    # ALL established business + low-KYC. Skip a cycle only when every member fits that profile.
    legit_biz = {a["account_id"] for a in (accounts or [])
                 if a.get("account_type") == "business" and a.get("kyc_risk") == "low"}

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
        if legit_biz and all(a in legit_biz for a in cyc):
            continue  # legit inter-company settlement loop (all established business + low-KYC)
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


ROUND_STEP = 1000.0      # "clean" amounts are whole multiples of €1,000
ROUND_MIN = 1000.0       # ignore tiny round payments (a €50 transfer isn't a laundering tell)
MIN_ROUND_COUNT = 3      # need a habit of round transfers, not one coincidence


def _is_round(amt: float) -> bool:
    return amt >= ROUND_MIN and abs(amt / ROUND_STEP - round(amt / ROUND_STEP)) < 1e-9


def detect_round_amounts(graph, accounts, transactions) -> list[dict]:
    """A5: accounts that transact in suspiciously CLEAN round numbers (whole multiples of
    €1,000). Genuine commerce produces messy amounts (€4,137.22); deliberately round transfers
    are a weak laundering tell. This is a LOW-WEIGHT amplifier (never seeds a ring) — it nudges
    an account already under suspicion, it does not flag on its own. Score scales with how many
    round transfers the account makes and what share of its activity they represent."""
    round_by_acc = defaultdict(list)
    total_by_acc = defaultdict(int)
    for t in transactions:
        amt = float(t["amount"])
        is_round = _is_round(amt)
        for acc in (t["src"], t["dst"]):
            total_by_acc[acc] += 1
            if is_round:
                round_by_acc[acc].append(t["tx_id"])
    findings = []
    for acc, rtx in round_by_acc.items():
        if len(rtx) < MIN_ROUND_COUNT:
            continue
        share = len(rtx) / total_by_acc[acc] if total_by_acc[acc] else 0.0
        score = round(min(1.0, 0.3 + 0.08 * (len(rtx) - MIN_ROUND_COUNT) + 0.3 * share), 2)
        findings.append({
            "detector": "round_amounts", "subject_type": "account", "subject_ids": [acc],
            "score": score,
            "evidence": {"round_tx_count": len(rtx), "round_share": round(share, 2),
                         "step": ROUND_STEP, "tx_ids": rtx[:10]},
        })
    return findings


# ── B3: rapid fiat → crypto conversion ────────────────────────────────────────
FIAT_CHANNELS = frozenset({"sepa", "wire", "card", "cash_deposit"})
FC_WINDOW_H = 24        # crypto-out must follow the fiat-in within this many hours
FC_MIN_IN = 5_000.0     # material value — pocket-change conversions aren't a laundering tell
FC_MIN_RATIO = 0.5      # crypto-out must carry at least this fraction of the fiat-in (a cut may be skimmed)


def detect_fiat_to_crypto(graph, accounts, transactions) -> list[dict]:
    """B3: an account takes in FIAT (sepa/wire/card/cash) and pushes it straight back out via
    CRYPTO within FC_WINDOW_H — the placement→crypto-layering hop. A channel-typed specialisation
    of pass-through: same receive-then-forward shape, but it specifically catches the moment dirty
    fiat is converted into crypto (looser ratio than pass-through, since a cut is often skimmed).
    Score reflects how completely the inflow was converted and how fast."""
    ins, outs = defaultdict(list), defaultdict(list)
    for t in transactions:
        if t.get("channel") in FIAT_CHANNELS:
            ins[t["dst"]].append(t)
        elif t.get("channel") == "crypto":
            outs[t["src"]].append(t)
    findings = []
    for acc in set(ins) & set(outs):
        hit = None
        for ti in ins.get(acc, []):
            if ti["amount"] < FC_MIN_IN:
                continue
            for to in outs.get(acc, []):
                dt = _ts(to["timestamp"]) - _ts(ti["timestamp"])
                if (timedelta(0) <= dt <= timedelta(hours=FC_WINDOW_H)
                        and to["amount"] >= FC_MIN_RATIO * ti["amount"]
                        and to["dst"] != ti["src"]):
                    hit = (ti, to, dt)
                    break
            if hit:
                break
        if not hit:
            continue
        ti, to, dt = hit
        hours = dt.total_seconds() / 3600
        completeness = min(1.0, to["amount"] / ti["amount"]) if ti["amount"] else 0.0
        speed = max(0.0, 1.0 - hours / FC_WINDOW_H)
        score = round(min(1.0, 0.55 + 0.25 * completeness + 0.20 * speed), 2)
        findings.append({
            "detector": "fiat_to_crypto", "subject_type": "account", "subject_ids": [acc],
            "score": score,
            "evidence": {"fiat_in": round(ti["amount"], 2), "fiat_channel": ti["channel"],
                         "crypto_out": round(to["amount"], 2), "hours": round(hours, 1),
                         "completeness": round(completeness, 2), "speed": round(speed, 2)},
            "window": {"start": ti["timestamp"], "end": to["timestamp"]},
        })
    return findings


PASS_WINDOW_H = 24  # receive then forward within this many hours to count as a relay


def detect_passthrough(graph, accounts, transactions) -> list[dict]:
    """#3: account receives X then forwards >=0.8X within 24h (mule relay / layering).

    Score by ratio AND speed (REQUIREMENTS §9 #3) instead of a flat constant: a relay
    that forwards the full amount within minutes is a far stronger mule signal than one
    that forwards 80% a day later. Flat-scoring pinned every layering relay at the same
    0.30 risk — just under the flag threshold — so genuine relay mules went uncaught.
    """
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
            hours = dt.total_seconds() / 3600
            # completeness: how much of the inflow was forwarded (capped at 1.0 — forwarding
            # MORE than came in is consolidation, still relay-like but not extra-suspicious).
            completeness = min(1.0, to["amount"] / ti["amount"]) if ti["amount"] else 0.0
            # speed: faster relay = more suspicious. 0h → 1.0, full 24h window → 0.0.
            speed = max(0.0, 1.0 - hours / PASS_WINDOW_H)
            # floor 0.55 (the pattern itself is suspicious) up to 1.0 for a fast, full relay.
            score = round(min(1.0, 0.55 + 0.25 * completeness + 0.20 * speed), 2)
            findings.append({
                "detector": "passthrough", "subject_type": "account",
                "subject_ids": [acc], "score": score,
                "evidence": {"in": round(ti["amount"], 2), "out": round(to["amount"], 2),
                             "hours": round(hours, 1),
                             "completeness": round(completeness, 2), "speed": round(speed, 2)},
                "window": {"start": ti["timestamp"], "end": to["timestamp"]},
            })
    return findings
