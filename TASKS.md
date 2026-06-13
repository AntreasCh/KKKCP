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
- **Status:** ✅ done — decoy stress-test tool added; committed fixture kept clean (build stays green)
- **Right now:** generator gains `--decoys` (legit hard-negatives that mimic laundering). **Committed `sample_data/` stays decoy-free (`--decoys 0`)** so P3's just-landed `precision==1.0` tests + the demo don't break. Clean fixture eval unchanged: ring-recall 1.0, FP-rings 0, precision 1.0, recall 0.77 (P3's recalibration 👍).
- **Files I'm touching:** `backend/data/generator.py`, `sample_data/` (done)
- **Blockers:** —
- **Notes for the team:** `schemas.py` frozen. Ran `--decoys 8` as a precision stress-test (4 kinds: payday payroll burst, merchant flash-sale fan-in, sub-threshold B2B invoices, inter-company settlement loop; all stamped business + low-KYC + aged as the fair separating signal, never labelled). Detectors are **robust** to payroll/merchant/B2B 👍 — only 2 gaps surfaced:
  - **🟡 @P2 (circular):** legit **settlement loops** (3 business/low-KYC/aged accts, value-retaining, ≤72h) read as laundering cycles → 2 FP rings. Lever: down-weight cycles whose members are *all* established business + low-KYC, or require ≥1 fresh/high-risk account in the loop.
  - **🟡 @P3 (fan):** a legit mega-merchant (in=278, low-KYC, aged) still trips `fan_in` (risk 0.81) — the legit-hub down-weight needs to bite harder at very high degree.
  - **Proposal:** once you two harden these + bump the guardrail thresholds, I flip `--decoys` ON in the committed fixture so our precision is *earned*. Say the word.
- **Updated:** 2026-06-13

### P2 — panagiotis — Graph & Structural Detection
- **Status:** 🔵 in review
- **Right now:** `detect_circular` rewritten — only fires on time-ordered, value-retaining money loops (timestamps increase around the loop, retention 0.7–1.25, closes ≤72h, length ≥3). On the new fixture it catches **all 3 circular rings, 0 FP**; account precision rose 0.47→0.61. Added `backend/tests/test_structural.py` (5 pass, data-driven).
- **Files I'm touching:** `backend/detect/structural.py`, `backend/tests/test_structural.py`
- **Blockers:** —
- **Notes for the team:** Tuned `CIRC_MIN_RETENTION` to 0.7 — the planted 4-hop loops skim ~6%/hop (~0.78 end-to-end), so 0.8 missed them. My structural signal covers its patterns; the remaining 2 ring-recall misses are the `mule_fanout` assembly gap @kiriakos already flagged to @Andreas (expand fan finding → `evidence.counterparties`). Not editing `graph/build.py` (the MultiDiGraph build is fine as-is).
- **Updated:** 2026-06-13

### P3 — Andreas — Network Detection & Scoring
- **Status:** 🔵 in review — scoring recalibration done
- **Right now:** **account recall 0.359→0.769 (14→30/39), precision held 1.000 (0 FP), F1 0.528→0.870**; ring-recall stays 1.0, 0 FP rings, 17 rings. Root-caused the recall gap: scoring NORMALIZER (1.6) demanded *two* corroborating signals, so single-role mules (a pure relay, one circular loop, one fan-out) stalled below τ=0.5 — 10 passthrough relays pinned at exactly 0.30, etc. Recalibrated to 0.9 (a single proven typology now crosses τ). **Safe by construction:** the strong detectors (structuring/circular/passthrough) fire on **0 legit accounts** on this fixture, and worst-case legit weighted-sum (~0.24, factor-suppressed fan) stays far below τ — verified the sweep keeps precision 1.0 down to NORM=0.7.
- **Files I'm touching:** `backend/detect/network.py`, `backend/detect/scoring.py`, `backend/tests/test_scoring.py` (new)
- **Blockers:** —
- **Notes for the team:** one-line change in `scoring.py` (`NORMALIZER 1.6→0.9`, **no schema/API change** — risk values just rise, contract identical) + new `test_scoring.py` (4 integrated guardrails: precision==1.0, recall≥0.74, ring-recall==1.0, 0 FP rings; locks this in against regression). **Remaining 9 FNs are no-detector-fires:** 4 fan-in *collectors* (receive a big sum from <5 senders → fan threshold never trips), 3 `structuring` accounts whose deposits fall outside P2's [0.7T,T)/72h band, 2 isolated fan-out. To get past 0.77 I'd add a **consolidation/high-value-collector signal** in `network.py` (my lane) — but it risks legit FPs, so I'm pausing here at the clean precision-1.0 story unless we want to push it. @P2: the structuring-band misses (ACC00066/143/735) are yours if you want them.
- **Updated:** 2026-06-13

### P4 — savvas — API & Frontend
- **Status:** 🔵 in review
- **Right now:** advanced data filtering + human detail — new **Accounts table** view (toggle with the graph; owner/type/country/KYC/flags/rings/risk, sortable) and a shared **Filters drawer** (text, risk, type, KYC, country, channel, amount, date) that applies to BOTH the table and the graph; owner names now surface in tooltips, an optional "Names" graph toggle, and ring key-accounts/transactions. Builds on playback/case/search/breakdown.
- **Files I'm touching:** `backend/api/main.py`, `frontend/index.html`, `frontend/app.js`, `frontend/style.css`
- **Blockers:** —
- **Notes for the team:** §8 stays stable — **additive only**: `/api/graph` nodes now also carry `owner_name/country/kyc_risk`, edges carry `channel/timestamp`; new `GET /api/accounts` (full list w/ risk, rings, n_findings). Kept P5's account AI-analysis additions intact.
- **Updated:** 2026-06-13

### P5 — Alexandros — AI, Eval & Demo
- **Status:** 🟡 in progress — added account AI-analysis feature
- **Right now:** new `backend/ai/llm.py` unified provider (auto-detects OpenAI vs OpenRouter from key prefix; OpenRouter reasoning on); new `backend/ai/analysis.py` one-shot account analysis (subject + connected accounts → LLM verdict, template fallback). Copilot + SAR now route through `llm.py` too.
- **Files I'm touching:** `backend/ai/copilot.py`, `backend/ai/sar.py`, `backend/ai/llm.py`, `backend/ai/analysis.py`, `backend/eval/evaluate.py`, `DEMO.md` — **+ additive edits to `backend/api/main.py` & `frontend/` (heads-up below)**
- **Blockers:** —
- **Notes for the team:**
  - **🟡 @P4 (savvas):** I made **additive** changes to your files for the account-analysis feature — new route `POST /api/accounts/{id}/analyze` in `api/main.py`, and in `frontend/` an "🔍 AI analysis" button in the account inspector (`showAccount`) + a `runAccountAnalysis()` handler + `.ai-*` CSS. No existing endpoint/markup changed; pull before your next push to avoid a conflict. Ping me if you'd rather own the frontend bit.
  - AI provider is now **auto-detected from the key**: `sk-or-…` → OpenRouter, `sk-…` → OpenAI. Same `OPENROUTER_API_KEY`/`OPENAI_API_KEY` var.
- **Updated:** 2026-06-13

---

## 2. 🪵 Activity Log  *(append-only — newest at TOP, one line, sign it)*

- _2026-06-13 — P4 (savvas): advanced data filtering + human detail — new **Accounts table** view (toggle w/ graph; owner/type/country/KYC/flags/rings/risk, sortable) + a shared **Filters drawer** (text/risk/type/KYC/country/channel/amount/date) applying to both table and graph; owner names in node tooltips, a "Names" graph toggle, and ring key-accounts/transactions. **Additive API:** `/api/graph` nodes +owner_name/country/kyc_risk, edges +channel/timestamp; new `GET /api/accounts`. §8 otherwise unchanged; P5's AI-analysis kept. — savvas_
- _2026-06-13 — P3 (Andreas): added **`READINESS.md`** (winning plan: scoring-criteria + per-judge analysis, prioritized gap list, 3-min script, Q&A prep) and **`AWS_DEPLOYMENT.md`** (production architecture + the Bedrock-swap story for the AWS judge). **🟡 @P5 (Alexandros) heads-up:** I refreshed **`DEMO.md`** (your file — corrected stale bits: OpenRouter key not Anthropic, 800/4k counts not 600/2.5k, determinism-resolved note). Doc-only, no `ai/` code touched. **Two P0s for you:** (1) set `OPENROUTER_API_KEY` in `.env` — the copilot is currently disabled; (2) optional Bedrock adapter in `ai/llm.py` for the AWS judge (one function, spec in AWS_DEPLOYMENT.md). — Andreas_
- _2026-06-13 — P3 (Andreas): **account recall 0.359→0.769, precision held 1.0, F1 →0.870**; ring metrics unchanged (recall 1.0, 0 FP rings). Root cause: scoring NORMALIZER=1.6 required two corroborating signals so single-role mules (10 passthrough relays @0.30, fan/circular-only) stalled under τ — recalibrated to 0.9. Safe: strong detectors fire on 0 legit accts; verified precision stays 1.0 down to NORM=0.7. Added `backend/tests/test_scoring.py` (4 guardrails). `scoring.py` only, no schema/API change. Remaining 9 FNs are no-detector-fire collectors/structuring-band misses. — Andreas_
- _2026-06-13 — P1 (kiriakos): added **hard-negative decoys** to the generator (`--decoys`, 4 kinds: payday payroll burst, merchant flash-sale fan-in, sub-threshold B2B invoices, inter-company settlement loop — unlabelled, so flags = true FPs). **Committed fixture kept CLEAN (`--decoys 0`) so P3's new `precision==1.0` guardrails + the demo stay green.** Stress run (`--decoys 8`) shows detection is robust except 2 gaps → **@P2** circular fires on legit settlement loops, **@P3** legit mega-merchant `ACC00739` (in=278) trips `fan_in`. Proposing we flip decoys ON in the fixture once P2/P3 harden + bump their guardrail thresholds. — kiriakos_
- _2026-06-13 — P5 (Alexandros): AI is now **OpenRouter-only** (per request) via the OpenAI SDK pointed at OpenRouter, reasoning enabled, key read from gitignored `.env`. **⚠️ Added `openai` to `backend/requirements.txt` → run `pip install -r backend/requirements.txt`.** Bad-key 401s fall back to template (analysis) / show a hint (copilot). — Alexandros_
- _2026-06-13 — P5 (Alexandros): account AI-analysis feature — click an account → one-shot LLM verdict over it + its connected accounts (`ai/analysis.py`), new route `POST /api/accounts/{id}/analyze`, "🔍 AI analysis" button in the inspector. New `ai/llm.py` auto-detects provider from key (sk-or-→OpenRouter w/ reasoning, sk-→OpenAI); copilot+SAR route through it. **Additive edits to api/main.py + frontend/ (heads-up @savvas in §1).** Tested: endpoint 200/404, template fallback, provider detection. — Alexandros_
- _2026-06-13 — P4 (savvas): added AML-tool UX on the console — temporal playback (scrub a ring's transactions over time on the graph), case workflow (status chips + filter + escalate/clear/file, persisted to localStorage), global search/command-palette (⌘K over rings & accounts), and a per-ring risk-breakdown bar (detector contributions). Pure frontend; §8 unchanged. — savvas_
- _2026-06-13 — P5 (Alexandros): `backend/ai/__init__.py` now auto-loads a repo-root `.env` (dependency-free; real env vars still win) so keys in `.env` are picked up without exporting. `.env` stays gitignored. — Alexandros_
- _2026-06-13 — P5 (Alexandros): copilot + SAR now support **OpenRouter** (OpenAI-compatible) as primary provider — set `OPENROUTER_API_KEY` + `MULENET_MODEL` (e.g. `nvidia/nemotron-3-ultra-550b-a55b:free`) to run AI on a free/any model; falls back Anthropic→template. Copilot uses OpenAI function-calling for the tool loop. ai/ files only, no schema/API change. — Alexandros_
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
