# ✅ TASKS — Live Board & Phase 1 Kickoff

> 🧠 **THIS FILE IS OUR SHARED MEMORY.** Update it as you work so every teammate (and their
> Claude Code) sees who is doing what, right now.
>
> **Conflict rules (so this file never blocks us):**
> 1. **Edit ONLY your own status block** in §1 — different lines = no conflicts.
> 2. **Activity Log (§2) is append-only** — add your line at the **TOP**, keep it to one line, sign it.
> 3. **`git pull --rebase origin main` before every push.** Commit status updates on their own and push immediately.
> 4. Put what files you're touching in **"Files I'm touching"** so nobody opens the same file.

Status legend: 🔲 not started · 🟡 in progress · 🔵 in review · ✅ done · 🔴 blocked

---

## 1. 📊 Live Status Board  *(edit ONLY your block)*

### P1 — Andreas — Data & Schemas
- **Status:** 🔲 not started
- **Right now:** —
- **Files I'm touching:** `backend/schemas.py`, `backend/data/generator.py`, `sample_data/`
- **Blockers:** —
- **Notes for the team:** —
- **Updated:** —

### P2 — Panayiotis — Graph & Structural Detection
- **Status:** 🔲 not started
- **Right now:** —
- **Files I'm touching:** `backend/graph/build.py`, `backend/detect/structural.py`
- **Blockers:** —
- **Notes for the team:** —
- **Updated:** —

### P3 — Savvas — Network Detection & Scoring
- **Status:** 🔲 not started
- **Right now:** —
- **Files I'm touching:** `backend/detect/network.py`, `backend/detect/scoring.py`, `backend/detect/pipeline.py`
- **Blockers:** —
- **Notes for the team:** —
- **Updated:** —

### P4 — (claim) — API & Frontend
- **Status:** 🔲 not started
- **Right now:** —
- **Files I'm touching:** `backend/api/main.py`, `frontend/`
- **Blockers:** —
- **Notes for the team:** —
- **Updated:** —

### P5 — (claim) — AI, Eval & Demo
- **Status:** 🔲 not started
- **Right now:** —
- **Files I'm touching:** `backend/ai/sar.py`, `backend/eval/evaluate.py`
- **Blockers:** 🔴 needs AWS/Bedrock access from organizers
- **Notes for the team:** —
- **Updated:** —

---

## 2. 🪵 Activity Log  *(append-only — newest at TOP, one line, sign it)*

- _2026-06-13 — Phase 0 scaffold landed: app runs end-to-end, contracts frozen, sample_data committed. Baseline `/api/eval`: ring-recall 1.0, precision 0.023, 26 FP rings. — Claude_

---

## 3. 🔗 Parallelism — everyone can start NOW

Phase 0 made the only hard dependency (data contract + sample data) a committed artifact, so all
five tasks are independently startable. The only soft coupling: P3's eval numbers improve as P2's
detectors improve — not blocking (frozen `Finding` interface + working stubs). Build against
`sample_data/`; improvements compose automatically.

**Shared goal / scoreboard:** `GET /api/eval` — **keep ring-recall ~1.0 while driving
false-positive rings → 0.**

---

## 4. 🟢 Everyone first (10 min)
1. `git pull origin main`
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt`
3. `uvicorn backend.api.main:app --reload --port 8000` → open `http://localhost:8000`, confirm graph + rings render
4. Read your section of `REQUIREMENTS.md` §13
5. Set your block above to 🟡 and push

---

## 5. First tasks per agent  *(full detail in [REQUIREMENTS.md](./REQUIREMENTS.md) §13)*

### P1 — Data & Schemas · `schemas.py`, `data/generator.py`, `sample_data/`
1. Lock `schemas.py` — change only via an Activity Log heads-up.
2. Richer generator: more varied legit noise, **2–3 instances per pattern**, harder-to-spot rings.
3. *(credibility/AWS-gap)* shape data toward the **IBM AMLSim** format.
- **Done when:** a human can trace one planted ring; dataset feels realistic.

### P2 — Graph & Structural Detection · `graph/build.py`, `detect/structural.py`
1. `detect_circular` over-fires on random cycles → add **timestamp-increasing + amount-retention** filter.
2. Tighten `structuring` + `passthrough` thresholds against `/api/eval`.
- **Done when:** detectors fire on planted patterns, not background — FP count drops.

### P3 — Network Detection & Scoring · `detect/network.py`, `scoring.py`, `pipeline.py`
1. Add a **temporal window** to fan-in/out (legit high-degree accounts must stop flagging).
2. Score Louvain communities by **flagged-account density**, not raw density.
3. Calibrate scoring normalizer + ring threshold so detected ≈ true rings.
- **Done when:** rings_detected drops from 30 → ~6–10, FP rings → near 0, ring-recall stays high.

### P4 — API & Frontend · `api/main.py`, `frontend/`
1. Polish the graph: highlight/cluster rings, edge coloring, legend.
2. Ring detail panel: show the actual transactions + pattern evidence.
3. Prominent eval banner + clean SAR display.
- **Done when:** clicking a ring tells the laundering story at a glance.

### P5 — AI, Eval & Demo · `ai/sar.py`, `eval/evaluate.py`, demo
1. **🔴 Get AWS access from the organizers NOW** — gates Bedrock + sponsor points.
2. Verify Bedrock model id; confirm SAR via Bedrock (template fallback already works).
3. Build the **"Ask MuleNet" copilot** endpoint (2nd visible AWS feature — closes the AWS gap).
4. Own eval numbers, the **fixed demo seed**, and the 3-min demo script (REQUIREMENTS §17).
- **Done when:** SAR generates via Claude; `/api/eval` shows the headline metric; demo runs clean twice.
