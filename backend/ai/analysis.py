"""Account AI analysis (P5) — click an account, get the LLM's read on it and its network.

One-shot completion (no tools): we hand the model the subject account, its risk/findings, and its
connected accounts (transaction counterparties with flows), and ask for an AML assessment.
Provider is auto-detected in llm.py (OpenAI / OpenRouter). Deterministic template fallback so the
feature works with no key and never errors the UI.
"""
from __future__ import annotations

import json

from backend.ai import llm

PROMPT = """You are a senior AML investigator reviewing a flagged bank account. Use ONLY the
structured evidence below — the subject account, the accounts sending money INTO it, the accounts
it sends money OUT to, the aggregate money flow, and the detector findings.

Reason like an analyst, not a template. Ground every claim in the data: cite concrete account ids,
EUR amounts, transaction counts, KYC levels, account age, and the in-vs-out balance of funds.
Decide which laundering typologies (if any) fit and justify each from the evidence:
structuring/smurfing, layering, pass-through relay, fan-in, fan-out, or circular flow.

Write a sharp, specific assessment in natural prose (~120-200 words, no rigid headers) covering:
- A verdict WITH a confidence level (high/medium/low) and the account's role in the network
  (mule, relay, aggregator/controller, or likely legitimate).
- The strongest red flags, each tied to specific counterparties and figures.
- A brief narrative of how money moves through this account.
- The 2-3 highest-priority next steps for an investigator (freeze, RFI, SAR, expand to which
  counterparties, etc.).
If the evidence is weak, say so plainly rather than inventing risk. Vary your phrasing; do not
reuse boilerplate sentences.

ACCOUNT & NETWORK EVIDENCE (JSON):
{ctx}"""


def _context(account_id: str, result: dict, dataset: dict) -> dict | None:
    amap = {a["account_id"]: a for a in dataset["accounts"]}
    rmap = {a["account_id"]: a for a in result["account_risk"]}
    acct = amap.get(account_id)
    if not acct:
        return None

    inflow: dict[str, list] = {}   # sender -> txns into subject
    outflow: dict[str, list] = {}  # recipient -> txns out of subject
    for t in dataset["transactions"]:
        if t["dst"] == account_id:
            inflow.setdefault(t["src"], []).append(t)
        elif t["src"] == account_id:
            outflow.setdefault(t["dst"], []).append(t)

    def summarize(flows: dict) -> list:
        ranked = sorted(flows.items(), key=lambda kv: -sum(x["amount"] for x in kv[1]))[:10]
        return [{"account_id": cp, "owner": amap.get(cp, {}).get("owner_name"),
                 "kyc_risk": amap.get(cp, {}).get("kyc_risk"),
                 "risk": rmap.get(cp, {}).get("risk"),
                 "n_tx": len(ts), "total": round(sum(x["amount"] for x in ts), 2)}
                for cp, ts in ranked]

    findings = [f for f in result["findings"] if account_id in f["subject_ids"]][:10]
    total_in = round(sum(x["amount"] for ts in inflow.values() for x in ts), 2)
    total_out = round(sum(x["amount"] for ts in outflow.values() for x in ts), 2)
    all_ts = sorted(t["timestamp"] for t in dataset["transactions"]
                    if t["src"] == account_id or t["dst"] == account_id)
    return {
        "subject": {"account_id": account_id, "owner": acct.get("owner_name"),
                    "account_type": acct.get("account_type"), "country": acct.get("country"),
                    "kyc_risk": acct.get("kyc_risk"), "opened_at": acct.get("opened_at"),
                    "risk": rmap.get(account_id, {}).get("risk")},
        "flow_summary": {
            "total_in": total_in, "total_out": total_out,
            "retained": round(total_in - total_out, 2),
            "passthrough_ratio": round(total_out / total_in, 2) if total_in else None,
            "distinct_senders": len(inflow), "distinct_recipients": len(outflow),
            "first_tx": all_ts[0] if all_ts else None, "last_tx": all_ts[-1] if all_ts else None,
        },
        "senders_into_subject": summarize(inflow),
        "recipients_from_subject": summarize(outflow),
        "findings": findings,
    }


def _result(ctx: dict, analysis: str, source: str) -> dict:
    return {"analysis": analysis, "source": source, "subject": ctx["subject"],
            "connected": {"senders": ctx["senders_into_subject"],
                          "recipients": ctx["recipients_from_subject"]},
            "findings": ctx["findings"]}


def _template(ctx: dict) -> dict:
    s = ctx["subject"]
    n_in, n_out = len(ctx["senders_into_subject"]), len(ctx["recipients_from_subject"])
    risk = s.get("risk") or 0
    verdict = "likely mule" if risk >= 0.5 else ("suspicious" if risk >= 0.3 else "probably legitimate")
    detail = ("High fan-in/out with elevated risk is consistent with relaying funds; recommend "
              "review and consider a freeze." if risk >= 0.5
              else "Some network activity but no strong laundering signal; routine monitoring suffices.")
    text = (f"Account {s['account_id']} ({s.get('owner') or 'unknown'}, {s.get('account_type')}, "
            f"KYC {s.get('kyc_risk')}, risk {risk}) transacts with {n_in} senders and {n_out} "
            f"recipients. Verdict: {verdict}. {detail}")
    return _result(ctx, text, "template")


def analyze_account(account_id: str, result: dict, dataset: dict) -> dict:
    ctx = _context(account_id, result, dataset)
    if ctx is None:
        return {"error": "account not found"}
    if llm.available():
        try:
            # temperature > 0 so the assessment varies run-to-run instead of repeating boilerplate
            txt, source = llm.text(
                [{"role": "user", "content": PROMPT.format(ctx=json.dumps(ctx))}],
                max_tokens=900, temperature=0.8)
            return _result(ctx, txt, source)
        except Exception as e:  # noqa: BLE001 — any provider failure -> template, never break the UI
            print(f"[analysis] LLM unavailable, using template: {e}")
    return _template(ctx)
