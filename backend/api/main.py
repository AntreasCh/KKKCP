"""MuleNet API — REQUIREMENTS.md §8 (Owner: P4).

Run from the repo root:
    pip install -r backend/requirements.txt
    uvicorn backend.api.main:app --reload --port 8000
    # open http://localhost:8000
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.data.generator import generate_dataset
from backend.detect import pipeline
from backend.eval.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample_data"
FRONTEND = ROOT / "frontend"

# Auto-freeze rule: accounts at/above this risk are auto-frozen. Fixed constant (no slider).
FREEZE_THRESHOLD = 0.90

app = FastAPI(title="MuleNet API")


@app.middleware("http")
async def _no_cache_frontend(request, call_next):
    """Serve the static frontend with no-cache so a returning browser always picks up the latest
    app.js / style.css (no stale UI after we ship a change). API responses are unaffected."""
    resp = await call_next(request)
    path = request.url.path
    if not path.startswith("/api/") and (path == "/" or path.endswith((".js", ".css", ".html"))):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp
# manual: account ids whose status was set by a human reviewer (block/ban/clear) — these are
# sticky and ignore the auto-freeze.
STATE: dict = {"dataset": None, "labels": None, "result": None, "manual": set()}


def _recompute():
    STATE["result"] = pipeline.run(STATE["dataset"])
    _apply_freeze()  # auto-freeze ≥ threshold every time risk is recomputed


def _load_committed():
    """(Re)load the committed sample fixture into STATE and run detection."""
    ds, lb = SAMPLE / "dataset.json", SAMPLE / "labels.json"
    if ds.exists():
        STATE["dataset"] = json.loads(ds.read_text())
        STATE["labels"] = json.loads(lb.read_text()) if lb.exists() else {"mule_accounts": [], "rings": []}
    else:
        STATE["dataset"], STATE["labels"] = generate_dataset()
    _recompute()


@app.on_event("startup")
def _startup():
    _load_committed()


def _summary() -> dict:
    d, r = STATE["dataset"], STATE["result"]
    return {"accounts": len(d["accounts"]), "transactions": len(d["transactions"]),
            "rings_detected": len(r["rings"]),
            "flagged_accounts": sum(1 for a in r["account_risk"] if a["risk"] >= 0.5)}


class GenReq(BaseModel):
    # defaults match backend/data/generator.py so "Generate" yields a rich network
    n_accounts: int = 800
    n_legit_tx: int = 4000
    n_rings: int = 15
    seed: int = 42


@app.post("/api/dataset/generate")
def gen(req: GenReq):
    STATE["manual"] = set()  # fresh dataset → forget prior manual decisions
    STATE["dataset"], STATE["labels"] = generate_dataset(req.n_accounts, req.n_legit_tx, req.n_rings, req.seed)
    _recompute()
    return {"dataset_id": f"seed{req.seed}", "summary": _summary()}


# ── graph enrichment helpers (shared by the account-scoped ego graph) ───────
def _enriched_edges(txs: list[dict]) -> list[dict]:
    risk = {a["account_id"]: a["risk"] for a in STATE["result"]["account_risk"]}
    tx_ring: dict[str, str] = {}
    for ring in STATE["result"]["rings"]:
        for tx in ring["tx_ids"]:
            tx_ring.setdefault(tx, ring["ring_id"])
    return [{"id": t["tx_id"], "source": t["src"], "target": t["dst"], "amount": t["amount"],
             "suspicious": risk.get(t["src"], 0) >= 0.5 or risk.get(t["dst"], 0) >= 0.5,
             "ring": tx_ring.get(t["tx_id"]), "channel": t.get("channel"), "timestamp": t.get("timestamp")}
            for t in txs]


def _enriched_nodes(accounts: list[dict]) -> list[dict]:
    """Build graph nodes for the account-scoped ego graph: each carries risk + ring membership
    so the frontend can risk-color the network and highlight ring members."""
    risk = {a["account_id"]: a["risk"] for a in STATE["result"]["account_risk"]}
    node_ring: dict[str, str] = {}
    for ring in STATE["result"]["rings"]:
        for acc in ring["account_ids"]:
            node_ring.setdefault(acc, ring["ring_id"])
    return [{"id": a["account_id"], "label": a["account_id"], "risk": risk.get(a["account_id"], 0),
             "type": a["account_type"], "ring": node_ring.get(a["account_id"]),
             "owner_name": a.get("owner_name"), "country": a.get("country"), "kyc_risk": a.get("kyc_risk")}
            for a in accounts]


@app.get("/api/dataset/current")
def current():
    return _summary()


@app.get("/api/graph/account/{account_id}")
def graph_account(account_id: str, hops: int = 1, max_nodes: int = 400, max_edges: int = 1500,
                  suspicious_only: bool = False):
    """Ego-network around one account — the scalable lens. Returns the account + its direct
    counterparties (hops=1) or one step further (hops=2) + the transfers among them, in the
    same node/edge shape as /api/graph. The full dataset can be millions of transactions; this
    response is bounded to `max_nodes`/`max_edges` so the graph render stays small and calm."""
    d = STATE["dataset"]
    accts = {a["account_id"]: a for a in d["accounts"]}
    if account_id not in accts:
        raise HTTPException(404, f"account {account_id} not found")
    hops = 2 if int(hops) >= 2 else 1
    txs = d["transactions"]

    own = [t for t in txs if t["src"] == account_id or t["dst"] == account_id]
    edges = list(own)
    if hops >= 2:                                   # follow the money one more step out
        ring1 = set()
        for t in own:
            ring1.add(t["src"]); ring1.add(t["dst"])
        ring1.discard(account_id)
        seen = {t["tx_id"] for t in edges}
        for t in txs:
            if (t["src"] in ring1 or t["dst"] in ring1) and t["tx_id"] not in seen:
                edges.append(t); seen.add(t["tx_id"])

    truncated = False
    if len(edges) > max_edges:                      # keep the largest transfers (the meaningful flows)
        edges = sorted(edges, key=lambda t: -t.get("amount", 0))[:max_edges]
        truncated = True
    keep = {account_id}
    for t in edges:
        keep.add(t["src"]); keep.add(t["dst"])
    if len(keep) > max_nodes:                        # cap nodes: account + highest-risk neighbours
        risk = {a["account_id"]: a["risk"] for a in STATE["result"]["account_risk"]}
        keep = {account_id} | set(sorted(keep, key=lambda a: -risk.get(a, 0))[:max_nodes])
        edges = [t for t in edges if t["src"] in keep and t["dst"] in keep]
        truncated = True

    node_dicts = [accts[a] for a in keep if a in accts]
    out_edges = _enriched_edges(edges)
    out_nodes = _enriched_nodes(node_dicts)
    if suspicious_only:
        # Visual Review: account + ONLY its suspicious/ring counterparties — keep edges flagged
        # suspicious or in a ring, the nodes incident to those edges, plus the focus account node.
        out_edges = [e for e in out_edges if e["suspicious"] or e["ring"]]
        incident = {account_id}
        for e in out_edges:
            incident.add(e["source"]); incident.add(e["target"])
        out_nodes = [n for n in out_nodes if n["id"] in incident]
    return {"focus": account_id, "owner": accts[account_id].get("owner_name"), "hops": hops,
            "nodes": out_nodes, "edges": out_edges,
            "tx_count": len(own), "total_tx": len(txs), "truncated": truncated}


@app.get("/api/accounts")
def accounts_list():
    """Full account list with risk, ring membership and finding counts — powers the
    filterable Accounts table (P4). Additive; the per-account detail route is unchanged."""
    d, r = STATE["dataset"], STATE["result"]
    rmap = {a["account_id"]: a["risk"] for a in r["account_risk"]}
    acc_rings: dict[str, list] = {}
    for ring in r["rings"]:
        for a in ring["account_ids"]:
            acc_rings.setdefault(a, []).append(ring["ring_id"])
    fcount: dict[str, int] = {}
    for f in r["findings"]:
        for a in f["subject_ids"]:
            fcount[a] = fcount.get(a, 0) + 1
    return [{**a, "risk": round(rmap.get(a["account_id"], 0), 3),
             "rings": acc_rings.get(a["account_id"], []),
             "n_findings": fcount.get(a["account_id"], 0)} for a in d["accounts"]]


@app.get("/api/rings")
def rings():
    return [{k: v for k, v in r.items() if k != "narrative"} for r in STATE["result"]["rings"]]


@app.get("/api/rings/{ring_id}")
def ring_detail(ring_id: str):
    r = next((x for x in STATE["result"]["rings"] if x["ring_id"] == ring_id), None)
    if not r:
        raise HTTPException(404, "ring not found")
    members = set(r["account_ids"])
    txids = set(r["tx_ids"])
    amap = {a["account_id"]: a for a in STATE["dataset"]["accounts"]}
    rmap = {a["account_id"]: a for a in STATE["result"]["account_risk"]}
    accounts = [{**amap.get(a, {"account_id": a}), "risk": rmap.get(a, {}).get("risk", 0)}
                for a in r["account_ids"]]
    txs = [t for t in STATE["dataset"]["transactions"] if t["tx_id"] in txids][:200]
    findings = [f for f in STATE["result"]["findings"] if set(f["subject_ids"]) & members][:50]
    return {**r, "accounts": accounts, "transactions": txs, "findings": findings}


@app.get("/api/accounts/{acc_id}")
def account(acc_id: str):
    amap = {a["account_id"]: a for a in STATE["dataset"]["accounts"]}
    if acc_id not in amap:
        raise HTTPException(404, "account not found")
    rmap = {a["account_id"]: a for a in STATE["result"]["account_risk"]}
    findings = [f for f in STATE["result"]["findings"] if acc_id in f["subject_ids"]]
    txs = [t for t in STATE["dataset"]["transactions"] if t["src"] == acc_id or t["dst"] == acc_id][:200]
    acc_risk = rmap.get(acc_id, {}).get("risk", 0)
    return {"account": amap[acc_id], "risk": acc_risk,
            "top_signals": rmap.get(acc_id, {}).get("top_signals", []),
            "findings": findings, "transactions": txs}


@app.get("/api/transactions/{tx_id}")
def transaction(tx_id: str):
    """Full transaction detail for the inspector's transaction drill-down (Tier D). Returns the raw
    payment plus the risk + status of both endpoints and any ring it belongs to."""
    tx = next((t for t in STATE["dataset"]["transactions"] if t["tx_id"] == tx_id), None)
    if tx is None:
        raise HTTPException(404, "transaction not found")
    amap = {a["account_id"]: a for a in STATE["dataset"]["accounts"]}
    rmap = {a["account_id"]: a["risk"] for a in STATE["result"]["account_risk"]}
    ring_id = None
    for ring in STATE["result"]["rings"]:
        if tx_id in ring["tx_ids"]:
            ring_id = ring["ring_id"]
            break

    def _party(aid: str) -> dict:
        a = amap.get(aid, {})
        return {"account_id": aid, "owner_name": a.get("owner_name"), "country": a.get("country"),
                "account_type": a.get("account_type"), "status": a.get("status", "active"),
                "risk": round(rmap.get(aid, 0.0), 3)}

    return {"transaction": tx, "ring_id": ring_id,
            "src": _party(tx["src"]), "dst": _party(tx["dst"])}


@app.post("/api/accounts/{acc_id}/analyze")
def analyze(acc_id: str):
    """AI analysis of one account + its connected accounts (P5). One-shot LLM call; template fallback."""
    if acc_id not in {a["account_id"] for a in STATE["dataset"]["accounts"]}:
        raise HTTPException(404, "account not found")
    from backend.ai.analysis import analyze_account
    return analyze_account(acc_id, STATE["result"], STATE["dataset"])


# ── enforcement: risk-threshold freezing + manual review (§6) ────────────────
# Mutates Account.status on the in-memory dataset. Auto-freeze uses the fixed FREEZE_THRESHOLD;
# accounts a human reviewed (block/ban/clear) are sticky and ignore the auto-freeze.
_RISK = lambda: {a["account_id"]: a["risk"] for a in STATE["result"]["account_risk"]}
_DECISIONS = {"block": "blocked", "ban": "banned", "clear": "active", "freeze": "frozen"}


def _apply_freeze():
    """(Re)apply the auto-freeze: status='frozen' when risk ≥ FREEZE_THRESHOLD, else 'active' —
    except accounts in STATE['manual'] (a human already decided those), left untouched."""
    if not STATE.get("result"):
        return
    risk = _RISK()
    manual = STATE.setdefault("manual", set())
    for a in STATE["dataset"]["accounts"]:
        if a["account_id"] in manual:
            continue
        a["status"] = "frozen" if risk.get(a["account_id"], 0) >= FREEZE_THRESHOLD else "active"


def _freeze_reason(acc_id: str, risk: float) -> dict:
    """Why this account is under enforcement: threshold + the detector findings that drove the risk."""
    fs = [f for f in STATE["result"]["findings"] if acc_id in f["subject_ids"]]
    patterns = sorted({f["detector"] for f in fs})
    manual = acc_id in STATE.get("manual", set())
    return {
        "threshold": FREEZE_THRESHOLD,
        "auto": not manual,
        "summary": (f"Risk {risk*100:.0f}% ≥ freeze threshold {FREEZE_THRESHOLD*100:.0f}%"
                    if risk >= FREEZE_THRESHOLD else f"Risk {risk*100:.0f}% (manually actioned)"),
        "patterns": patterns,
        "findings": fs[:10],
    }


class DecisionReq(BaseModel):
    action: str  # block | ban | clear | freeze


@app.get("/api/freeze")
def freeze_config():
    """Fixed auto-freeze threshold + how many accounts are frozen/under review."""
    n = sum(1 for a in STATE["dataset"]["accounts"] if a.get("status", "active") != "active")
    return {"threshold": FREEZE_THRESHOLD, "under_review": n}


@app.get("/api/frozen")
def frozen():
    """The review queue: accounts under enforcement (frozen/blocked/banned), highest risk first.
    Each carries a `reason` (threshold + the patterns/findings that drove the risk)."""
    risk = _RISK()
    out = []
    for a in STATE["dataset"]["accounts"]:
        st = a.get("status", "active")
        if st == "active":
            continue
        r = round(risk.get(a["account_id"], 0), 3)
        out.append({"account_id": a["account_id"], "owner_name": a.get("owner_name"),
                    "account_type": a.get("account_type"), "kyc_risk": a.get("kyc_risk"),
                    "status": st, "risk": r, "reason": _freeze_reason(a["account_id"], r)})
    out.sort(key=lambda x: -x["risk"])
    return out


@app.post("/api/accounts/{acc_id}/decision")
def decision(acc_id: str, req: DecisionReq):
    """Record a reviewer's decision on an account: block / ban / clear (unfreeze) / freeze.
    The decision is sticky — it overrides the auto-freeze until the dataset is regenerated."""
    amap = {a["account_id"]: a for a in STATE["dataset"]["accounts"]}
    if acc_id not in amap:
        raise HTTPException(404, "account not found")
    if req.action not in _DECISIONS:
        raise HTTPException(400, f"invalid action (expected one of {list(_DECISIONS)})")
    amap[acc_id]["status"] = _DECISIONS[req.action]
    STATE.setdefault("manual", set()).add(acc_id)  # sticky: ignore auto-freeze from now on
    return {"account_id": acc_id, "status": amap[acc_id]["status"]}


@app.get("/api/eval")
def api_eval():
    return evaluate(STATE["result"], STATE["labels"])


# ── "Ask MuleNet" copilot — a tool-using agent over the detection results (P5) ──
class AskReq(BaseModel):
    question: str


@app.post("/api/ask")
def ask(req: AskReq):
    """'Ask MuleNet' analyst copilot — gives the LLM tools to query the detected rings, accounts
    and findings, runs a bounded tool-use loop, then answers. Returns {answer, tool_calls, source}."""
    from backend.ai.copilot import ask as copilot_ask
    return copilot_ask(req.question, STATE["result"], STATE["dataset"], STATE["labels"])


# Mount the static frontend LAST so /api/* routes win.
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
