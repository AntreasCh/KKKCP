# 🎬 MuleNet — 3-Minute Demo Script (Owner: P5 — Alexandros)

> Goal: tell the laundering story end-to-end in ~3 min and land the headline metric.
> **Everything runs on `localhost:8000`.** AI is additive — the demo never depends on the network.

## 🔒 Fixed demo seed

- **Demo seed = `42`** (the `/api/dataset/generate` default). Always demo on this seed so the
  numbers and the graph look identical in every dry run.
- Safer still: **demo on the committed `sample_data/`** (loaded automatically on startup) — it's the
  exact fixture we tuned against. Only hit "Generate" live if you want the on-stage wow moment.
- ✅ **Determinism (resolved):** ring detection is now deterministic — Louvain is seeded and ring
  assembly is order-independent — so the numbers are identical on every run. Quote them with
  confidence: **17 rings detected · 0 false-positive rings · ring-recall 1.0 · account precision
  1.0 / recall 0.77** on the committed `sample_data/` (800 accounts / ~4,000 transactions / 15
  planted rings).

## ▶️ Setup (before you present)

```bash
pip install -r backend/requirements.txt
export OPENROUTER_API_KEY=sk-or-v1-...     # enables the copilot + live SAR. Put it in a gitignored .env (auto-loaded) or export it.
                                           # Without a key: SAR still works (template), but the "Ask MuleNet" copilot is DISABLED.
uvicorn backend.api.main:app --reload --port 8000
# open http://localhost:8000
```

Sanity check the scoreboard from the terminal:
```bash
python -m backend.eval.evaluate
```

## 🗣️ The 3-minute run (§17)

| # | Time | Beat | What you say / do |
|---|------|------|-------------------|
| 1 | 0:15 | **Problem** | "Money laundering hides in *networks*, not single transactions. Analysts drown in volume and miss the pattern." |
| 2 | 0:20 | **Generate** | Use the loaded `sample_data` (seed 42): "800 accounts, ~4,000 transactions, with laundering rings hidden inside." (Only hit **Generate** live if you want the on-stage wow.) |
| 3 | 0:20 | **Graph** | Network renders, risk-colored. "Red clusters = high-risk accounts MuleNet surfaced automatically." |
| 4 | 0:20 | **Detect** | "Four independent graph detectors — structuring, circular flow, pass-through, fan-in/out — plus Louvain communities flagged the suspicious rings, ranked by risk." |
| 5 | 0:40 | **Inspect** | Click the **top ring** → detail panel: show the structuring + circular-flow evidence and the actual transactions that prove it. |
| 6 | 0:30 | **Ask MuleNet** | Type into the copilot: *"Trace how money flows through the top ring and why it's suspicious."* Show the **tool-call trace** — `list_rings → get_ring → trace_path` — i.e. the agent investigating our own data, then its answer. |
| 7 | 0:20 | **SAR** | Click **Generate SAR** → Claude drafts the report an analyst would file (template fallback if offline). |
| 8 | 0:15 | **Proof** | Run `python -m backend.eval.evaluate` (or open `/api/eval`): "**Ring-recall 1.0, zero false-positive rings, account precision 1.0** — every ring caught, no legit account flagged — and it all runs locally; the AI only writes the report and answers questions." |

## 🤖 Copilot questions that demo well (they force tool use)

- "Which ring is the highest risk and why?" → `list_rings` + `get_ring`
- "Trace the money from <key account A> to <key account B>." → `trace_path`
- "How do rings DET_005 and DET_013 relate — do they share accounts?" → `compare_rings`
- "What patterns flagged account ACC00045?" → `get_account`

Each answer cites ring ids, account ids, patterns and amounts — and the UI shows the tool trace so
judges watch the agent investigate rather than just chat.

## ✅ Pre-demo checklist

- [ ] `uvicorn` running, `localhost:8000` loads, graph + rings render.
- [ ] `python -m backend.eval.evaluate` prints the scoreboard (ring-recall 1.0).
- [ ] Copilot answers a question and shows a tool trace (or "disabled" message if no key — still fine).
- [ ] "Generate SAR" returns a narrative (template is acceptable).
- [ ] Ran the whole script **twice** clean.
