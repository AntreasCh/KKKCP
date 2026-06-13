"""Account AI analysis (P5) — click an account, get the LLM's read on it and its network.

One-shot completion (no tools): we hand the model the subject account, its risk/findings, and its
connected accounts (transaction counterparties with flows), and ask for an AML assessment.
Provider is auto-detected in llm.py (OpenAI / OpenRouter). Deterministic template fallback so the
feature works with no key and never errors the UI.
"""
from __future__ import annotations

import json

from backend.ai import llm

PROMPT = """You are a senior AML investigator writing a short, objective assessment of ONE bank account.

Be evidence-led, NOT alarmist. A deterministic detection system has already scored this account:
its `risk` (0.0 = clean … 1.0 = highest), `risk_band`, and `findings` list are AUTHORITATIVE — base
your verdict on them, not on a hunch.

Decision rules (follow them):
- If `risk_band` is "low" (risk < 0.3) AND `findings` is empty: the account looks **LEGITIMATE**.
  Say so plainly, briefly explain the benign pattern (e.g. salary/payroll, a merchant collecting
  many small payments, normal personal use, routine business settlement), and recommend NO action /
  routine monitoring. Do NOT call normal activity "suspicious" and do NOT invent laundering typologies.
- Only name a laundering typology (structuring/smurfing, layering, pass-through relay, fan-in,
  fan-out, circular) if a `findings` entry or the flow numbers clearly support it — and cite that
  specific evidence. High volume alone is NOT suspicious (legitimate businesses move large sums).
- Scale your language to the score: low → reassuring; medium → cautious, note what to watch;
  high → flag clearly with the proof.

Using ONLY the JSON evidence, write ~100-170 words of natural prose covering:
1. A verdict that matches `risk`/`findings`, with a confidence level and the account's role
   (mule, relay, aggregator, or legitimate <type>).
2. The concrete reasons — cite account ids, EUR amounts, KYC, account age, the in/out balance — or,
   if legitimate, why the activity is consistent with normal behaviour.
3. A proportionate recommendation.
Vary your phrasing; don't reuse boilerplate.

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
    risk = rmap.get(account_id, {}).get("risk") or 0
    risk_band = "high" if risk >= 0.6 else ("medium" if risk >= 0.3 else "low")
    return {
        "subject": {"account_id": account_id, "owner": acct.get("owner_name"),
                    "account_type": acct.get("account_type"), "country": acct.get("country"),
                    "kyc_risk": acct.get("kyc_risk"), "opened_at": acct.get("opened_at"),
                    "risk": risk, "risk_band": risk_band, "n_findings": len(findings),
                    "flagged_by_detectors": bool(findings)},
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
            # moderate temperature: enough variation to avoid boilerplate, low enough to stay
            # grounded in the risk score (so a 0-risk account isn't called "suspicious")
            txt, source = llm.text(
                [{"role": "user", "content": PROMPT.format(ctx=json.dumps(ctx))}],
                max_tokens=900, temperature=0.5)
            if txt.strip():
                return _result(ctx, txt, source)
            # empty content (some reasoning models): treat as a soft failure below
            raise RuntimeError("model returned empty content")
        except Exception as e:  # noqa: BLE001
            # A key IS configured but the call failed — surface the real reason instead of silently
            # returning the (identical) template, so the user can see it's e.g. a bad OpenRouter key.
            msg = str(e)
            print(f"[analysis] OpenRouter call failed: {msg}")
            out = _template(ctx)
            out["source"] = "error"
            out["error"] = msg
            out["analysis"] = ("⚠️ The AI provider (OpenRouter) call failed, so this is the rule-based "
                               f"fallback — NOT the LLM.\nReason: {msg}{llm.bad_key_hint()}\n\n"
                               + out["analysis"])
            return out
    # No key configured at all -> deterministic template (keeps the demo working offline).
    return _template(ctx)
