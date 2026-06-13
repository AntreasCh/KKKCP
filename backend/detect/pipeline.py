"""Detection pipeline orchestrator — REQUIREMENTS.md §13 (P3 owns; P4 calls it).

run(dataset) -> {"findings": [...], "account_risk": [...], "rings": [...]}
This is the single integration point: detectors + scoring compose here.
"""
from __future__ import annotations

from backend.detect import network, scoring, structural
from backend.graph.build import build_graph


def run(dataset: dict) -> dict:
    accounts = dataset["accounts"]
    transactions = dataset["transactions"]
    graph = build_graph(transactions)

    findings: list[dict] = []
    findings += structural.detect_structuring(graph, accounts, transactions)
    findings += structural.detect_circular(graph, accounts, transactions)
    findings += structural.detect_passthrough(graph, accounts, transactions)
    findings += network.detect_fan(graph, accounts, transactions)
    findings += network.detect_communities(graph, accounts, transactions)

    account_risk = scoring.score_accounts(findings)
    rings = scoring.build_rings(findings, account_risk, transactions)
    return {"findings": findings, "account_risk": account_risk, "rings": rings}
