"""SAR generator — REQUIREMENTS.md §11 (Owner: P5).

Drafts a Suspicious Activity Report for a detected ring.
Order of preference: **OpenRouter** (any/free model) -> **Anthropic API** -> AWS Bedrock ->
deterministic template. The template means the demo NEVER depends on the network — AI is additive.

Provider selection (by env var):
  - OPENROUTER_API_KEY  -> OpenRouter (OpenAI-compatible); model from OPENROUTER_MODEL (or MULENET_MODEL)
  - ANTHROPIC_API_KEY   -> Anthropic; model from MULENET_MODEL (default claude-haiku-4-5)
"""
from __future__ import annotations

import json
import os

# Anthropic model (used only on the Anthropic fallback path). OpenAI/OpenRouter model + provider
# selection live in backend/ai/llm.py, auto-detected from the API key.
MODEL = os.getenv("MULENET_MODEL", "claude-haiku-4-5")

PROMPT = """You are an AML compliance analyst. Write a concise Suspicious Activity Report (SAR)
for the money-laundering ring described below. Be factual, cite the patterns and amounts.

Return ONLY a raw JSON object (no markdown, no ``` code fences) with exactly these keys, and every
value MUST be a single plain-text string (not a nested object or list):
  "summary", "parties", "suspicious_activity", "recommended_action"

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


def _strip_fence(txt: str) -> str:
    """Models often wrap JSON in a ```json … ``` fence — peel it off before parsing."""
    s = txt.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _flat(v) -> str:
    """Coerce a field to readable plain text — the model sometimes returns dicts/lists."""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "; ".join(_flat(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_flat(x)}" for k, x in v.items())
    return str(v)


def _wrap_ai(txt: str, ctx: dict, source: str) -> dict:
    try:
        data = json.loads(_strip_fence(txt))
        summary, parties = _flat(data.get("summary", "")), _flat(data.get("parties", ""))
        activity, rec = _flat(data.get("suspicious_activity", "")), _flat(data.get("recommended_action", ""))
        narrative = (f"SUSPICIOUS ACTIVITY REPORT — {ctx['ring_id']}\n\n{summary}\n\n"
                     f"Parties: {parties}\n\n{activity}\n\nRecommended action: {rec}")
        return {"narrative": narrative,
                "structured": {"summary": summary, "parties": parties,
                               "suspicious_activity": activity, "recommended_action": rec},
                "source": source}
    except Exception:
        # not JSON after all — fall back to the model's prose as the narrative
        return {"narrative": _strip_fence(txt), "structured": {"summary": _strip_fence(txt)}, "source": source}


def generate_sar(ring, accounts, transactions, findings) -> dict:
    ctx = _context(ring, accounts, transactions, findings)
    prompt = PROMPT.format(ctx=json.dumps(ctx))

    # 1) OpenAI-compatible (OpenAI or OpenRouter, auto-detected from the key in llm.py)
    try:
        from backend.ai import llm
        if llm.available():
            txt, source = llm.text([{"role": "user", "content": prompt}], max_tokens=800)
            return _wrap_ai(txt, ctx, source)
    except Exception as e:
        print(f"[sar] OpenAI-compatible provider unavailable, trying next: {e}")

    # 2) Anthropic API
    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=MODEL, max_tokens=800,
                messages=[{"role": "user", "content": PROMPT.format(ctx=json.dumps(ctx))}])
            txt = "".join(b.text for b in msg.content if b.type == "text")
            return _wrap_ai(txt, ctx, "anthropic")
    except Exception as e:
        print(f"[sar] Anthropic API unavailable, trying next: {e}")

    # 3) AWS Bedrock (optional fallback — only if we end up with AWS creds)
    try:
        if os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_PROFILE"):
            import boto3
            br = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "eu-west-1"))
            body = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 800,
                    "messages": [{"role": "user", "content": PROMPT.format(ctx=json.dumps(ctx))}]}
            resp = br.invoke_model(modelId=os.getenv("BEDROCK_MODEL", f"anthropic.{MODEL}"),
                                   body=json.dumps(body))
            txt = json.loads(resp["body"].read())["content"][0]["text"]
            return _wrap_ai(txt, ctx, "bedrock")
    except Exception as e:
        print(f"[sar] Bedrock unavailable, using template: {e}")

    # 4) deterministic template (always works — demo never depends on the network)
    return _template(ctx)
