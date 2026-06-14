# ☁️ MuleNet on AWS — Production Architecture

> **For the AWS judge (Nikiforos Botis) & the Q&A.** The hackathon build runs **locally** by
> design (no server to host on for the demo). This document is the honest answer to *"how does
> this run in production on AWS?"* — and shows the AI layer is a **one-adapter swap to Amazon
> Bedrock**.
>
> **What's true today:** detection is 100% deterministic graph maths (no cloud needed); the AI
> layer (per-account analysis + copilot) currently calls an OpenRouter model through the OpenAI SDK. Swapping it
> to **Bedrock** is a single provider adapter (`backend/ai/llm.py`) — same `complete()` interface,
> Bedrock Converse API + tool-use underneath.

---

## Why MuleNet maps cleanly onto AWS

MuleNet is already split into the exact pieces a managed cloud wants: **stateless detection**,
**a graph**, **object storage for datasets**, and **a thin AI layer**. Nothing in the design
assumes a single box.

```
        Banks / PSPs / fintechs                 Compliance analyst (browser)
          (batch or stream)                              │
                │                                        │  HTTPS
                ▼                                         ▼
        ┌──────────────────┐                   ┌────────────────────────┐
        │ Amazon Kinesis / │  transactions     │  CloudFront + S3        │
        │ MSK (stream)  ──────────────────────▶│  (static analyst console)│
        │  or S3 batch     │                   └───────────┬────────────┘
        └────────┬─────────┘                               │ /api/*
                 │                                          ▼
                 │                              ┌────────────────────────┐
                 ▼                              │ API Gateway → Lambda /  │
        ┌──────────────────┐                    │ ECS Fargate (FastAPI)   │
        │  Detection jobs  │   read/write       │  pipeline.run()         │
        │  Lambda / Fargate│◀──────────────────▶│  + /api/ask, /analyze   │
        │  (networkx +     │                    └───────┬────────────┬───┘
        │   Louvain)       │                            │            │
        └───┬──────────┬───┘                            │            │
            │          │                                ▼            ▼
            ▼          ▼                        ┌──────────────┐ ┌──────────────┐
   ┌──────────────┐ ┌──────────────┐           │ Amazon       │ │ Amazon       │
   │ Amazon S3    │ │ Amazon       │           │ Bedrock      │ │ Neptune      │
   │ (datasets,   │ │ Neptune      │           │ (Claude:     │ │ (graph store,│
   │  audit logs) │ │ (tx graph)   │           │ analysis+    │ │  Gremlin)    │
   │              │ │              │           │  copilot)    │ │              │
   └──────────────┘ └──────────────┘           └──────────────┘ └──────────────┘
```

## Service mapping

| MuleNet piece (today) | AWS service (production) | Why |
|---|---|---|
| `pipeline.run()` detection (networkx/Louvain) | **AWS Lambda** (small banks) or **ECS Fargate** (large graphs) | Stateless, bursty, scales to zero; no servers to manage |
| Transaction graph | **Amazon Neptune** | Managed graph DB; Gremlin queries replace in-memory networkx at scale; fan-in/out & cycles are native graph traversals |
| `dataset.json`, audit artifacts | **Amazon S3** | Durable object storage; audit trail |
| Streaming ingestion | **Amazon Kinesis / MSK** | Real-time transaction feed → near-real-time scoring |
| FastAPI (`api/main.py`) | **API Gateway + Lambda** or **Fargate** | Same code; the app is already ASGI |
| Frontend (static `index.html`/vis-network) | **S3 + CloudFront** | No build step; CDN-served |
| **"Ask MuleNet" copilot + per-account AI analysis** | **Amazon Bedrock (Claude)** | Managed, in-VPC, no data leaves AWS — critical for bank data; tool-use loop maps to Bedrock Converse `toolConfig` |
| Secrets (model keys) | **AWS Secrets Manager** | No keys in code/env |
| Eval / monitoring | **CloudWatch** | Track precision/recall/FP-rate as live SLOs |

## The Bedrock swap (concrete, small)

The AI layer is isolated behind one module, `backend/ai/llm.py`, exposing `complete(messages,
tools, …)`. Today it builds an OpenAI-SDK client pointed at OpenRouter. The Bedrock adapter is
the same function with a `bedrock-runtime` client and the **Converse API**:

```python
import boto3
def complete(messages, tools=None, max_tokens=800, temperature=None):
    client = boto3.client("bedrock-runtime", region_name="eu-central-1")
    resp = client.converse(
        modelId="anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=_to_bedrock(messages),                  # role/content shape
        toolConfig={"tools": _to_bedrock_tools(tools)} if tools else None,
        inferenceConfig={"maxTokens": max_tokens, **({"temperature": temperature} if temperature else {})},
    )
    return _from_bedrock(resp)   # normalize back to our {role, content, tool_calls} dict
```

The copilot's tool-use loop (`list_rings` / `get_ring` / `trace_path` / `compare_rings`) is
provider-agnostic above this line — it consumes our normalized dict — so **only the adapter
changes**. Owner: P5 (it's `ai/` lane).

## What AWS unlocks that local can't

- **Data residency & security:** bank transactions never leave the AWS account; Bedrock runs the
  LLM in-region (EU) — a hard requirement for real financial data and EU AML rules.
- **Scale:** Neptune + Fargate handle millions of transactions; the demo's in-memory graph is the
  same algorithms, just bigger.
- **Real-time:** Kinesis → Lambda gives near-real-time ring scoring instead of batch.
- **Compliance trail:** S3 + CloudTrail give the immutable audit log regulators expect.

## Honest status

- ✅ Architecture is real and the code is already cleanly separated for it.
- ✅ Bedrock swap is a single adapter (interface already abstracted in `ai/llm.py`).
- ⏳ Not wired for the hackathon — we demo locally (no AWS creds provisioned), AI on OpenRouter.
- 🎯 In the pitch: *"Detection is cloud-agnostic graph maths; the AI is Bedrock-ready — one
  adapter — and the production shape is Neptune + Lambda + S3 + Bedrock, all in-VPC so bank data
  never leaves AWS."*
