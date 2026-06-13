"""Scoring + ring assembly — REQUIREMENTS.md §10 (Owner: P3).

score_accounts(findings)            -> list[AccountRisk]
build_rings(findings, risk, txns)   -> list[Ring]

PLACEHOLDER weighting + ring merge. TODO(P3): calibrate the normalizer and weights
against the eval harness; link structuring/passthrough accounts into their rings.
"""
from __future__ import annotations

from collections import defaultdict

WEIGHTS = {"structuring": 0.9, "circular": 1.0, "passthrough": 0.7,
           "fan_in": 0.8, "fan_out": 0.8, "community": 0.3}


def score_accounts(findings: list[dict]) -> list[dict]:
    agg = defaultdict(lambda: {"sum": 0.0, "signals": []})
    for f in findings:
        contrib = WEIGHTS.get(f["detector"], 0.5) * f["score"]
        for acc in f["subject_ids"]:
            agg[acc]["sum"] += contrib
            agg[acc]["signals"].append({"detector": f["detector"], "score": round(f["score"], 2)})
    out = []
    for acc, a in agg.items():
        risk = min(1.0, a["sum"] / 3.0)  # TODO(P3): calibrate normalizer
        top = sorted(a["signals"], key=lambda s: -s["score"])[:4]
        out.append({"account_id": acc, "risk": round(risk, 3), "top_signals": top})
    out.sort(key=lambda x: -x["risk"])
    return out


def build_rings(findings: list[dict], account_risk: list[dict], transactions: list[dict]) -> list[dict]:
    risk_map = {a["account_id"]: a["risk"] for a in account_risk}
    tx_by_pair = defaultdict(list)
    for t in transactions:
        tx_by_pair[(t["src"], t["dst"])].append(t["tx_id"])

    candidates = [f for f in findings if f["subject_type"] == "subgraph"]
    rings: list[dict] = []
    rid = 0
    for f in sorted(candidates, key=lambda f: -f["score"]):
        accts = set(f["subject_ids"])
        merged = next((r for r in rings if len(accts & set(r["account_ids"])) >= 2), None)
        if merged:
            merged["account_ids"] = sorted(set(merged["account_ids"]) | accts)
            if f["detector"] not in merged["patterns"]:
                merged["patterns"].append(f["detector"])
        else:
            rid += 1
            rings.append({"ring_id": f"DET_{rid:03d}", "account_ids": sorted(accts),
                          "tx_ids": [], "patterns": [f["detector"]],
                          "key_accounts": [], "score": 0.0, "narrative": None})

    for r in rings:
        members = set(r["account_ids"])
        txids = []
        for (s, d), ids in tx_by_pair.items():
            if s in members and d in members:
                txids.extend(ids)
        r["tx_ids"] = txids
        mrisk = [risk_map.get(a, 0.0) for a in r["account_ids"]]
        avg = sum(mrisk) / len(mrisk) if mrisk else 0.0
        diversity = min(1.0, 0.2 * len(set(r["patterns"])))
        r["score"] = round(min(1.0, 0.7 * avg + 0.3 * diversity), 3)
        r["key_accounts"] = sorted(r["account_ids"], key=lambda a: -risk_map.get(a, 0.0))[:3]

    rings.sort(key=lambda r: -r["score"])
    return [r for r in rings if r["score"] > 0.15][:30]
