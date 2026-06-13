# 👥 MuleNet — Assignments & Starting Prompts

Canonical owner map for team KKKCP. Live status goes in [TASKS.md](./TASKS.md) → Live Status Board.
Full detail per role in [REQUIREMENTS.md](./REQUIREMENTS.md) §13. Roles are swappable — just keep
**one owner per block**.

| User | Role | Owns (touch only these) | First focus |
|---|---|---|---|
| **kiriakos** | **P1 — Data & Schemas** | `backend/schemas.py`, `backend/data/generator.py`, `sample_data/` | realistic data: 2–3 instances per pattern, AMLSim-shaped, varied noise |
| **panagiotis** | **P2 — Graph & Structural** | `backend/graph/build.py`, `backend/detect/structural.py` | precision: timestamp+amount filters on circular; tighten structuring/passthrough |
| **savvas** | **P3 — Network & Scoring** | `backend/detect/network.py`, `backend/detect/scoring.py`, `backend/detect/pipeline.py` | precision: temporal fan window; community scoring; calibration |
| **BOSS** | **P4 — API & Frontend (+integration)** | `backend/api/main.py`, `frontend/` | graph polish, ring detail panel, wire copilot chat, eval/SAR display, coordinate integration |
| **scriptkiddie** | **P5 — AI + Eval + Demo** | `backend/ai/copilot.py`, `backend/ai/sar.py`, `backend/eval/evaluate.py` | flesh out the tool-using copilot; eval numbers; fixed demo seed + script |

**Shared rules (everyone):**
- AI = **Anthropic API** (`ANTHROPIC_API_KEY`), no AWS. App runs **locally only** (`localhost:8000`).
- `schemas.py` is **frozen** — don't change it without a heads-up in TASKS.md activity log.
- **`git pull --rebase origin main` before you start and before every push.** Small commits.
- Stay in **your** files. Update **your** block in TASKS.md → Live Status Board as you go.
- Scoreboard: `GET /api/eval` — **keep ring-recall ~1.0 while pushing false-positive rings → 0.**

---

## 🚀 Starting prompts (paste into your Claude Code, in the repo root)

### P1 — kiriakos (Data & Schemas)
```text
We're at iFX Hack building MuleNet — a money-laundering network detector (Python + FastAPI +
networkx, vis-network frontend, Anthropic API for the AI). The repo is scaffolded and runs.

I'm kiriakos, owner of P1 — Data & Schemas. Read REQUIREMENTS.md (§7 data contracts, §9 detection
algorithms, §13 P1), TASKS.md (my section + the conflict rules), and CLAUDE.md (git workflow).

Touch ONLY: backend/schemas.py, backend/data/generator.py, sample_data/. schemas.py is the FROZEN
contract — don't change its fields without posting a one-line heads-up in TASKS.md activity log.

Setup: python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt,
then `uvicorn backend.api.main:app --reload --port 8000` and confirm http://localhost:8000 works.

Job: make backend/data/generator.py produce realistic data — more varied legit background traffic,
2–3 planted instances PER pattern (structuring/circular/mule_fanin/mule_fanout/layering), and rings
that are hard but traceable. Shape it toward the IBM AMLSim benchmark format for credibility. Then
regenerate and commit sample_data/dataset.json + labels.json.

Workflow: set my block in TASKS.md to 🟡 and list my files; git pull --rebase before every push;
small commits. Done when a human can trace one planted ring and the dataset feels realistic.
Work autonomously; only ask me if you hit a real decision.
```

### P2 — panagiotis (Graph & Structural Detection)
```text
We're at iFX Hack building MuleNet — a money-laundering network detector (Python + FastAPI +
networkx). The repo is scaffolded and runs.

I'm panagiotis, owner of P2 — Graph & Structural Detection. Read REQUIREMENTS.md (§7 contracts, §9
algorithms #1–#3, §13 P2), TASKS.md (my section + conflict rules), CLAUDE.md (git workflow).

Touch ONLY: backend/graph/build.py, backend/detect/structural.py. Don't change schemas.py or other
people's files without a heads-up in TASKS.md activity log.

Setup: venv + pip install -r backend/requirements.txt, then run uvicorn and confirm localhost:8000.

Job: improve the structural detectors so they fire on planted laundering, not random background.
(1) detect_circular currently over-fires — only flag cycles where timestamps increase around the
loop AND amount is retained (~0.8) within ~72h. (2) Tighten detect_structuring and detect_passthrough.
Measure with GET /api/eval after each change — drive false_positive_rings down, keep ring_recall high.

Workflow: set my block in TASKS.md to 🟡 + list my files; git pull --rebase before every push; small
commits; test against sample_data/. Done when my detectors flag planted patterns, not noise.
Work autonomously; only ask me if blocked on a decision.
```

