"""'Ask MuleNet' analyst copilot — REQUIREMENTS §11b (Owner: P5).

**NOT a wrapper.** Claude is given TOOLS to query the detection results (rings, accounts,
findings) and runs a tool-use loop to *investigate* the network before answering — an agent
over our own data, via the Anthropic API. This is the substantial AI piece.

Tools exposed to the model:
  - list_rings              : all detected rings (id, score, patterns, size)
  - get_ring                : full detail for one ring
  - get_account             : risk + findings for one account
  - trace_path              : follow the money — shortest tx chain from one account to another
  - compare_rings           : side-by-side comparison of two rings (overlap, patterns, amounts)

Each entry in the returned ``tool_calls`` trace carries ``tool``/``input``/``output`` so the UI
can render the agent investigating step by step.
"""
from __future__ import annotations

import json
import os
from collections import deque

# Anthropic model (used only on the Anthropic fallback path). OpenAI/OpenRouter model + provider
# selection live in backend/ai/llm.py, auto-detected from the API key.
MODEL = os.getenv("MULENET_MODEL", "claude-haiku-4-5")

SYSTEM = (
    "You are MuleNet's AML analyst copilot. Investigate WITH THE TOOLS before answering — list and "
    "inspect rings, look up accounts, trace money between accounts, compare rings. "
    "Ground every conclusion in what the tools return: the detector findings and the risk scores are "
    "authoritative. Be objective, not alarmist — if an account or ring has a low risk score or no "
    "findings, say it looks legitimate rather than implying guilt, and don't invent patterns the data "
    "doesn't show. High transaction volume alone is not suspicious. When you do flag something, cite "
    "the specific ring ids, account ids, patterns, amounts and risk scores that justify it. "
    "Answer concisely in plain language; if you can't verify something with the tools, say so."
)

