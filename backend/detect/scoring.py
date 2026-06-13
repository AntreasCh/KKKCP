"""Scoring + ring assembly — REQUIREMENTS.md §10 (Owner: P3 / Andreas).

score_accounts(findings)                    -> list[AccountRisk]
build_rings(findings, account_risk, txns)   -> list[Ring]

Rings are assembled from STRONG-detector seeds (structuring / circular / pass-through / fan),
expanded to the hub's counterparties, merged on overlap, and scored by member risk + pattern
diversity + **transaction volume among members**. Volume is the key precision lever: real
laundering moves real money, so legit low-amount clusters fall below the volume floor.
"""
from __future__ import annotations

from collections import defaultdict

# How much each detector contributes to an ACCOUNT's risk.
WEIGHTS = {"structuring": 0.9, "circular": 0.9, "passthrough": 0.8,
           "fan_in": 0.8, "fan_out": 0.8, "community": 0.15}

# Detectors strong enough to seed a ring (community is context only).
STRONG = {"structuring", "circular", "passthrough", "fan_in", "fan_out"}

# account risk = min(1, weighted_sum / NORMALIZER). Calibrated so that ONE proven strong
# typology crosses τ=0.5: a relay (passthrough 0.8·0.6=0.48), a circular loop, a structuring
# pattern or an unsuppressed fan each warrants suspicion on its own — that's how AML triage
# works. (1.6 required two corroborating signals, which under-scored single-role mules and
# capped account recall at 0.36.) Safe because the strong detectors never fire on a legit
# account here, so the worst legit weighted-sum (~0.24, factor-suppressed fan) stays well
# below τ. Verified: precision holds at 1.0, recall 0.36→0.77, 0 FP rings. See test_scoring.py.
NORMALIZER = 0.9
MIN_RING_VOLUME = 15_000  # EUR of transactions among members — laundering moves real money
MIN_RING_SCORE = 0.45
MIN_RING_SIZE = 3
MONEY_EDGE = 5_000        # a seed must contain at least one transfer this large (kills legit-cycle noise)
SEED_SCORE_FLOOR = 0.3    # a down-weighted account finding (e.g. legit hub) must not seed a ring


def _has_money_edge(members: set[str], pair_amt: dict) -> bool:
    for a in members:
        for b in members:
            if pair_amt.get((a, b), 0.0) >= MONEY_EDGE:
                return True
    return False


def score_accounts(findings: list[dict]) -> list[dict]:
    agg = defaultdict(lambda: {"sum": 0.0, "signals": []})
    for f in findings:
        contrib = WEIGHTS.get(f["detector"], 0.5) * f["score"]
        for acc in f["subject_ids"]:
            agg[acc]["sum"] += contrib
            agg[acc]["signals"].append({"detector": f["detector"], "score": round(f["score"], 2)})
    out = []
    for acc, a in agg.items():
        risk = min(1.0, a["sum"] / NORMALIZER)
        top = sorted(a["signals"], key=lambda s: -s["score"])[:4]
        out.append({"account_id": acc, "risk": round(risk, 3), "top_signals": top})
    out.sort(key=lambda x: -x["risk"])
    return out


def build_rings(findings: list[dict], account_risk: list[dict], transactions: list[dict]) -> list[dict]:
    risk_map = {a["account_id"]: a["risk"] for a in account_risk}

    # adjacency + pairwise amounts / tx ids
    in_n, out_n = defaultdict(set), defaultdict(set)
    pair_amt, pair_tx = defaultdict(float), defaultdict(list)
    for t in transactions:
        s, d = t["src"], t["dst"]
        out_n[s].add(d)
        in_n[d].add(s)
        pair_amt[(s, d)] += float(t["amount"])
        pair_tx[(s, d)].append(t["tx_id"])

    # 1) seed clusters from strong findings
    seeds = []
    for f in findings:
        if f["detector"] not in STRONG:
            continue
        # Account findings that were down-weighted (e.g. a legit business hub) must not
        # seed a ring. Subgraph findings (circular) always seed — they're proof-carrying.
        if f["subject_type"] == "account" and f["score"] < SEED_SCORE_FLOOR:
            continue
        if f["subject_type"] == "subgraph":
            accts = set(f["subject_ids"])
        else:  # account finding — expand the hub to its counterparties
            hub = f["subject_ids"][0]
            cps = f["evidence"].get("counterparties")
            if cps:
                accts = {hub} | set(cps)
            else:
                # No explicit counterparty list (structuring / passthrough): expand ONLY to
                # neighbors connected by a significant transfer. Expanding to every neighbor
                # glued unrelated seeds into 90-account mega-blobs (imprecise + false-positive).
                accts = {hub} | {n for n in (in_n[hub] | out_n[hub])
                                 if pair_amt.get((hub, n), 0.0) >= MONEY_EDGE
                                 or pair_amt.get((n, hub), 0.0) >= MONEY_EDGE}
        if len(accts) >= 2 and _has_money_edge(accts, pair_amt):
            seeds.append({"accts": accts, "patterns": {f["detector"]}, "max": f["score"]})

    # 2) merge seeds that overlap (share >= 2 accounts). DETERMINISTIC order: highest score
    #    first, ties broken by the member set itself — so ring assembly never depends on
    #    detector emit order or Python's per-process hash seed (otherwise the ring count
    #    drifts run-to-run, which wrecks a live demo).
    merged: list[dict] = []
    for s in sorted(seeds, key=lambda s: (-s["max"], tuple(sorted(s["accts"])))):
        hit = next((m for m in merged if len(s["accts"] & m["accts"]) >= 2), None)
        if hit:
            hit["accts"] |= s["accts"]
            hit["patterns"] |= s["patterns"]
            hit["max"] = max(hit["max"], s["max"])
        else:
            merged.append(s)

    # 3) score + threshold (iterate members sorted so the volume sum is bit-for-bit stable)
    rings = []
    for m in merged:
        members = sorted(m["accts"])
        if len(members) < MIN_RING_SIZE:
            continue
        vol = sum(pair_amt[(a, b)] for a in members for b in members if (a, b) in pair_amt)
        txids = [tx for a in members for b in members for tx in pair_tx.get((a, b), [])]
        mrisk = [risk_map.get(a, 0.0) for a in members]
        avg_risk = sum(mrisk) / len(mrisk) if mrisk else 0.0
        max_risk = max(mrisk) if mrisk else 0.0
        # A real ring is ONE strong hub + many low-risk spokes (classic mule fan-out).
        # Pure mean risk dilutes the hub to ~0, so blend in the peak member risk.
        risk_term = 0.6 * max_risk + 0.4 * avg_risk
        diversity = min(1.0, 0.25 * len(m["patterns"]))
        vol_factor = min(1.0, vol / 50_000)
        score = round(0.5 * risk_term + 0.2 * diversity + 0.3 * vol_factor, 3)
        if score < MIN_RING_SCORE or vol < MIN_RING_VOLUME:
            continue
        rings.append({"account_ids": members, "tx_ids": txids, "patterns": sorted(m["patterns"]),
                      "key_accounts": sorted(members, key=lambda a: (-risk_map.get(a, 0.0), a))[:3],
                      "score": score, "narrative": None})

    # stable ordering + ids: score desc, then first account id; assign DET_xxx after sorting
    rings.sort(key=lambda r: (-r["score"], r["account_ids"][0]))
    for i, r in enumerate(rings, 1):
        r["ring_id"] = f"DET_{i:03d}"
    return rings
