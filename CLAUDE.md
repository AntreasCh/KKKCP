# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

It is **also our team's live sync document** for iFX Hack 2026. Read the workflow rules
below — following them is how we avoid git conflicts.

**How we work:** all **5 of us** run **Claude Code individually** on our own machines, one
feature per person. There's **no shared server** — everything runs **locally** (see below).

---

## 🎯 Project

- **Team:** KKKCP
- **Event:** iFX Hack 2026 — 24h hackathon, 13–14 June, University of Limassol (Cyprus)
- **Track:** **Keep Money Safe** (fraud / scams / financial crime / AML / consumer protection)
- **Sponsor:** AWS — using AWS services (Bedrock, Rekognition, Textract, etc.) is a plus.
- **Project:** **MuleNet** — money-laundering network detector (decided 2026-06-13). Full spec + per-person tasks: **[REQUIREMENTS.md](./REQUIREMENTS.md)**.
- **Submission deadline:** **Sun 14 June, 12:00 (noon).** Presentations 14:00–15:30.
- **Repo:** https://github.com/AntreasCh/KKKCP
- **Idea options & decision:** see [`IDEAS.md`](./IDEAS.md)

Judges score on: Innovation & Creativity · Technical Execution · Functionality & Demo ·
Problem Solving · Industry Impact. **Keep a working demo path green at all times.**

---

## 🚦 Git workflow — READ THIS (this is how we avoid conflicts)

Conflicts happen when two people change **the same lines** and push without syncing.
These four habits prevent ~all of them:

**1. Pull before you start working — every time.**
```bash
git pull --rebase origin main
```

**2. Commit small and often.** Small commits = tiny, easy-to-resolve conflicts.
```bash
git add <only-your-files>
git commit -m "clear message about what changed"
```

**3. Pull again right before you push, then push.**
```bash
git pull --rebase origin main   # bring in teammates' work first
git push origin main
```

**4. Own your area.** Don't edit a file someone else is actively working in. Claim files in
the **Team Sync** section below so we don't collide. One feature → one person (or one
branch).

### Editing THIS file (CLAUDE.md) without conflicts
- **Only edit your own block** under *Team Sync*. Never touch a teammate's block.
- **Decision Log** is *append-only*: add a new line at the **top** of the list, never rewrite
  existing lines.
- Commit CLAUDE.md changes on their own (`git commit -m "sync: <your update>"`) and push
  immediately — don't let edits sit.

### If you DO get a conflict (don't panic)
```bash
# After a pull that reports a conflict in <file>:
# 1. Open <file>, find the <<<<<<< ======= >>>>>>> markers.
# 2. Keep both people's work (merge by hand), delete the marker lines.
# 3. Then:
git add <file>
git rebase --continue      # if you were rebasing
git push origin main
```
Stuck? Ping the team before forcing anything. **Never** `git push --force` to `main`.

---

## 🧱 Tech stack & commands

> 🖥️ **Runs locally only — we have no server to host on.** The whole app (and the demo)
> must run on each person's own machine via `localhost`. **Don't** add hosting, deploys, or
> anything that needs a live remote server to demo. Calling cloud **APIs** (e.g. AWS Bedrock)
> from the local app is fine — that's a remote call, not a server we run.

- **Language / framework:** Python 3.11+ · FastAPI + uvicorn (backend) · vis-network (frontend, no build step)
- **Graph / detection:** `networkx`, `python-louvain`, `numpy`, `pandas`
- **Install deps:** `pip install -r backend/requirements.txt`
- **Run locally (localhost):** `uvicorn backend.api.main:app --reload --port 8000` → open `http://localhost:8000`
- **Run tests:** `pytest backend/` (add as we go)
- **AI layer:** **Anthropic API** (Claude, `claude-haiku-4-5`, set `MULENET_MODEL` to change) — powers the SAR generator **and** the tool-using "Ask MuleNet" copilot. Needs `ANTHROPIC_API_KEY`. Optional AWS Bedrock fallback; deterministic template fallback so the demo never needs the network.

---

## 👥 Team Sync

> Edit **only your own block.** Update "Working on" and "Status" as you go. This is how we
> see who's touching what and avoid stepping on each other. **5 people, 5 blocks** — claim
> a feature/area so two of us never run Claude Code on the same files.
>
> **P1–P5 below are a proposed starting mapping — swap roles freely, just keep one owner per
> block. Your detailed first tasks are in [TASKS.md](./TASKS.md).**
>
> 📍 **Live status (who's doing what right now) lives in [TASKS.md](./TASKS.md) → Live Status
> Board — update there, not here. The blocks below are just the durable role assignment.**

### Andreas Christodoulou (@AntreasCh) — proposed **P1: Data & Schemas**
- **Working on:** synthetic data generator; harden realism + AMLSim-shaped data (TASKS.md)
- **Files/area owned:** `backend/schemas.py`, `backend/data/generator.py`, `sample_data/`
- **Status:** not started
- **Blockers:** —

### Panayiotis (@pkonto04) — proposed **P2: Graph & Structural Detection**
- **Working on:** cut false positives in structuring / circular / pass-through detectors
- **Files/area owned:** `backend/graph/build.py`, `backend/detect/structural.py`
- **Status:** not started
- **Blockers:** —

### Savvas Kattimeris — proposed **P3: Network Detection & Scoring**
- **Working on:** temporal fan detection, Louvain ring scoring, scoring calibration
- **Files/area owned:** `backend/detect/network.py`, `backend/detect/scoring.py`, `backend/detect/pipeline.py`
- **Status:** not started
- **Blockers:** —

### (claim — add your name) — proposed **P4: API & Frontend**
- **Working on:** graph polish, ring detail panel, SAR + eval display
- **Files/area owned:** `backend/api/main.py`, `frontend/`
- **Status:** not started
- **Blockers:** —

### (claim — add your name) — proposed **P5: AI, Eval & Demo**
- **Working on:** Bedrock SAR + "Ask MuleNet" copilot, eval numbers, demo script; **get AWS access**
- **Files/area owned:** `backend/ai/sar.py`, `backend/eval/evaluate.py`, demo
- **Status:** not started
- **Blockers:** needs AWS/Bedrock access from organizers

---

## 📋 Decision Log (newest at top — append only)

- _2026-06-13 — **AI layer = Anthropic API (not Bedrock).** Powers the SAR + a tool-using "Ask MuleNet" copilot (an agent over our findings — not a wrapper). Model `claude-haiku-4-5`, set `MULENET_MODEL` to change; Bedrock kept as optional fallback. P5 no longer blocked on AWS — needs `ANTHROPIC_API_KEY`._
- _2026-06-13 — **Project decided: MuleNet** (AML money-laundering network detector). Stack: Python + FastAPI + networkx + vis-network; Claude (Bedrock) for SAR only. Full spec + 5-person split in [REQUIREMENTS.md](./REQUIREMENTS.md). Each person: claim a block in Team Sync above._
- _2026-06-13 — Decided: app runs **locally only** (no server to host on); demo runs on localhost. Team of **5**, each running Claude Code individually — one feature/area per person._
- _2026-06-13 — Repo set up; idea options drafted in `IDEAS.md`; awaiting team vote on track idea._
