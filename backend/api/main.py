"""MuleNet API — REQUIREMENTS.md §8 (Owner: P4).

Run from the repo root:
    pip install -r backend/requirements.txt
    uvicorn backend.api.main:app --reload --port 8000
    # open http://localhost:8000
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape as _xesc

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.ai.sar import generate_sar
from backend.data.generator import LiveFeed, generate_dataset
from backend.detect import pipeline
from backend.eval.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample_data"
FRONTEND = ROOT / "frontend"

app = FastAPI(title="MuleNet API")
STATE: dict = {"dataset": None, "labels": None, "result": None, "live": None}

# ── watchlist screening (synthetic, deterministic per account) ──────────────
# Mirrors a real AML stack screening every customer against sanctions / PEP /
# adverse-media lists. Derived deterministically from the account id (+ risk),
# biased toward high-risk accounts, so results are stable per dataset.
_SANCTION_LISTS = ("OFAC SDN", "EU Consolidated List", "UN Security Council")
_ADVERSE = ("fraud investigation", "money-laundering allegations",
            "organised-crime ties", "embezzlement charges")


def _ahash(aid: str) -> int:
    return int(hashlib.md5(aid.encode()).hexdigest()[:8], 16)


def _screening(acc: dict, risk: float) -> list[dict]:
    h = _ahash(acc["account_id"])
    flagged = risk >= 0.5
    hits: list[dict] = []
    if (flagged and h % 6 == 0) or h % 120 == 0:
        hits.append({"type": "sanctions", "label": "Sanctions match",
                     "list": _SANCTION_LISTS[h % len(_SANCTION_LISTS)],
                     "detail": "Strong name/identifier match — escalate for manual review"})
    if (flagged and h % 7 == 1) or h % 40 == 0:
        hits.append({"type": "pep", "label": "PEP", "list": "Dow Jones PEP",
                     "detail": "Politically exposed person or close associate"})
    if (flagged and h % 5 == 2) or h % 35 == 0:
        hits.append({"type": "adverse_media", "label": "Adverse media", "list": "Refinitiv World-Check",
                     "detail": "Negative news: " + _ADVERSE[h % len(_ADVERSE)]})
    return hits


def _recompute():
    STATE["result"] = pipeline.run(STATE["dataset"])


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
    risk = {a["account_id"]: a["risk"] for a in r["account_risk"]}
    screened = sum(1 for a in d["accounts"] if _screening(a, risk.get(a["account_id"], 0)))
    return {"accounts": len(d["accounts"]), "transactions": len(d["transactions"]),
            "rings_detected": len(r["rings"]),
            "flagged_accounts": sum(1 for a in r["account_risk"] if a["risk"] >= 0.5),
            "screening_hits": screened}


class GenReq(BaseModel):
    # defaults match backend/data/generator.py so "Generate" yields a rich network
    n_accounts: int = 800
    n_legit_tx: int = 4000
    n_rings: int = 15
    seed: int = 42


@app.post("/api/dataset/generate")
def gen(req: GenReq):
    STATE["live"] = None
    STATE["dataset"], STATE["labels"] = generate_dataset(req.n_accounts, req.n_legit_tx, req.n_rings, req.seed)
    _recompute()
    return {"dataset_id": f"seed{req.seed}", "summary": _summary()}


# ── LIVE STREAM (P1's LiveFeed engine, wired by P4) ─────────────────────────
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


@app.post("/api/stream/start")
def stream_start(seed: int | None = None):
    """Begin a live monitored stream: a small starting network that grows on each poll."""
    lf = LiveFeed(seed=seed)
    STATE["dataset"], STATE["labels"] = lf.initial(100)
    STATE["live"] = lf
    _recompute()
    return {"summary": _summary()}


@app.get("/api/stream/next")
def stream_next():
    """One tick of the live stream: emit new transactions, re-run detection, return the new
    edges + any freshly-detected ring (for a 🚨 alert) + an updated summary."""
    lf = STATE.get("live")
    if not lf:
        raise HTTPException(409, "no active live stream — call /api/stream/start first")
    batch = lf.next_batch()
    STATE["dataset"]["transactions"].extend(batch["transactions"])
    burst = batch.get("ring")
    if burst:
        mule = burst.pop("_mule_accounts", [])
        STATE["labels"]["rings"].append({k: v for k, v in burst.items() if not k.startswith("_")})
        STATE["labels"]["mule_accounts"] = sorted(set(STATE["labels"]["mule_accounts"]) | set(mule))
    _recompute()

    alert = None
    if burst:  # map the planted burst to the detected ring it best overlaps, for a clickable alert
        ba = set(burst["account_ids"])
        best, best_ov = None, 0
        for dr in STATE["result"]["rings"]:
            ov = len(set(dr["account_ids"]) & ba)
            if ov > best_ov:
                best, best_ov = dr, ov
        if best:
            alert = {"ring_id": best["ring_id"], "account_ids": best["account_ids"],
                     "patterns": best["patterns"], "n_accounts": len(best["account_ids"])}
    return {"new_edges": _enriched_edges(batch["transactions"]), "ring": alert,
            "clock": batch.get("clock"), "summary": _summary()}


@app.post("/api/stream/stop")
def stream_stop():
    """End the live stream and restore the committed fixture."""
    STATE["live"] = None
    _load_committed()
    return {"summary": _summary()}


@app.get("/api/dataset/current")
def current():
    return _summary()


@app.get("/api/graph")
def graph(max_nodes: int = 400):
    d, r = STATE["dataset"], STATE["result"]
    risk = {a["account_id"]: a["risk"] for a in r["account_risk"]}
    # Map each account / transaction to the highest-scoring ring it belongs to.
    # rings are sorted by score desc, so setdefault keeps the strongest ring.
    # `ring` is an additive field on top of the §8 graph contract — frontend uses
    # it to color detected clusters; consumers that ignore it are unaffected.
    node_ring: dict[str, str] = {}
    tx_ring: dict[str, str] = {}
    for ring in r["rings"]:
        for acc in ring["account_ids"]:
            node_ring.setdefault(acc, ring["ring_id"])
        for tx in ring["tx_ids"]:
            tx_ring.setdefault(tx, ring["ring_id"])
    keep = set()
    for ring in r["rings"]:
        keep |= set(ring["account_ids"])
    for a in sorted(d["accounts"], key=lambda a: -risk.get(a["account_id"], 0)):
        if len(keep) >= max_nodes:
            break
        keep.add(a["account_id"])
    # owner/country/KYC on nodes and channel/timestamp on edges are additive fields
    # so the frontend can show human detail and filter on it (§8 consumers unaffected).
    nodes = [{"id": a["account_id"], "label": a["account_id"], "risk": risk.get(a["account_id"], 0),
              "type": a["account_type"], "ring": node_ring.get(a["account_id"]),
              "owner_name": a.get("owner_name"), "country": a.get("country"), "kyc_risk": a.get("kyc_risk"),
              "screened": bool(_screening(a, risk.get(a["account_id"], 0)))}
             for a in d["accounts"] if a["account_id"] in keep]
    edges = [{"id": t["tx_id"], "source": t["src"], "target": t["dst"], "amount": t["amount"],
              "suspicious": risk.get(t["src"], 0) >= 0.5 or risk.get(t["dst"], 0) >= 0.5,
              "ring": tx_ring.get(t["tx_id"]), "channel": t.get("channel"), "timestamp": t.get("timestamp")}
             for t in d["transactions"] if t["src"] in keep and t["dst"] in keep]
    return {"nodes": nodes, "edges": edges}


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
             "n_findings": fcount.get(a["account_id"], 0),
             "screening": _screening(a, rmap.get(a["account_id"], 0))} for a in d["accounts"]]


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
            "findings": findings, "transactions": txs,
            "screening": _screening(amap[acc_id], acc_risk)}


@app.post("/api/accounts/{acc_id}/analyze")
def analyze(acc_id: str):
    """AI analysis of one account + its connected accounts (P5). One-shot LLM call; template fallback."""
    if acc_id not in {a["account_id"] for a in STATE["dataset"]["accounts"]}:
        raise HTTPException(404, "account not found")
    from backend.ai.analysis import analyze_account
    return analyze_account(acc_id, STATE["result"], STATE["dataset"])


@app.post("/api/rings/{ring_id}/sar")
def sar(ring_id: str):
    r = next((x for x in STATE["result"]["rings"] if x["ring_id"] == ring_id), None)
    if not r:
        raise HTTPException(404, "ring not found")
    out = generate_sar(r, STATE["dataset"]["accounts"], STATE["dataset"]["transactions"],
                        STATE["result"]["findings"])
    r["narrative"] = out["narrative"]
    return out


@app.get("/api/rings/{ring_id}/goaml")
def goaml(ring_id: str):
    """Structured regulatory STR filing in goAML-style XML (the UN/FIU format) — the
    machine-readable filing that complements the human SAR narrative (P4)."""
    r = next((x for x in STATE["result"]["rings"] if x["ring_id"] == ring_id), None)
    if not r:
        raise HTTPException(404, "ring not found")
    d, res = STATE["dataset"], STATE["result"]
    amap = {a["account_id"]: a for a in d["accounts"]}
    txs = [t for t in d["transactions"] if t["tx_id"] in set(r["tx_ids"])]
    total = round(sum(t["amount"] for t in txs), 2)
    sar_out = generate_sar(r, d["accounts"], d["transactions"], res["findings"])
    now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def acct(aid: str) -> str:
        a = amap.get(aid, {})
        return ("<t_account><institution_name>MuleNet Bank</institution_name>"
                f"<account>{_xesc(aid)}</account><currency_code>EUR</currency_code>"
                f"<account_name>{_xesc(a.get('owner_name', ''))}</account_name>"
                f"<personal_account_type>{_xesc(a.get('account_type', ''))}</personal_account_type>"
                "</t_account>")

    tx_xml = "".join(
        "<transaction>"
        f"<transactionnumber>{_xesc(t['tx_id'])}</transactionnumber>"
        f"<date_transaction>{_xesc(t['timestamp'])}</date_transaction>"
        f"<transmode_code>{_xesc(t.get('channel', ''))}</transmode_code>"
        f"<amount_local>{t['amount']}</amount_local>"
        f"<t_from>{acct(t['src'])}</t_from><t_to>{acct(t['dst'])}</t_to>"
        "</transaction>" for t in txs)
    indicators = "".join(f"<indicator>{_xesc(p)}</indicator>" for p in r.get("patterns", []))

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<report>\n'
           "  <rentity_id>MULENET-KKKCP</rentity_id>\n  <submission_code>E</submission_code>\n"
           "  <report_code>STR</report_code>\n"
           f"  <entity_reference>{_xesc(ring_id)}</entity_reference>\n"
           f"  <submission_date>{now}</submission_date>\n  <currency_code_local>EUR</currency_code_local>\n"
           "  <reporting_person><first_name>MuleNet</first_name><last_name>Compliance</last_name>"
           "<title>AML Analyst</title></reporting_person>\n"
           f"  <reason>{_xesc(sar_out.get('narrative', ''))}</reason>\n"
           f"  <report_indicators>{indicators}</report_indicators>\n"
           f"  <total_amount>{total}</total_amount>\n"
           f"  <transactions>{tx_xml}</transactions>\n</report>\n")
    return Response(content=xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="STR_{ring_id}.xml"'})


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
