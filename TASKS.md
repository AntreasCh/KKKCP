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

### P1 — kiriakos — Data & Schemas
- **Status:** 🔵 in review (data done; one ring-recall gap is P3-side, see heads-up)
- **Right now:** committed richer fixture — 800 accts / ~4.1k txns / 15 rings (3 per pattern). Eval on it: **ring-recall 0.87, FP-rings 1, acct-precision 0.42** (vs Phase-0 baseline recall 1.0 but precision 0.023 / 26 FP-rings — the old 1.0 was trivial; everything was flagged).
- **Files I'm touching:** `backend/data/generator.py`, `sample_data/`
- **Blockers:** —
- **Notes for the team:** `schemas.py` unchanged (still frozen). New data adds **legit hubs** (employers/merchants/utilities: business + low-KYC + old accounts, traffic spread over 30d) and gives **mule centres** a realistic profile (fresh accounts, elevated KYC, high-risk jurisdiction) — a fair signal to separate payroll fan-out from mules. Labels split **ring account_ids** (full set, for ring-recall) from **mule_accounts** (central/relay only).
  - **🔴 @P3 (Andreas):** the 2 missed rings are both `mule_fanout`. `detect_fan` correctly emits a `fan_out` finding (score ~0.9) but only the **hub** is in `subject_ids`; the spokes sit in `evidence.counterparties`. `build_rings` assembles from flagged accounts only → detected ring = `{hub}` → <60% overlap → miss. **Fix:** when seeding a ring from a fan finding, pull in `evidence.counterparties`. That alone should push ring-recall back to ~1.0.
- **Updated:** 2026-06-13

### P2 — panagiotis — Graph & Structural Detection
- **Status:** 🔵 in review
- **Right now:** `detect_circular` rewritten — only fires on time-ordered, value-retaining money loops (timestamps increase around the loop, retention 0.7–1.25, closes ≤72h, length ≥3). On the new fixture it catches **all 3 circular rings, 0 FP**; account precision rose 0.47→0.61. Added `backend/tests/test_structural.py` (5 pass, data-driven).
- **Files I'm touching:** `backend/detect/structural.py`, `backend/tests/test_structural.py`
- **Blockers:** —
- **Notes for the team:** Tuned `CIRC_MIN_RETENTION` to 0.7 — the planted 4-hop loops skim ~6%/hop (~0.78 end-to-end), so 0.8 missed them. My structural signal covers its patterns; the remaining 2 ring-recall misses are the `mule_fanout` assembly gap @kiriakos already flagged to @Andreas (expand fan finding → `evidence.counterparties`). Not editing `graph/build.py` (the MultiDiGraph build is fine as-is).
- **Updated:** 2026-06-13

