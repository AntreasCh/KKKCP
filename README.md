# 🕸️ MuleNet — Money-Laundering Network Detector

**Team KKKCP · iFX Hack 2026 · Track: Keep Money Safe**

MuleNet ingests bank transactions, builds a transaction **graph**, and uses graph algorithms +
heuristics to surface money-laundering **rings** (mules, layering, circular flows, structuring).
It scores and visualizes them, and Claude auto-drafts a Suspicious Activity Report per ring.
**~90% deterministic algorithms; the AI only writes the report — it is not a wrapper.**

- 📋 **Full spec & per-person tasks:** [REQUIREMENTS.md](./REQUIREMENTS.md)
- 🤝 **Team workflow / sync:** [CLAUDE.md](./CLAUDE.md)
- 💡 **Idea background:** [IDEAS.md](./IDEAS.md)

## Run it (local only)

```bash
pip install -r backend/requirements.txt
uvicorn backend.api.main:app --reload --port 8000
# open http://localhost:8000
```

The app boots from the committed `sample_data/`. Click **Generate dataset** to make a fresh one.
AI for the SAR is optional: set `ANTHROPIC_API_KEY`, or AWS creds for Bedrock. With neither, the
SAR falls back to a deterministic template — the demo never depends on the network.

## Regenerate the sample dataset

```bash
python -m backend.data.generator --accounts 600 --legit-tx 2500 --rings 6 --seed 42
```

## Layout

```
backend/
  schemas.py          # FROZEN data contracts (REQUIREMENTS §7)
  data/generator.py   # synthetic dataset + labels (P1)
  graph/build.py       # tx list -> networkx graph (P2)
  detect/structural.py # structuring, circular, pass-through (P2)
  detect/network.py    # fan-in/out, Louvain communities (P3)
  detect/scoring.py    # risk scoring + ring assembly (P3)
  detect/pipeline.py   # orchestrator (P3/P4)
  ai/sar.py            # Claude SAR generator + template fallback (P5)
  eval/evaluate.py     # precision/recall vs labels (P5)
  api/main.py          # FastAPI + static frontend (P4)
frontend/              # vis-network UI (P4)
sample_data/           # committed dataset.json + labels.json (P1)
```