TOOLS = [
    {"name": "list_rings", "description": "List all detected laundering rings (id, score, patterns, size).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_ring", "description": "Full detail for one ring by id, e.g. DET_001.",
     "input_schema": {"type": "object", "properties": {"ring_id": {"type": "string"}}, "required": ["ring_id"]}},
    {"name": "get_account", "description": "An account's risk score and findings by id, e.g. ACC00042.",
     "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}},
    {"name": "trace_path",
     "description": "Follow the money: find the shortest chain of transactions from one account to "
                    "another, in the direction funds flow. Returns each hop with amount, timestamp and channel.",
     "input_schema": {"type": "object",
                      "properties": {"src_account": {"type": "string"},
                                     "dst_account": {"type": "string"},
                                     "max_hops": {"type": "integer", "description": "default 6"}},
                      "required": ["src_account", "dst_account"]}},
    {"name": "compare_rings",
     "description": "Compare two detected rings side by side: scores, patterns, sizes, total amounts "
                    "and any shared accounts. Use to explain how two rings relate.",
     "input_schema": {"type": "object",
                      "properties": {"ring_id_a": {"type": "string"}, "ring_id_b": {"type": "string"}},
                      "required": ["ring_id_a", "ring_id_b"]}},
]


def _tools_impl(result, dataset):
    rmap = {a["account_id"]: a for a in result["account_risk"]}
    amap = {a["account_id"]: a for a in dataset["accounts"]}
    rings = {r["ring_id"]: r for r in result["rings"]}
    txs = dataset["transactions"]

    # directed money-flow adjacency: src -> [(dst, tx), ...]
    adj: dict[str, list] = {}
    for t in txs:
        adj.setdefault(t["src"], []).append(t)

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

    def trace_path(src_account, dst_account, max_hops=6):
        if src_account not in amap or dst_account not in amap:
            return {"error": "unknown account"}
        if src_account == dst_account:
            return {"error": "src and dst are the same account"}
        # BFS over directed tx edges -> shortest hop chain following the money.
        prev: dict[str, tuple] = {src_account: None}
        q = deque([(src_account, 0)])
        while q:
            node, depth = q.popleft()
            if depth >= max_hops:
                continue
            for t in adj.get(node, []):
                nxt = t["dst"]
                if nxt not in prev:
                    prev[nxt] = (node, t)
                    if nxt == dst_account:
                        q.clear()
                        break
                    q.append((nxt, depth + 1))
        if dst_account not in prev:
            return {"found": False, "src": src_account, "dst": dst_account,
                    "note": f"no directed money flow within {max_hops} hops"}
        # reconstruct
        hops, cur = [], dst_account
        while prev[cur] is not None:
            parent, t = prev[cur]
            hops.append({"from": parent, "to": cur, "tx_id": t["tx_id"], "amount": t["amount"],
                         "timestamp": t["timestamp"], "channel": t["channel"]})
            cur = parent
        hops.reverse()
        return {"found": True, "src": src_account, "dst": dst_account, "n_hops": len(hops),
                "total_moved": round(sum(h["amount"] for h in hops), 2), "hops": hops}

    def compare_rings(ring_id_a, ring_id_b):
        ra, rb = rings.get(ring_id_a), rings.get(ring_id_b)
        if not ra or not rb:
            return {"error": "one or both rings not found"}

        def _amount(r):
            ids = set(r["tx_ids"])
            return round(sum(t["amount"] for t in txs if t["tx_id"] in ids), 2)

        sa, sb = set(ra["account_ids"]), set(rb["account_ids"])
        shared = sorted(sa & sb)
        return {
            ring_id_a: {"score": ra["score"], "patterns": ra["patterns"],
                        "n_accounts": len(sa), "total_amount": _amount(ra)},
            ring_id_b: {"score": rb["score"], "patterns": rb["patterns"],
                        "n_accounts": len(sb), "total_amount": _amount(rb)},
            "shared_accounts": shared, "n_shared": len(shared),
            "shared_patterns": sorted(set(ra["patterns"]) & set(rb["patterns"])),
        }

    return {"list_rings": list_rings, "get_ring": get_ring, "get_account": get_account,
            "trace_path": trace_path, "compare_rings": compare_rings}


def _ask_openai_compatible(question: str, result: dict, dataset: dict) -> dict:
    """Tool-using loop via OpenRouter (OpenAI SDK) function-calling."""
    from backend.ai import llm

    impl = _tools_impl(result, dataset)
    oa_tools = [{"type": "function",
                 "function": {"name": t["name"], "description": t["description"],
                              "parameters": t["input_schema"]}} for t in TOOLS]
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    trace = []
    source = llm.provider()

    try:
        for _ in range(8):  # bounded agentic loop
            msg = llm.complete(messages, max_tokens=1024, tools=oa_tools)
            source = msg.pop("_source", source)
            calls = msg.get("tool_calls") or []
            if not calls:
                return {"answer": msg.get("content") or "", "tool_calls": trace, "source": source}
            messages.append(msg)  # assistant turn with tool_calls
            for tc in calls:
                name = tc["function"]["name"]
                raw = tc["function"].get("arguments") or "{}"
                args = json.loads(raw) if isinstance(raw, str) else raw
                fn = impl.get(name)
                out = fn(**args) if fn else {"error": "unknown tool"}
                trace.append({"tool": name, "input": args, "output": out})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(out)})
        return {"answer": "(stopped after max tool iterations)", "tool_calls": trace, "source": source}
    except Exception as e:
        hint = llm.bad_key_hint() if "401" in str(e) else ""
        return {"answer": f"AI request failed: {e}{hint}", "tool_calls": trace, "source": "error"}


def ask(question: str, result: dict, dataset: dict, labels: dict | None = None) -> dict:
    from backend.ai import llm

    # Provider order: OpenAI/OpenRouter (auto-detected from key) -> Anthropic -> disabled.
    if llm.available():
        return _ask_openai_compatible(question, result, dataset)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"answer": "Set OPENROUTER_API_KEY / OPENAI_API_KEY or ANTHROPIC_API_KEY to enable the AI "
                          "copilot. Meanwhile, browse the detected rings and the eval panel.",
                "tool_calls": [], "source": "disabled"}
    import anthropic

    client = anthropic.Anthropic()
    impl = _tools_impl(result, dataset)
    messages = [{"role": "user", "content": question}]
    trace = []

    for _ in range(8):  # bounded agentic loop
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
                # surface the result in the trace so the UI can show what the agent saw
                trace.append({"tool": b.name, "input": b.input, "output": out})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})

    return {"answer": "(stopped after max tool iterations)", "tool_calls": trace, "source": "anthropic"}
