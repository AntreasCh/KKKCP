"""SAR generator — REQUIREMENTS.md §11 (Owner: P5). The ONLY LLM call in MuleNet.

Order of preference: AWS Bedrock (sponsor points) -> Anthropic API -> deterministic
template. The template means the demo NEVER depends on the network — AI is additive.

TODO(P5): verify the exact Bedrock model id for our account; add the "Ask MuleNet"
analyst-copilot endpoint (REQUIREMENTS §"How to close the AWS gap").
"""
from __future__ import annotations

import json
import os

MODEL_ID = "claude-haiku-4-5"

PROMPT = """You are an AML compliance analyst. Write a concise Suspicious Activity Report (SAR)
for the money-laundering ring described below. Be factual, cite the patterns and amounts.
Return ONLY JSON with keys: summary, parties, suspicious_activity, recommended_action.

RING DATA:
{ctx}"""


def _context(ring, accounts, transactions, findings) -> dict:
    amap = {a["account_id"]: a for a in accounts}
    txids = set(ring["tx_ids"])
    txs = [t for t in transactions if t["tx_id"] in txids]
    total = round(sum(t["amount"] for t in txs), 2)
    return {
        "ring_id": ring["ring_id"], "patterns": ring["patterns"], "score": ring["score"],
        "n_accounts": len(ring["account_ids"]), "n_tx": len(txs), "total_amount": total,
        "key_accounts": [{"id": a, "owner": amap.get(a, {}).get("owner_name"),
                          "kyc": amap.get(a, {}).get("kyc_risk")} for a in ring["key_accounts"]],
    }


def _template(ctx: dict) -> dict:
    summary = (f"Ring {ctx['ring_id']} involves {ctx['n_accounts']} accounts and {ctx['n_tx']} "
               f"transactions totalling EUR {ctx['total_amount']:,.2f}, exhibiting "
               f"{', '.join(ctx['patterns']) or 'suspicious'} patterns (risk {ctx['score']}).")
    parties = "; ".join(f"{k['id']} ({k.get('owner') or 'unknown'}, KYC {k.get('kyc')})"
                        for k in ctx["key_accounts"]) or "n/a"
    activity = ("Funds move through the network in a manner consistent with layering and "
                "structuring: amounts and timing indicate deliberate obfuscation of origin.")
    rec = "Freeze the key accounts, file a SAR with the FIU, and review linked counterparties."
    narrative = (f"SUSPICIOUS ACTIVITY REPORT — {ctx['ring_id']}\n\n{summary}\n\n"
                 f"Key parties: {parties}\n\n{activity}\n\nRecommended action: {rec}")
    return {"narrative": narrative,
            "structured": {"summary": summary, "parties": parties,
                           "suspicious_activity": activity, "recommended_action": rec},
            "source": "template"}


def _wrap_ai(txt: str, ctx: dict, source: str) -> dict:
    try:
        data = json.loads(txt)
        narrative = (f"SUSPICIOUS ACTIVITY REPORT — {ctx['ring_id']}\n\n{data.get('summary','')}\n\n"
                     f"Parties: {data.get('parties','')}\n\n{data.get('suspicious_activity','')}\n\n"
                     f"Recommended action: {data.get('recommended_action','')}")
        return {"narrative": narrative, "structured": data, "source": source}
    except Exception:
        return {"narrative": txt, "structured": {"summary": txt}, "source": source}


def generate_sar(ring, accounts, transactions, findings) -> dict:
    ctx = _context(ring, accounts, transactions, findings)

    # 1) AWS Bedrock (preferred — sponsor points)
    try:
        if os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_PROFILE"):
            import boto3
            br = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "eu-west-1"))
            body = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 800,
                    "messages": [{"role": "user", "content": PROMPT.format(ctx=json.dumps(ctx))}]}
            resp = br.invoke_model(modelId=os.getenv("BEDROCK_MODEL", f"anthropic.{MODEL_ID}"),
                                   body=json.dumps(body))
            txt = json.loads(resp["body"].read())["content"][0]["text"]
            return _wrap_ai(txt, ctx, "bedrock")
    except Exception as e:
        print(f"[sar] Bedrock unavailable, trying next: {e}")

    # 2) Anthropic API
    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=MODEL_ID, max_tokens=800,
                messages=[{"role": "user", "content": PROMPT.format(ctx=json.dumps(ctx))}])
            txt = "".join(b.text for b in msg.content if b.type == "text")
            return _wrap_ai(txt, ctx, "anthropic")
    except Exception as e:
        print(f"[sar] Anthropic API unavailable, using template: {e}")

    # 3) deterministic template (always works)
    return _template(ctx)
