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
- **Status:** ✅ done — data/labels complete & validated against the latest integrated pipeline
- **Right now:** fixture stands at 800 accts / ~4.1k txns / 15 rings (3 per pattern). Current eval: **ring-recall 1.0, FP-rings 0, acct-precision 1.0** (P3 landed the fan-out fix 👍). Verified labels are honest — the account-recall gap is **not** a labels problem (see heads-up).
- **Files I'm touching:** `backend/data/generator.py`, `sample_data/` (idle — done)
- **Blockers:** —
- **Notes for the team:** `schemas.py` unchanged (frozen). Data has **legit hubs** (business/low-KYC/aged, traffic spread over 30d) + realistic **mule profiles** (fresh accts, elevated KYC, high-risk CC). Labels split full **ring account_ids** (ring-recall) from central **mule_accounts** (precision).
  - **🟡 @P2/@P3 — account-recall 0.359 is detection-side, not labels:** I checked all 25 unflagged "mules" — they're genuine relays/hubs, correctly labeled, just under-scored. Concrete draggers: **`ACC00593` fan-in hub (14 incoming) → risk 0.00**; **`ACC00066`/`ACC00735` structuring hubs → 0.00**; **~11 layering interior relays all stuck at exactly 0.30** (P2's flat passthrough score, just under τ=0.5). Levers: make passthrough score scale with ratio/speed (not flat 0.6), and have `detect_fan`/scoring credit a high in-degree hub even when its burst is partly outside the 48h window. Happy to pair — I won't change labels (they're correct; dropping them would just mask this).
- **Updated:** 2026-06-13

### P2 — panagiotis — Graph & Structural Detection
- **Status:** 🔵 in review
- **Right now:** `detect_circular` rewritten — only fires on time-ordered, value-retaining money loops (timestamps increase around the loop, retention 0.7–1.25, closes ≤72h, length ≥3). On the new fixture it catches **all 3 circular rings, 0 FP**; account precision rose 0.47→0.61. Added `backend/tests/test_structural.py` (5 pass, data-driven).
- **Files I'm touching:** `backend/detect/structural.py`, `backend/tests/test_structural.py`
- **Blockers:** —
- **Notes for the team:** Tuned `CIRC_MIN_RETENTION` to 0.7 — the planted 4-hop loops skim ~6%/hop (~0.78 end-to-end), so 0.8 missed them. My structural signal covers its patterns; the remaining 2 ring-recall misses are the `mule_fanout` assembly gap @kiriakos already flagged to @Andreas (expand fan finding → `evidence.counterparties`). Not editing `graph/build.py` (the MultiDiGraph build is fine as-is).
- **Updated:** 2026-06-13

### P3 — Andreas — Network Detection & Scoring
- **Status:** 🔵 in review — integration pass done
- **Right now:** ring-recall **0.87→1.0 (15/15)**, account precision **0.61→1.0 (0 FP)**, **FP rings →0**, and detection is now **deterministic** (was 11–26 rings run-to-run). 17 tight rings, no mega-blobs.
- **Files I'm touching:** `backend/detect/network.py`, `backend/detect/scoring.py`
- **Blockers:** —
- **Notes for the team:** four changes, all in my files, **no schema/API change**: (1) fanout rings were dropped because spokes carry 0 risk → ring score now blends peak member risk, not just mean; (2) `detect_fan` down-weights legit-hub profiles (business + low-KYC) so payroll/merchant hubs stop flagging — killed all 9 account FPs; (3) `build_rings` is now order-independent + Louvain seeded → stable ring count for the demo; (4) structuring/passthrough seeds expand only to **money-edge** neighbors, which killed the 95-/56-account mega-blobs that were the false-positive rings. **Account recall still 0.359** — next lever is P2's flat-0.6 passthrough score + crediting relay mules; happy to pair.
- **Updated:** 2026-06-13

