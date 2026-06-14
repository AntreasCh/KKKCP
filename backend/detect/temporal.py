"""Temporal behaviour detectors — Tier B (#B1 activity spike, #B2 dormant reactivation).

These read only fields already on the data (timestamps + opened_at). They are LOW-WEIGHT
supporting signals (see scoring.WEIGHTS / not in STRONG): they enrich an account's risk and
surface the *named* typology to the analyst, but they never flag an account on their own and
never seed a ring — the structural detectors (pass-through / fan) own flagging and ring
assembly for these accounts. In real data they'd catch cases the structural ones miss.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ts(s: str) -> datetime:
    return datetime.strptime(s, TS_FMT)


def _latest(transactions: list[dict]):
    latest = None
    for t in transactions:
        try:
            d = _ts(t["timestamp"])
        except (ValueError, KeyError, TypeError):
            continue
        if latest is None or d > latest:
            latest = d
    return latest


# ── B2: dormant → active reactivation ─────────────────────────────────────────
DORMANT_MIN_AGE_DAYS = 365     # the account must be genuinely old (a long-lived, not fresh, account)
DR_WINDOW_H = 24               # receive then forward within this window (reactivated as a conduit)
DR_MIN_IN = 10_000.0           # a material sum — a dormant account waking up for €50 isn't laundering
DR_MIN_RATIO = 0.8             # forwards most of what it received (pass-through reactivation)


def detect_dormant_reactivation(graph, accounts, transactions) -> list[dict]:
    """B2: a long-dormant / aged account that suddenly springs to life as a conduit — receives a
    material sum and forwards most of it within DR_WINDOW_H. Real laundering buys/borrows aged
    'clean history' accounts and reactivates them; an aged account behaving like a fresh mule is
    the tell. (Flagging itself is left to pass-through; this names the reactivation.)"""
    acc_by_id = {a["account_id"]: a for a in (accounts or [])}
    ref = _latest(transactions)
    if ref is None:
        return []
    ins, outs = defaultdict(list), defaultdict(list)
    for t in transactions:
        ins[t["dst"]].append(t)
        outs[t["src"]].append(t)
    findings = []
    for acc in set(ins) & set(outs):
        rec = acc_by_id.get(acc)
        if not rec:
            continue
        try:
            opened = datetime.strptime(str(rec.get("opened_at"))[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        age_days = (ref - opened).days
        if age_days < DORMANT_MIN_AGE_DAYS:
            continue
        hit = None
        for ti in ins[acc]:
            if ti["amount"] < DR_MIN_IN:
                continue
            for to in outs[acc]:
                dt = _ts(to["timestamp"]) - _ts(ti["timestamp"])
                if (timedelta(0) <= dt <= timedelta(hours=DR_WINDOW_H)
                        and to["amount"] >= DR_MIN_RATIO * ti["amount"]
                        and to["dst"] != ti["src"]):
                    hit = (ti, to, dt)
                    break
            if hit:
                break
        if not hit:
            continue
        ti, to, dt = hit
        hours = dt.total_seconds() / 3600
        speed = max(0.0, 1.0 - hours / DR_WINDOW_H)
        score = round(min(1.0, 0.55 + 0.25 * speed + 0.2 * min(1.0, age_days / 1095)), 2)
        findings.append({
            "detector": "dormant_reactivation", "subject_type": "account", "subject_ids": [acc],
            "score": score,
            "evidence": {"account_age_days": age_days, "in": round(ti["amount"], 2),
                         "out": round(to["amount"], 2), "hours": round(hours, 1)},
            "window": {"start": ti["timestamp"], "end": to["timestamp"]},
        })
    return findings


# ── B1: activity velocity / spike vs the account's own baseline ───────────────
SPIKE_WINDOW_H = 24            # the burst window
SPIKE_MIN_TX = 5              # at least this many transactions inside the burst window
SPIKE_BASELINE_MAX = 5        # activity OUTSIDE the burst is sparse (a genuinely quiet baseline)
SPIKE_MIN_VALUE = 20_000.0    # the burst moves a material sum


def detect_activity_spike(graph, accounts, transactions) -> list[dict]:
    """B1: an account that is normally quiet (few, small transactions) suddenly spikes — many
    transactions moving a material sum inside a short window. Activity 'inconsistent with the
    account's own history'. A legit hub is busy *all the time* (no sparse baseline), so it doesn't
    trip this; an account that erupts out of near-silence does."""
    by_acc = defaultdict(list)
    for t in transactions:
        for acc in (t["src"], t["dst"]):
            by_acc[acc].append(t)
    win = timedelta(hours=SPIKE_WINDOW_H)
    findings = []
    for acc, txs in by_acc.items():
        n = len(txs)
        if n < SPIKE_MIN_TX:
            continue
        txs.sort(key=lambda t: _ts(t["timestamp"]))
        # largest count of transactions inside any SPIKE_WINDOW_H window
        best_i, best_j, best_count = 0, 0, 0
        for i in range(n):
            j = i
            while j < n and _ts(txs[j]["timestamp"]) - _ts(txs[i]["timestamp"]) <= win:
                j += 1
            if j - i > best_count:
                best_count, best_i, best_j = j - i, i, j
        if best_count < SPIKE_MIN_TX:
            continue
        if n - best_count > SPIKE_BASELINE_MAX:   # busy outside the window → steady, not a spike
            continue
        window = txs[best_i:best_j]
        vol = sum(t["amount"] for t in window)
        if vol < SPIKE_MIN_VALUE:
            continue
        baseline = n - best_count
        burst_ratio = best_count / max(1, baseline)
        score = round(min(1.0, 0.4 + 0.05 * (best_count - SPIKE_MIN_TX) + 0.2 * min(1.0, burst_ratio / 5)
                          + 0.2 * min(1.0, vol / 100_000)), 2)
        findings.append({
            "detector": "activity_spike", "subject_type": "account", "subject_ids": [acc],
            "score": score,
            "evidence": {"burst_tx": best_count, "baseline_tx": baseline,
                         "burst_value": round(vol, 2), "window_hours": SPIKE_WINDOW_H},
            "window": {"start": window[0]["timestamp"], "end": window[-1]["timestamp"]},
        })
    return findings
