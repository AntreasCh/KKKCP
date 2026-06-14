# 🕸️ MuleNet — Money-Laundering Network Detector

**Team KKKCP · iFX Hack 2026 · Track: Keep Money Safe**

MuleNet ingests bank transactions, builds a transaction **graph**, and runs a **multi-tier
detection pipeline** — structural typologies (structuring, layering, circular flows, fan-in/out),
network/community analysis, behavioural & profile signals, and **crypto-wallet exposure** — to
score accounts and surface money-laundering **rings** and mules. High-risk accounts (**≥0.90**)
auto-freeze for review; an **operator console** lets analysts browse accounts, open a per-account
**Visual Review** graph, run an **AI analysis**, and ask the **Ask MuleNet** copilot.
**~90% deterministic algorithms; the AI assists analysis — it is not load-bearing.**

- 📋 **Full spec & per-person tasks:** [REQUIREMENTS.md](./REQUIREMENTS.md)
- 🤝 **Team workflow / sync:** [CLAUDE.md](./CLAUDE.md)
- 💡 **Idea background:** [IDEAS.md](./IDEAS.md)

## Run it (local only)

```bash
pip install -r backend/requirements.txt
uvicorn backend.api.main:app --reload --port 8000
# open http://localhost:8000
```

The app boots from the committed `sample_data/` into the operator console. Click **Generate** for
a fresh dataset. The AI features (per-account analysis + **Ask MuleNet** copilot) are optional: set
`OPENROUTER_API_KEY` in a gitignored `.env`. Without it they fall back to templates — detection is
fully deterministic and never depends on the network.

## Regenerate the sample dataset

```bash
python -m backend.data.generator --seed 42   # defaults: 800 accounts, 4000 legit tx, 15 rings + kingpin + hard-negative decoys
```

## Layout

```
backend/
  schemas.py           # data contracts (P1)
  data/generator.py    # synthetic dataset + labels (P1)
  graph/build.py        # tx list -> networkx graph (P2)
  detect/structural.py  # structuring, circular, pass-through (P2)
  detect/network.py     # fan-in/out, Louvain communities (P3)
  detect/temporal.py    # time-based behavioural signals
  detect/kyc.py         # KYC / profile signals
  detect/crypto.py      # crypto-wallet exposure (mixer/darknet/high-risk)
  detect/scoring.py     # risk scoring + ring assembly (P3)
  detect/pipeline.py    # orchestrator
  ai/analysis.py        # per-account AI analysis (P5)
  ai/copilot.py         # "Ask MuleNet" tool-using copilot (P5)
  ai/llm.py             # provider adapter (OpenRouter / OpenAI)
  eval/evaluate.py      # precision/recall vs labels
  api/main.py           # FastAPI + static frontend (P4)
frontend/               # operator console + Visual Review graph (vis-network) (P4)
sample_data/            # committed dataset.json + labels.json (P1)
```