### P3 — savvas (Network Detection & Scoring)
```text
We're at iFX Hack building MuleNet — a money-laundering network detector (Python + FastAPI +
networkx). The repo is scaffolded and runs. This is the biggest precision lever.

I'm savvas, owner of P3 — Network Detection & Scoring. Read REQUIREMENTS.md (§7 contracts, §9 #4–#5,
§10 scoring, §13 P3), TASKS.md (my section + conflict rules), CLAUDE.md (git workflow).

Touch ONLY: backend/detect/network.py, backend/detect/scoring.py, backend/detect/pipeline.py. Don't
change schemas.py or others' files without a TASKS.md activity-log heads-up.

Setup: venv + pip install -r backend/requirements.txt, then uvicorn, confirm localhost:8000.

Job: (1) add a temporal window to detect_fan so legit high-degree accounts stop flagging; (2) score
Louvain communities by flagged-account density, not raw graph density; (3) calibrate the scoring
normalizer and the ring-score threshold in build_rings so detected rings ≈ true rings. Target via
GET /api/eval: rings_detected drops from ~30 to ~6–10, false_positive_rings near 0, ring_recall ~1.0.

Workflow: set my block in TASKS.md to 🟡 + list my files; git pull --rebase before every push; small
commits; test against sample_data/. Done when the eval shows high ring-recall with few false positives.
Work autonomously; only ask me if blocked on a decision.
```

### P4 — BOSS (API & Frontend + integration)
```text
We're at iFX Hack building MuleNet — a money-laundering network detector (Python + FastAPI backend,
vis-network frontend, Anthropic API). The repo is scaffolded and runs end-to-end on localhost:8000.

I'm BOSS, owner of P4 — API & Frontend, and I coordinate integration. Read REQUIREMENTS.md (§8 API
contract, §13 P4, §17 demo), TASKS.md, CLAUDE.md (git workflow).

Touch mainly: backend/api/main.py, frontend/. The API + UI already work against the pipeline — make
them demo-quality.

Setup: venv + pip install -r backend/requirements.txt, then uvicorn and open localhost:8000.

Job: (1) polish the graph — highlight/cluster detected rings, color suspicious edges, add a legend;
(2) ring detail panel shows the actual transactions + the pattern evidence that proves it; (3) add an
"Ask MuleNet" chat box wired to POST /api/ask (the tool-using copilot) and show its answer; (4) make
the eval banner and SAR output prominent and clean. Keep the API contract in §8 stable (it's what the
others build against) — if it must change, post in TASKS.md activity log first.

Workflow: set my block in TASKS.md to 🟡 + list my files; git pull --rebase before every push; small
commits. Done when clicking a ring tells the laundering story and the copilot chat works.
Work autonomously; flag me on integration blockers.
```

### P5 — scriptkiddie (AI + Eval + Demo)
```text
We're at iFX Hack building MuleNet — a money-laundering network detector. AI is via the Anthropic API
(Claude), NOT Bedrock. The repo is scaffolded and runs on localhost:8000.

I'm scriptkiddie, owner of P5 — AI + Eval + Demo. Read REQUIREMENTS.md (§11 AI layer, §12 eval, §17
demo, §13 P5), TASKS.md, CLAUDE.md (git workflow).

Touch ONLY: backend/ai/copilot.py, backend/ai/sar.py, backend/eval/evaluate.py (+ demo notes). Don't
change schemas.py or others' files without a TASKS.md activity-log heads-up.

Setup: venv + pip install -r backend/requirements.txt; export ANTHROPIC_API_KEY=...; then uvicorn,
confirm localhost:8000.

Job: the substantial piece is the tool-using "Ask MuleNet" copilot (backend/ai/copilot.py, POST
/api/ask) — Claude already calls tools (list_rings/get_ring/get_account) in a loop. Add more tools
(trace_path between two accounts, compare_rings) and return the tool-call trace so the UI can show it
investigating. Confirm the SAR generator works via Anthropic (template fallback already works). Own the
eval numbers (§12), pick a FIXED demo seed, and write the 3-minute demo script (§17). Once that ships
(it's quick), pair with P2/P3 on detection tuning — that's where the real hours are.

Workflow: set my block in TASKS.md to 🟡 + list my files; git pull --rebase before every push; small
commits. Done when the copilot answers by calling tools, SAR drafts a report, and /api/eval prints the
metric. Work autonomously; only ask me if blocked on a decision.
```
