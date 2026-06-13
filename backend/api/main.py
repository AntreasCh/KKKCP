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

from backend.ai.sar import generate_sar
from backend.data.generator import generate_dataset
from backend.detect import pipeline
from backend.eval.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample_data"
FRONTEND = ROOT / "frontend"

app = FastAPI(title="MuleNet API")
STATE: dict = {"dataset": None, "labels": None, "result": None}


def _recompute():
    STATE["result"] = pipeline.run(STATE["dataset"])


@app.on_event("startup")
def _startup():
    ds, lb = SAMPLE / "dataset.json", SAMPLE / "labels.json"
    if ds.exists():
        STATE["dataset"] = json.loads(ds.read_text())
        STATE["labels"] = json.loads(lb.read_text()) if lb.exists() else {"mule_accounts": [], "rings": []}
    else:
        STATE["dataset"], STATE["labels"] = generate_dataset()
    _recompute()


def _summary() -> dict:
    d, r = STATE["dataset"], STATE["result"]
    return {"accounts": len(d["accounts"]), "transactions": len(d["transactions"]),
            "rings_detected": len(r["rings"]),
            "flagged_accounts": sum(1 for a in r["account_risk"] if a["risk"] >= 0.5)}


class GenReq(BaseModel):
    n_accounts: int = 600
    n_legit_tx: int = 2500
    n_rings: int = 6
    seed: int = 42


@app.post("/api/dataset/generate")
def gen(req: GenReq):
    STATE["dataset"], STATE["labels"] = generate_dataset(req.n_accounts, req.n_legit_tx, req.n_rings, req.seed)
    _recompute()
    return {"dataset_id": f"seed{req.seed}", "summary": _summary()}


@app.get("/api/dataset/current")
def current():
    return _summary()


@app.get("/api/graph")
def graph(max_nodes: int = 400):
    d, r = STATE["dataset"], STATE["result"]
    risk = {a["account_id"]: a["risk"] for a in r["account_risk"]}
    keep = set()
    for ring in r["rings"]:
        keep |= set(ring["account_ids"])
    for a in sorted(d["accounts"], key=lambda a: -risk.get(a["account_id"], 0)):
        if len(keep) >= max_nodes:
            break
        keep.add(a["account_id"])
    nodes = [{"id": a["account_id"], "label": a["account_id"], "risk": risk.get(a["account_id"], 0),
              "type": a["account_type"]} for a in d["accounts"] if a["account_id"] in keep]
    edges = [{"id": t["tx_id"], "source": t["src"], "target": t["dst"], "amount": t["amount"],
              "suspicious": risk.get(t["src"], 0) >= 0.5 or risk.get(t["dst"], 0) >= 0.5}
             for t in d["transactions"] if t["src"] in keep and t["dst"] in keep]
    return {"nodes": nodes, "edges": edges}


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
    return {"account": amap[acc_id], "risk": rmap.get(acc_id, {}).get("risk", 0),
            "findings": findings, "transactions": txs}


@app.post("/api/rings/{ring_id}/sar")
def sar(ring_id: str):
    r = next((x for x in STATE["result"]["rings"] if x["ring_id"] == ring_id), None)
    if not r:
        raise HTTPException(404, "ring not found")
    out = generate_sar(r, STATE["dataset"]["accounts"], STATE["dataset"]["transactions"],
                        STATE["result"]["findings"])
    r["narrative"] = out["narrative"]
    return out


class AskReq(BaseModel):
    question: str


@app.post("/api/ask")
def ask(req: AskReq):
    """'Ask MuleNet' analyst copilot — a tool-using agent over the detection results (P5)."""
    from backend.ai.copilot import ask as copilot_ask
    return copilot_ask(req.question, STATE["result"], STATE["dataset"], STATE["labels"])


@app.get("/api/eval")
def api_eval():
    return evaluate(STATE["result"], STATE["labels"])


# Mount the static frontend LAST so /api/* routes win.
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
