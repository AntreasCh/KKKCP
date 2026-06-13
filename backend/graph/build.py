"""Transaction-graph construction — REQUIREMENTS.md §13 (Owner: P2).

build_graph(transactions) -> networkx.MultiDiGraph
  nodes = account_ids
  edges = one per transaction, keyed by tx_id, with amount/timestamp/channel attrs.
"""
from __future__ import annotations

from datetime import datetime

import networkx as nx

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s, TS_FMT)


def build_graph(transactions: list[dict]) -> "nx.MultiDiGraph":
    g = nx.MultiDiGraph()
    for t in transactions:
        g.add_edge(
            t["src"], t["dst"], key=t["tx_id"],
            tx_id=t["tx_id"], amount=float(t["amount"]),
            timestamp=t["timestamp"], channel=t.get("channel"),
        )
    return g
