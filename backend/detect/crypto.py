"""C6 — crypto chain-analysis (Option A: wallet tagging, no on-chain graph).

Reads the C6 transaction fields (crypto_asset / counterparty_wallet / wallet_label). Detectors:
- detect_mixer_exposure   : direct mixer/darknet exposure — near-conclusive (high weight, auto-flag-ish)
- detect_high_risk_wallet : exposure to flagged wallets — contributor
- detect_wallet_consolidation : many distinct SUSPICIOUS wallets funnel into one account (crypto fan-in)
- detect_chain_hopping    : one account rapidly switches assets (BTC->ETH->USDT) to break the trail

None are in scoring.STRONG, so they never seed a ring. The generator labels suspicious wallets
ONLY on all-mule crypto legs, so exposure (attributed to both endpoints) is precision-safe.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
MIXER_LABELS = frozenset({"mixer", "darknet"})
SUSPICIOUS_LABELS = frozenset({"mixer", "darknet", "high_risk"})
CONSOLIDATION_MIN = 4          # distinct suspicious wallets funnelling into one account
CONSOLIDATION_WINDOW_H = 48
CHAIN_MIN_TX = 3               # crypto txns in the window
CHAIN_WINDOW_H = 24


def _ts(s: str) -> datetime:
    return datetime.strptime(s, TS_FMT)


def _crypto(transactions):
    return [t for t in transactions if t.get("channel") == "crypto"]


def detect_mixer_exposure(graph, accounts, transactions) -> list[dict]:
    """Direct exposure to a mixer/tumbler or darknet-market wallet — a near-conclusive crypto
    laundering signal. Attributed to BOTH parties of the leg."""
    agg: dict = defaultdict(lambda: {"count": 0, "labels": set(), "wallets": set()})
    for t in _crypto(transactions):
        if t.get("wallet_label") in MIXER_LABELS:
            for acc in (t["src"], t["dst"]):
                e = agg[acc]
                e["count"] += 1
                e["labels"].add(t["wallet_label"])
                e["wallets"].add(t.get("counterparty_wallet"))
    findings = []
    for acc, e in agg.items():
        findings.append({
            "detector": "mixer_exposure", "subject_type": "account", "subject_ids": [acc],
            "score": round(min(1.0, 0.8 + 0.1 * e["count"]), 2),
            "evidence": {"crypto_tx": e["count"], "labels": sorted(e["labels"]),
                         "wallets": sorted(w for w in e["wallets"] if w)[:5]},
        })
    return findings


def detect_high_risk_wallet(graph, accounts, transactions) -> list[dict]:
    """Exposure to flagged 'high_risk' wallets (scam/abuse addresses) — a contributor, not proof."""
    agg: dict = defaultdict(lambda: {"count": 0, "wallets": set()})
    for t in _crypto(transactions):
        if t.get("wallet_label") == "high_risk":
            for acc in (t["src"], t["dst"]):
                e = agg[acc]
                e["count"] += 1
                e["wallets"].add(t.get("counterparty_wallet"))
    findings = []
    for acc, e in agg.items():
        findings.append({
            "detector": "high_risk_wallet", "subject_type": "account", "subject_ids": [acc],
            "score": round(min(1.0, 0.5 + 0.1 * e["count"]), 2),
            "evidence": {"crypto_tx": e["count"], "wallets": sorted(w for w in e["wallets"] if w)[:5]},
        })
    return findings


def detect_wallet_consolidation(graph, accounts, transactions) -> list[dict]:
    """Many DISTINCT suspicious wallets funnel crypto into one account within a window — the crypto
    analogue of mule fan-in (consolidating dispersed proceeds). Attributed to the collector (dst)."""
    incoming: dict = defaultdict(list)
    for t in _crypto(transactions):
        if t.get("wallet_label") in SUSPICIOUS_LABELS and t.get("counterparty_wallet"):
            try:
                incoming[t["dst"]].append((_ts(t["timestamp"]), t["counterparty_wallet"]))
            except (ValueError, KeyError):
                continue
    win = timedelta(hours=CONSOLIDATION_WINDOW_H)
    findings = []
    for acc, evs in incoming.items():
        evs.sort(key=lambda e: e[0])
        best: set = set()
        for i in range(len(evs)):
            wallets: set = set()
            for j in range(i, len(evs)):
                if evs[j][0] - evs[i][0] <= win:
                    wallets.add(evs[j][1])
                else:
                    break
            if len(wallets) > len(best):
                best = wallets
        if len(best) >= CONSOLIDATION_MIN:
            findings.append({
                "detector": "wallet_consolidation", "subject_type": "account", "subject_ids": [acc],
                "score": round(min(1.0, 0.5 + 0.07 * len(best)), 2),
                "evidence": {"distinct_wallets": len(best), "window_hours": CONSOLIDATION_WINDOW_H},
            })
    return findings


def detect_chain_hopping(graph, accounts, transactions) -> list[dict]:
    """One account moves funds through several crypto assets in quick succession (BTC->ETH->USDT)
    to break the on-chain trail. Approximate signal (Option A): >= CHAIN_MIN_TX crypto txns spanning
    >= 2 distinct assets within a short window. Attributed to the sender."""
    by_src: dict = defaultdict(list)
    for t in _crypto(transactions):
        if t.get("crypto_asset"):
            try:
                by_src[t["src"]].append((_ts(t["timestamp"]), t["crypto_asset"]))
            except (ValueError, KeyError):
                continue
    win = timedelta(hours=CHAIN_WINDOW_H)
    findings = []
    for acc, evs in by_src.items():
        evs.sort(key=lambda e: e[0])
        for i in range(len(evs)):
            assets: set = set()
            count = 0
            for j in range(i, len(evs)):
                if evs[j][0] - evs[i][0] <= win:
                    assets.add(evs[j][1])
                    count += 1
                else:
                    break
            if count >= CHAIN_MIN_TX and len(assets) >= 2:
                findings.append({
                    "detector": "chain_hopping", "subject_type": "account", "subject_ids": [acc],
                    "score": round(min(1.0, 0.4 + 0.12 * len(assets)), 2),
                    "evidence": {"crypto_tx": count, "distinct_assets": sorted(assets),
                                 "window_hours": CHAIN_WINDOW_H},
                })
                break
    return findings