### P3 — Andreas — Network Detection & Scoring
- **Status:** 🟡 core pass done (will finalize after P2's circular fix)
- **Right now:** done first pass — rings 30→7, FP rings 26→3, ring-recall 1.0
- **Files I'm touching:** `backend/detect/network.py`, `backend/detect/scoring.py`
- **Blockers:** residual FP / ring-bloat is circular-driven → needs **P2** (panagiotis) circular timestamp+amount filter
- **Notes for the team:** detect_fan is now account-type (hub in subject_ids, counterparties in evidence) — still a valid Finding, no schema change. Rings are built from strong-detector seeds + tx volume (≥€15k) with a €5k money-edge filter; community detection is context-only now.
- **Updated:** 2026-06-13

### P4 — savvas — API & Frontend
- **Status:** 🔲 not started
- **Right now:** —
- **Files I'm touching:** `backend/api/main.py`, `frontend/`
- **Blockers:** —
- **Notes for the team:** —
- **Updated:** —

### P5 — Alexandros — AI, Eval & Demo
- **Status:** 🔵 in review
- **Right now:** copilot tools + trace, eval CLI, SAR confirmed, DEMO.md shipped; ready to pair on P2/P3 detection tuning
- **Files I'm touching:** `backend/ai/copilot.py`, `backend/ai/sar.py`, `backend/eval/evaluate.py`, `DEMO.md`
- **Blockers:** `ANTHROPIC_API_KEY` not set locally → copilot/SAR fall back gracefully (template/disabled); logic still testable offline
- **Notes for the team:** copilot now returns a richer `tool_calls` trace (each entry has `tool`/`input`/`output`) so P4 can render the agent investigating. API contract unchanged.
- **Updated:** 2026-06-13

---

## 2. 🪵 Activity Log  *(append-only — newest at TOP, one line, sign it)*

- _2026-06-13 — P2 (panagiotis): `detect_circular` now fires only on time-ordered, value-retaining money loops (retention 0.7–1.25, ≤72h, len≥3). Catches all 3 circular rings on the new fixture, 0 FP; nudged acct-precision 0.42→0.61. Added `backend/tests/` (data-driven, 5 pass). Remaining ring-recall gap is the `mule_fanout` assembly issue @kiriakos already flagged to @Andreas. — panagiotis_
- _2026-06-13 — P1 (kiriakos): shipped richer fixture (800 accts / 4.1k txns / 15 rings, 3 per pattern) + legit hubs (payroll/merchant/utility) + realistic mule profiles. Eval: ring-recall 0.87, FP-rings 26→1, acct-precision 0.023→0.42. 🔴 @P3: 2 missed rings are `mule_fanout` — `build_rings` should expand a fan finding to its `evidence.counterparties` (spokes), which lifts recall back to ~1.0. schemas.py untouched. — kiriakos_
- _2026-06-13 — P1 (kiriakos): starting richer generator — 2–3 instances/pattern, realistic legit noise + legit hubs, AMLSim-aligned typologies; labels split ring-set vs mule-set. schemas.py untouched. — kiriakos_
- _2026-06-13 — P5: copilot gains `trace_path` + `compare_rings` tools and returns a richer `tool_calls` trace (tool/input/output) for the UI; eval gains `format_report` + `python -m backend.eval.evaluate` CLI and additive `false_positive_rate`; SAR Anthropic+template paths confirmed; demo seed fixed at 42, `DEMO.md` added. Heads-up @P3: Louvain is non-deterministic → ring count drifts run-to-run (~24–26 FP); seeding it would stabilise demo numbers. — Alexandros_
- _2026-06-13 — P3 (Andreas): temporal fan window + hub-centric risk + money/volume ring assembly → rings 30→7, false-positive rings 26→3, ring-recall held at 1.0. Residual FP/bloat is circular over-detection — drops further once P2's circular timestamp/amount filter lands. — Andreas_
- _2026-06-13 — Phase 0 scaffold landed: app runs end-to-end, contracts frozen, sample_data committed. Baseline `/api/eval`: ring-recall 1.0, precision 0.023, 26 FP rings. — Claude_

---

## 3. 🔗 Parallelism — everyone can start NOW

Phase 0 made the only hard dependency (data contract + sample data) a committed artifact, so all
five tasks are independently startable. The only soft coupling: P3's eval numbers improve as P2's
detectors improve — not blocking (frozen `Finding` interface + working stubs). Build against
`sample_data/`; improvements compose automatically.

**Shared goal / scoreboard:** `GET /api/eval` — **keep ring-recall ~1.0 while driving
false-positive rings → 0.**

> 🧑‍🤝‍🧑 **Using 5 people well (when code-gen is fast):** Claude Code makes *typing* fast, so the
> bottleneck isn't lines of code — it's the **judgment-heavy, iterative** work that agents don't
> shortcut: tuning detection against the eval, making the data realistic, making the viz genuinely
> good, designing the copilot's tools. The biggest time-sink is **detection precision (P2+P3)** —
> run → measure → adjust, many times. So once the faster tracks (P5 AI, P4 UI shell, P1 data) hit
> "good enough", **those people pile onto P2/P3 tuning and demo polish.** Spend the 5 on *depth and
> quality*, not on splitting boilerplate.

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

### P5 — AI, Eval & Demo · `ai/copilot.py`, `ai/sar.py`, `eval/evaluate.py`, demo
**AI = Anthropic API (Claude), not Bedrock.** Set `ANTHROPIC_API_KEY`.
1. Build out the **"Ask MuleNet" copilot** (`ai/copilot.py`, `POST /api/ask`) — the substantial,
   non-wrapper piece: Claude calls tools (`list_rings`/`get_ring`/`get_account`) to investigate.
   Add more tools (`trace_path`, `compare_rings`), surface the tool-call trace in the UI.
2. Confirm the SAR generator works via Anthropic (template fallback already works).
3. Own eval numbers, the **fixed demo seed**, and the 3-min demo script (REQUIREMENTS §17).
4. Once 1–2 ship (fast), **pair with P2/P3 on detection tuning** — that's where the real hours are.
- **Done when:** copilot answers by calling tools; SAR drafts a report; `/api/eval` shows the metric; demo runs clean twice.
