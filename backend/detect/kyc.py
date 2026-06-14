"""KYC / identity behavioural detectors — Tier C (#C4 device linkage).

Links accounts that share a device fingerprint or signup IP — one operator running a mule fleet.
Emitted as findings that contribute account risk (scoring.WEIGHTS); NOT in STRONG, so it never
seeds a ring. (C3 activity-vs-declared-profile is a capped amplifier in scoring.py, since a
declared/actual gap is a risk indicator, not proof — legit accounts sometimes exceed their estimate.)
"""
from __future__ import annotations

from collections import defaultdict

# ── C4: device / IP linkage ───────────────────────────────────────────────────
DEVICE_CLUSTER_MIN = 3         # this many accounts on one device/IP = an operator cluster


def detect_device_linkage(graph, accounts, transactions) -> list[dict]:
    """C4: accounts sharing a device fingerprint or signup IP — a single operator controlling
    many accounts. Emits a finding per account in a cluster of >= DEVICE_CLUSTER_MIN, naming the
    other linked accounts. (Flagging itself is corroborated by the structural detectors.)"""
    by_key: dict = defaultdict(set)
    for a in (accounts or []):
        for key in ("device_id", "signup_ip"):
            v = a.get(key)
            if v:
                by_key[(key, v)].add(a["account_id"])
    # account -> set of co-located accounts (union across device + ip), and the shared keys
    linked: dict = defaultdict(set)
    shared_keys: dict = defaultdict(set)
    for (key, v), members in by_key.items():
        if len(members) < DEVICE_CLUSTER_MIN:
            continue
        for m in members:
            linked[m] |= members
            shared_keys[m].add(f"{key}={v}")
    findings = []
    for acc, cluster in linked.items():
        others = sorted(cluster - {acc})
        cluster_size = len(cluster)
        score = round(min(1.0, 0.4 + 0.1 * cluster_size), 2)
        findings.append({
            "detector": "device_linkage", "subject_type": "account", "subject_ids": [acc],
            "score": score,
            "evidence": {"cluster_size": cluster_size, "shared": sorted(shared_keys[acc]),
                         "linked_accounts": others[:10]},
        })
    return findings
