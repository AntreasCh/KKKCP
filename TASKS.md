# ✅ TASKS — start here (Phase 1 kickoff)

Phase 0 is **done & on `main`**: the app runs end-to-end on `localhost`, schemas are frozen,
`sample_data/` is committed. So **all 5 of us can start in parallel now.**

**Shared scoreboard:** `GET /api/eval`. Baseline today = ring-recall **1.0**, account-precision
**0.023**, **26 false-positive rings**. The goal of Phase 1: **keep ring-recall ~1.0 while driving
false-positive rings toward 0.** Full detail per task in [REQUIREMENTS.md](./REQUIREMENTS.md).

---

## 🟢 Everyone first (10 min)
1. `git pull origin main`
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt`
3. `uvicorn backend.api.main:app --reload --port 8000` → open `http://localhost:8000`, confirm the graph + rings render
4. Read your section of `REQUIREMENTS.md` §13
5. **Claim your block** in `CLAUDE.md` → Team Sync (commit + push that one line)

---

## 👤 P1 — Data & Schemas  · `schemas.py`, `data/generator.py`, `sample_data/`
1. Lock `schemas.py` — change only via a Team Sync heads-up.
2. Richer generator: more varied legit noise, **2–3 instances per pattern**, harder-to-spot rings.
3. *(credibility/AWS-gap)* shape data toward the **IBM AMLSim** format.
- **Done when:** a human can trace one planted ring; dataset feels realistic.

## 👤 P2 — Graph & Structural Detection  · `graph/build.py`, `detect/structural.py`
1. `detect_circular` over-fires on random cycles → add **timestamp-increasing + amount-retention** filter.
2. Tighten `structuring` + `passthrough` thresholds against `/api/eval`.
- **Done when:** detectors fire on planted patterns, not background — FP count drops.

## 👤 P3 — Network Detection & Scoring  · `detect/network.py`, `scoring.py`, `pipeline.py`
1. Add a **temporal window** to fan-in/out (legit high-degree accounts must stop flagging).
2. Score Louvain communities by **flagged-account density**, not raw density.
3. Calibrate scoring normalizer + ring threshold so detected ≈ true rings.
- **Done when:** rings_detected drops from 30 → ~6–10, FP rings → near 0, ring-recall stays high.

## 👤 P4 — API & Frontend  · `api/main.py`, `frontend/`
1. Polish the graph: highlight/cluster rings, edge coloring, legend.
2. Ring detail panel: show the actual transactions + pattern evidence.
3. Prominent eval banner + clean SAR display.
- **Done when:** clicking a ring tells the laundering story at a glance.

## 👤 P5 — AI, Eval & Demo  · `ai/sar.py`, `eval/evaluate.py`, demo
1. **🔴 Get AWS access from the organizers NOW** — gates Bedrock + sponsor points.
2. Verify Bedrock model id; confirm SAR via Bedrock (template fallback already works).
3. Build the **"Ask MuleNet" copilot** endpoint (2nd visible AWS feature — closes the AWS gap).
4. Own eval numbers, the **fixed demo seed**, and the 3-min demo script (REQUIREMENTS §17).
- **Done when:** SAR generates via Claude; `/api/eval` shows the headline metric; demo runs clean twice.
