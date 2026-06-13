"""'Ask MuleNet' analyst copilot — REQUIREMENTS §11b (Owner: P5).

**NOT a wrapper.** Claude is given TOOLS to query the detection results (rings, accounts,
findings) and runs a tool-use loop to *investigate* the network before answering — an agent
over our own data, via the Anthropic API. This is the substantial AI piece.

TODO(P5): add tools (trace_path between two accounts, compare_rings), stream the answer,
and surface the tool-call trace in the UI so judges watch the agent investigate.
"""
from __future__ import annotations

import json
import os

# Configurable; bump to a stronger model for deeper reasoning. Tokens here are tiny/cheap.
MODEL = os.getenv("MULENET_MODEL", "claude-haiku-4-5")

SYSTEM = (
    "You are MuleNet's AML analyst copilot. Use the provided tools to investigate the detected "
    "money-laundering network before you answer — list rings, inspect a ring, look up accounts. "
    "Be concise and cite the ring ids, account ids, patterns and amounts that justify your answer."
)

TOOLS = [
    {"name": "list_rings", "description": "List all detected laundering rings (id, score, patterns, size).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_ring", "description": "Full detail for one ring by id, e.g. DET_001.",
     "input_schema": {"type": "object", "properties": {"ring_id": {"type": "string"}}, "required": ["ring_id"]}},
    {"name": "get_account", "description": "An account's risk score and findings by id, e.g. ACC00042.",
     "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}},
]


def _tools_impl(result, dataset):
    rmap = {a["account_id"]: a for a in result["account_risk"]}
    amap = {a["account_id"]: a for a in dataset["accounts"]}
    rings = {r["ring_id"]: r for r in result["rings"]}

    def list_rings():
        return [{"ring_id": r["ring_id"], "score": r["score"], "patterns": r["patterns"],
                 "n_accounts": len(r["account_ids"])} for r in result["rings"]]

    def get_ring(ring_id):
        r = rings.get(ring_id)
        if not r:
            return {"error": "ring not found"}
        return {"ring_id": r["ring_id"], "score": r["score"], "patterns": r["patterns"],
                "n_accounts": len(r["account_ids"]), "n_tx": len(r["tx_ids"]),
                "key_accounts": [{"id": a, "risk": rmap.get(a, {}).get("risk"),
                                  "owner": amap.get(a, {}).get("owner_name")} for a in r["key_accounts"]]}

    def get_account(account_id):
        a = amap.get(account_id)
        if not a:
            return {"error": "account not found"}
        f = [x for x in result["findings"] if account_id in x["subject_ids"]]
        return {"account": a, "risk": rmap.get(account_id, {}).get("risk"), "findings": f[:10]}

    return {"list_rings": list_rings, "get_ring": get_ring, "get_account": get_account}


def ask(question: str, result: dict, dataset: dict, labels: dict | None = None) -> dict:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"answer": "Set ANTHROPIC_API_KEY to enable the AI copilot. "
                          "Meanwhile, browse the detected rings and the eval panel.",
                "tool_calls": [], "source": "disabled"}
    import anthropic

    client = anthropic.Anthropic()
    impl = _tools_impl(result, dataset)
    messages = [{"role": "user", "content": question}]
    trace = []

    for _ in range(6):  # bounded agentic loop
        resp = client.messages.create(model=MODEL, max_tokens=1024, system=SYSTEM,
                                      tools=TOOLS, messages=messages)
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"answer": text, "tool_calls": trace, "source": "anthropic"}
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                fn = impl.get(b.name)
                out = fn(**b.input) if fn else {"error": "unknown tool"}
                trace.append({"tool": b.name, "input": b.input})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})

    return {"answer": "(stopped after max tool iterations)", "tool_calls": trace, "source": "anthropic"}
