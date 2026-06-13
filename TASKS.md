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
- **Status:** ✅ done — added flagship **kingpin** ring + **dynamic decoys**; all green (11/11)
- **Right now:** committed `sample_data/` = 800 accts / ~4.2k txns / **16 rings** (15 + 1 flagship kingpin) + a **randomized** decoy mix. Integrated eval: **ring-recall 1.0, FP-rings 0, account precision 1.0, recall 0.78, 11/11 tests pass**. Kingpin ring is **fully detected (overlap 1.00)** and spans the full lifecycle. Reproduce: `python -m backend.data.generator --seed 42` (decoys now default to a random count+kinds; `--decoys 0`/`N` to pin).
- **Files I'm touching:** `backend/data/generator.py`, `sample_data/` (done)
- **Blockers:** —
- **Notes for the team:** `schemas.py` frozen. Two adds this round: (1) **flagship kingpin** — one orchestrator running placement (structuring+fan_in) → layering (2 pass-through hops) → integration (fan_out, with a relay kickback so all stages merge into ONE detected ring). (2) **dynamic decoys** — `n_decoys=None` now randomizes decoy count (5–12) AND kinds per seed, so every live Generate click stresses precision differently. Decoy-handling (P2 settlement-loop skip + P3 business/low-KYC down-weight) still holds → precision 1.0, FP-rings 0.
  - **🟡 @P3 (Andreas) — pin the flagship #1 (your lane, `scoring.py`):** the kingpin is fully detected but ranks **#5** (score 0.784) behind compact circular rings (~0.88), because its many one-shot smurfs/cash-outs dilute avg member risk. A full-lifecycle ring (placement+layering+integration, 3–4 distinct typologies) is *genuinely* more suspicious than a single-typology cluster — suggest bumping the **diversity weight** in `build_rings` score (currently `0.2·min(1,0.25·#patterns)`) or adding a small "≥3 typologies" bonus. That floats the kingpin to #1 for the demo and is defensible AML logic. Data-side can't do it (verified). I can prototype the 1-liner if you want.
  - **🔴 @P4 (savvas) — "Generate" button feels broken (your lane: `frontend/app.js` + `api/main.py`):** the endpoint works (tested: `{}`→seed42 6 rings, `{"seed":7}`→5 rings), but `app.js:881` posts an empty body `"{}"`, so `GenReq` defaults kick in with a **hardcoded `seed=42`** → every click regenerates the **identical** dataset (looks like nothing happens). It also **downgrades** vs the committed fixture (defaults 600/2500/**6 rings** vs committed 800/4000/**15**). Quick fixes: send a random seed (`body: JSON.stringify({seed: Date.now()%100000})`), and/or add seed/#accounts/#rings inputs, and/or bump `GenReq` defaults to 800/4000/15. Not touching your files — flagging for you.
- **Updated:** 2026-06-13

### P2 — panagiotis — Graph & Structural Detection
- **Status:** ✅ done — all P2 detectors clean against the decoy-ON fixture
- **Right now:** **Settlement-loop FP fixed.** `detect_circular` now skips a cycle whose every member is established **business + low-KYC** (the legit inter-company settlement-loop profile) — real laundering loops always carry ≥1 fresh/personal/elevated-KYC account. On the committed decoy-ON fixture: **FP-rings 2 → 0**, all 3 true circular rings still caught, ring-recall 1.0. Plus the earlier passthrough ratio+speed scaling. **11 tests pass.**
- **Files I'm touching:** `backend/detect/structural.py`, `backend/tests/test_structural.py`
- **Blockers:** —
- **Notes for the team:** Full committed-fixture eval now **ring-recall 1.0, FP-rings 0, account precision 1.0, recall 0.769, F1 0.87** — precision is *earned* against P1's hard negatives. **🟢 @Andreas (P3):** the 2 legit settlement-loop FP rings are gone, so your `test_scoring.py` FP-rings guardrail can tighten to **`fp_rings == 0`** (was ≤2). Recall-safe: 0/39 true mules are business+low-KYC (you confirmed). The 3 structuring-band misses (`ACC00066/143/735`) are an account-recall *nicety*, not a blocker — happy to take them if we want >0.77, but they're outside my `[0.7T,T)/72h` band by design (legit-looking deposit sizes); leaving for now so I don't chase recall into precision risk.
- **Updated:** 2026-06-13

### P3 — Andreas — Network Detection & Scoring
- **Status:** 🔵 in review — decoy hard-negatives handled (precision restored)
- **Right now:** on @kiriakos's **decoy-ON** fixture, precision had dropped to 0.79 (8 legit business FPs — incl. the mega-merchant `ACC00739` scoring a full **1.0**). Added an **established-business profile down-weight** in `scoring.py` (mirrors `network._legit_hub_factor`): an account that is **business AND low-KYC** — the exact decoy profile (payroll/merchant/B2B/settlement) — has its risk ×0.18. Result: **precision 0.79→1.000, recall held 0.769, F1 0.870, ring-recall 1.0**; mega-merchant risk 1.0→**0.30**. **Recall-safe by data:** 0/39 true mules are low-KYC (mules are fresh personal/elevated-KYC), and the 4 *business* mules are medium/high-KYC so the conjunction never touches them — verified with a factor sweep. Earlier: also recalibrated `NORMALIZER 1.6→0.9` (recall 0.359→0.769).
- **Files I'm touching:** `backend/detect/network.py`, `backend/detect/scoring.py`, `backend/detect/pipeline.py`, `backend/tests/test_scoring.py`
- **Blockers:** —
- **Notes for the team:** `scoring.py` + `pipeline.py` only, **no schema/API change** (`score_accounts` now takes optional `accounts`; only `pipeline.run` calls it). `test_scoring.py` updated to the honest decoy reality (precision==1.0, recall≥0.74, ring-recall==1.0, FP-rings≤2, legit-floor<0.45) — **10/10 pass.**
  - **🟢 @P2 (panagiotis):** my account down-weight cleared the *structuring* FP ring (3→2). The **2 remaining FP rings are the legit circular settlement loops** (`DET_002/003`, all business+low-KYC) — that's your detector-source fix (require ≥1 fresh/elevated-KYC account in the loop). I deliberately did **not** touch them to avoid us both over-correcting. Your structuring-band misses (`ACC00066/143/735`) still stand on your plate too.
- **Updated:** 2026-06-13

### P4 — savvas — API & Frontend
- **Status:** 🔵 in review
- **Right now:** three "wow" demo features — **Live transaction feed** (replays the network as a monitored stream: nodes light up, KPIs tick, rings fire 🚨 alert toasts), **one-click Investigation report** (printable / Save-as-PDF case dossier: evidence + flow + transactions + Claude SAR), and a **Threshold sandbox** (slide alert-τ, watch precision/recall trade off live on a PR curve). Plus earlier: accounts table, filters, playback, case workflow, search, breakdown.
- **Files I'm touching:** `backend/api/main.py`, `frontend/index.html`, `frontend/app.js`, `frontend/style.css`
- **Blockers:** —
- **Notes for the team:** §8 stays stable — **additive only**: enriched `/api/graph`, `GET /api/accounts`, new `GET /api/eval/curve` (τ sweep for the sandbox). Demo deep-links: `?live=1`, `?sandbox=1`, `?view=accounts`, `?q=<term>`. Kept P5's account AI-analysis additions intact.
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

- _2026-06-13 — P1 (kiriakos): added a flagship **kingpin** ring (full lifecycle: structuring+fan_in → 2 pass-through layering hops → fan_out w/ relay kickback, merges to ONE detected ring, overlap 1.00) + made **decoys dynamic** (random count 5–12 & kinds per seed, so every Generate click stresses precision differently). Committed fixture now 16 rings; **ring-recall 1.0, FP-rings 0, precision 1.0, recall 0.78, 11/11 green**. 🟡 @P3: kingpin ranks #5 (0.784) under the current ring score; a small **pattern-diversity/lifecycle bonus** in `build_rings` would pin the flagship #1 (defensible AML logic; data-side can't). — kiriakos_
- _2026-06-13 — P4 (savvas): shipped 3 demo "wow" features — **Live transaction feed** (replays the network as a monitored stream: nodes light up, KPIs tick, rings fire 🚨 toasts), **one-click Investigation report** (printable/PDF dossier: evidence+flow+transactions+SAR), **Threshold sandbox** (slide alert-τ → live precision/recall on a PR curve). New `GET /api/eval/curve` (additive); deep-links `?live=1`/`?sandbox=1`. Pure frontend + one read-only endpoint. — savvas_
- _2026-06-13 — P4 (savvas): fixed **Generate** (was always seed 42 → identical data; now sends a random seed each click + `GenReq` defaults bumped to 800/4000/15 to match the generator, so every click is a fresh rich network — thanks @kiriakos for the precise diagnosis) and the Accounts view now hides the graph-only **Transaction filters** (channel/amount/date). `api/main.py` GenReq defaults + frontend; no contract change. — savvas_
- _2026-06-13 — P1 (kiriakos): 🔴 **@P4 (savvas) — "Generate" button looks broken.** Endpoint is fine (tested live), but `app.js:881` posts empty body → `GenReq` hardcoded `seed=42` → every click rebuilds the **identical** dataset (+ downgrades to 600/6-rings vs committed 800/15). Fix in your lane: random seed per click and/or seed/size inputs and/or bump `GenReq` defaults. Details in my §1 note. — kiriakos_
- _2026-06-13 — P1 (kiriakos): decoy stress-test **closed** ✅ — with P2's settlement-loop skip + P3's business/low-KYC down-weight, the decoy-ON committed fixture is now **ring-recall 1.0, FP-rings 0, precision 1.0 (earned!), recall 0.77, 11/11 tests green**. Decision B paid off: hard-negatives made detection more robust, not just lowered a number. Data track done; free to pair on demo polish. — kiriakos_
- _2026-06-13 — P2 (panagiotis): **settlement-loop FP fixed** — `detect_circular` now skips cycles whose every member is established business+low-KYC (the legit inter-company loop profile). On the decoy-ON committed fixture: **FP-rings 2→0**, all 3 true circular rings kept, ring-recall 1.0, account precision 1.0/recall 0.769. structural.py only, no schema/API change, 11 tests pass. 🟢 @Andreas: your `test_scoring.py` FP-rings guardrail can now assert `==0`. — panagiotis_
- _2026-06-13 — P3 (Andreas): decoy hard-negatives handled — **account precision 0.79→1.000, recall held 0.769, F1 0.870, ring-recall 1.0** (was 8 legit-business FPs incl. mega-merchant `ACC00739` at risk 1.0). Added an established-business (business AND low-KYC) ×0.18 profile down-weight in `scoring.py` (recall-safe: 0/39 mules are low-KYC; verified by sweep). `scoring.py`+`pipeline.py` only, no schema/API change; `test_scoring.py` updated to decoy reality (10/10 pass). **@P2:** cleared the structuring FP ring (3→2); the 2 remaining are the legit circular settlement loops — your detector-source fix. — Andreas_

- _2026-06-13 — P4 (savvas): add a way back from a selected ring — "← Back to all rings" button in the inspector (account view backs to its ring), click-empty-canvas to deselect, and Fit now does a clean full reset via `clearSelection()` (clears highlight, refits, resets inspector + hash). Pure frontend. — savvas_
- _2026-06-13 — P1 (kiriakos): **flipped decoys ON in the committed fixture** (team call — precision should be earned). Eval now: ring-recall **1.0**, precision **0.79**, FP-rings **3**, recall 0.77. **🔴 @P3: this turns 3 of your `test_scoring.py` guardrails red** (precision/ring-metrics/legit-floor) — expected; please relax thresholds (precision≥0.78, fp_rings≤3) or harden the fan down-weight (legit mega-merchant `ACC00739` in=278 trips `fan_in`→1.0). **🟡 @P2:** legit settlement loops still read as cycles (you flagged you'd take this 👍). `--decoys 0` reverts the fixture if needed. — kiriakos_
- _2026-06-13 — P2 (panagiotis): scaled `detect_passthrough` by ratio+speed (§9 #3) — flat 0.6 had pinned all 10 layering relays at risk 0.30 (<τ); scores now 0.82–0.92, all on labeled mules (precision-safe). Composes with @Andreas's NORMALIZER recalibration (relays now sit comfortably above τ); verified combined eval still precision 1.0, recall 0.769, 10/10 tests pass. structural.py only, no schema/API change. — panagiotis_
- _2026-06-13 — P4 (savvas): UI bug-fix pass — graph tooltips no longer show raw HTML (plain text + themed `.vis-tooltip`); global search now matches **owner name / id / country** over all 800 accounts and shows owners; +404-safe account view, Esc closes the Filters drawer, owner names in flow tooltips, dynamic legend mode text, `?q=` deep-link. Pure frontend. — savvas_
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