### P4 — savvas — API & Frontend
- **Status:** 🔵 in review
- **Right now:** full UI redesign — light "analyst console" (Unit21/Sardine style), three-pane layout (ranked ring queue · network graph · tabbed Inspector/Ask-MuleNet), and the graph is now **static** (settles once, then physics off — no perpetual drift). Keeps focus view + flow diagram + evidence + SAR + copilot.
- **Files I'm touching:** `backend/api/main.py`, `frontend/index.html`, `frontend/app.js`, `frontend/style.css`
- **Blockers:** —
- **Notes for the team:** §8 API contract stays stable (only additive `ring` field on /api/graph). Copilot needs `ANTHROPIC_API_KEY` for a live demo; degrades gracefully otherwise.
- **Updated:** 2026-06-13

### P5 — Alexandros — AI, Eval & Demo
- **Status:** 🔵 in review
- **Right now:** copilot tools + trace, eval CLI, SAR confirmed, DEMO.md shipped; ready to pair on P2/P3 detection tuning
- **Files I'm touching:** `backend/ai/copilot.py`, `backend/ai/sar.py`, `backend/eval/evaluate.py`, `DEMO.md`
- **Blockers:** `ANTHROPIC_API_KEY` not set locally → copilot/SAR fall back gracefully (template/disabled); logic still testable offline
- **Notes for the team:** copilot now returns a richer `tool_calls` trace (each entry has `tool`/`input`/`output`) so P4 can render the agent investigating. API contract unchanged.
- **Updated:** 2026-06-13

---

## 2. 🪵 Activity Log  *(append-only — newest at TOP, one line, sign it)*

- _2026-06-13 — P4 (savvas): full UI redesign to a light "analyst console" (Unit21/Sardine style), three-pane layout (ranked ring queue · graph · tabbed Inspector/Ask-MuleNet); graph now settles once then freezes (physics off) so it no longer drifts. Pure frontend; §8 unchanged. — savvas_
- _2026-06-13 — P1 (kiriakos): data ✅ done — confirmed ring-recall 1.0 / FP-rings 0 / acct-precision 1.0 on the integrated pipeline. Audited the acct-recall gap (0.359): all 25 unflagged "mules" are correctly-labeled relays/hubs being under-scored — `ACC00593` fan-in hub (14 in) →0.00, structuring hubs →0.00, ~11 layering relays pinned at 0.30 (<τ). It's detection-side (P2 flat passthrough score + crediting in-degree hubs), not labels — not changing labels (would just mask it). — kiriakos_
- _2026-06-13 — P3 (Andreas): integration pass — ring-recall 0.87→1.0 (15/15, mule_fanout now 3/3), account precision 0.61→1.0 (0 FP), FP rings →0, and detection made DETERMINISTIC (was 11–26 rings/run). Fixes in network.py/scoring.py only, no schema/API change: peak-risk blend in ring score, legit-hub fan down-weight (business+low-KYC), order-independent build_rings + seeded Louvain, money-edge-bounded seed expansion (killed the 95-acct mega-blobs). Account recall still 0.359 → P2 passthrough scoring is the next lever. — Andreas_
- _2026-06-13 — P4 (savvas): graph readability pass — focus view (rings + flagged only) with a "Show all traffic" toggle, labels→hover tooltips, size/opacity hierarchy; plus a per-ring money-flow diagram (source→mule→destination, edge width ∝ amount, top-28 capped) in the detail panel. Pure frontend; §8 unchanged. — savvas_
- _2026-06-13 — P2 (panagiotis): `detect_circular` now fires only on time-ordered, value-retaining money loops (retention 0.7–1.25, ≤72h, len≥3). Catches all 3 circular rings on the new fixture, 0 FP; nudged acct-precision 0.42→0.61. Added `backend/tests/` (data-driven, 5 pass). Remaining ring-recall gap is the `mule_fanout` assembly issue @kiriakos already flagged to @Andreas. — panagiotis_
- _2026-06-13 — P4 (savvas): starting demo-quality UI pass — graph ring highlighting + legend, richer ring detail panel (transactions + pattern evidence), "Ask MuleNet" chat wired to /api/ask with tool-call trace, prominent eval/SAR display. §8 API contract unchanged. — savvas_
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
