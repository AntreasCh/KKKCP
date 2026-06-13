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
- **Status:** ✅ done — LiveFeed mints accounts live (wired by @P4); by-reference footgun root-fixed; all green (12/12)
- **Right now:** committed `sample_data/` unchanged (800/16 rings; ring-recall 1.0, FP 0, precision 1.0, recall ~0.78). **`LiveFeed` mints accounts on demand** (network grows nodes, not just edges; new legit accounts at random **1–10-tick** intervals; rings on brand-new disjoint accounts). @P4 wired it 🙏. Also **root-fixed the by-reference bug P4 caught**: `initial()` now returns a **copy** of the accounts list so the engine never silently grows the caller's `STATE` list → no duplicate-id graph crash. Verified P4's dedup-safe flow: 40 ticks → 131 accounts, 0 duplicates.
- **Files I'm touching:** `backend/data/generator.py`, `sample_data/` (done)
- **Blockers:** —
- **Notes for the team:** `schemas.py` frozen. P1 deliverables: flagship **kingpin** ring, **dynamic decoys**, and the **LiveFeed** engine (now wired by @P4 🙏).
  - **🟢 @P4 (savvas) — account-minting wiring DONE + footgun root-fixed.** Thanks for catching the duplicate-id crash — root cause was `initial()` leaking `self.accounts` by reference; I now return a copy, so `STATE` owns its list and your `next_batch()["accounts"]` are strictly new (your dedup-safe extend + `dedupeById` stay as belt-and-braces). Verified together: 40 ticks → 0 duplicate ids, network grows nodes calmly.
  - **~~🟡 @P3 — pin the flagship #1~~ — CANCELLED** (P3 chose to keep their lifecycle bonus; their call, I don't object).
  - **🟢 @P5's request (Account `status` field) — DONE.** Added `status: "active"|"frozen"|"blocked"|"banned"` to `Account` (**optional, default `"active"`** → fully backward-compatible, no existing consumer breaks). Generator + LiveFeed emit `"active"`; `sample_data` regenerated. **🔵 @P4:** the field is now in `/api/accounts` + graph nodes for your freeze/review feature (§6) — runtime freeze/block/ban transitions are yours to set in `STATE`.
- **Updated:** 2026-06-13

### P2 — panagiotis — Graph & Structural Detection
- **Status:** ✅ done — all P2 detectors clean against the decoy-ON fixture
- **Right now:** ⚡ **PERF: scaled structural detection to 100k+ txns (fixes the live-feed lag).** `detect_circular` was re-enumerating cycles on the whole growing graph every tick (~450ms). Two correctness-preserving fixes: (1) **money-edge pruning** — a value-retaining loop carries a big transfer each hop, so the cycle-search graph only needs pairs with a transfer ≥€1000; cycle search now scales with large transfers, not total tx count. (2) **memoised `_ts`** (strptime was re-parsing the same timestamps every tick). Result: **P2 structural 1819ms→208ms at 106k txns (8.7×)**, circular 442ms→18ms. Eval identical: ring-recall 1.0, FP 0, precision 1.0, recall 0.775, **12 tests pass**.
- **Files I'm touching:** `backend/detect/structural.py`, `backend/tests/test_structural.py`
- **Blockers:** —
- **Notes for the team:** **🔴 @Andreas (P3) — `detect_fan` is now the live-feed bottleneck at scale.** Profiled the full pipeline at 106k txns: P2 structural **208ms** (fixed), Louvain communities 89ms, but **`fan` = 6250ms** — it dominates and would lag a large live stream. Likely the same pattern (re-scanning all senders/recipients per account each tick); same fixes apply (memoise timestamp parsing, prune to significant-amount edges). My lane is fast now; yours is the next lever for 100k+ real-time. (Earlier finding still stands: the 9 account-recall misses aren't precision-safe in my lane — single-large-deposit/low-degree accounts; a consolidation rule adds 2 legit FPs. FP-rings is 0 → your `test_scoring.py` can assert `==0`.)
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
- **Right now:** **wired @P1's live account-minting — the live network now grows NODES, not just edges, with zero churn.** `stream_next` appends the batch's new accounts (dedup-safe) + returns enriched `new_nodes`; `pollLive` adds them as nodes **placed beside a connected neighbour** (`placeNewNodes`, physics frozen) so the layout never re-runs/drifts as the network grows. Playwright: nodes grow 85→92 while existing node positions stay **frozen**, 0 console errors. Earlier this stretch: **calmed the graph** (settle behind a "Laying out network…" overlay → freeze → reveal; no on-screen physics churn), live feed auto-start + Stop=freeze/Resume=continue, dark mode + grouped notifications inbox.
- **Files I'm touching:** `backend/api/main.py`, `frontend/app.js` (this round); `frontend/index.html`, `frontend/style.css` (earlier)
- **Blockers:** —
- **Notes for the team:** **Additive** — `/api/stream/next` gains a `new_nodes` key (same node shape as `/api/graph`); §8 otherwise stable, 12/12 tests green. Heads-up @P1: I add the new accounts **dedup-safe** because `LiveFeed.initial()` returns its `accounts` list *by reference* and `_mint` appends to it, so they were already landing in `STATE` — a plain `.extend()` double-added and crashed the graph (fixed). New nodes drop in next to a neighbour with `physics:false`, so the calm/frozen layout holds. Added a defensive `dedupeById` in `renderGraph` so duplicate-id data can never crash the whole graph again. **App still lands in LIVE mode by default** (`?live=0` / fixture deep-links opt out; `?live=1` forces).
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

- _2026-06-13 — P1 (kiriakos): root-fixed the LiveFeed **by-reference footgun @P4 caught** — `initial()` now returns a **copy** of the accounts list, so the engine never silently grows the caller's `STATE` list (the source of the duplicate-id graph crash). Verified P4's dedup-safe flow: 40 ticks → 131 accounts, **0 duplicates**, 12/12 tests green. `generator.py` only. — kiriakos_
- _2026-06-13 — P2 (panagiotis): ⚡ **perf — scaled structural detection for the live feed.** `detect_circular` money-edge pruning (cycle search only over pairs with a transfer ≥€1000) + memoised `_ts`. **P2 structural 1819ms→208ms at 106k txns**, circular 442ms→18ms; correctness identical (ring-recall 1.0, FP 0, precision 1.0, recall 0.775, 12 tests). `structural.py` only, no schema/API change. **🔴 @Andreas: `detect_fan` is now the pipeline bottleneck at scale (6250ms @106k)** — next lever for 100k+ real-time. — panagiotis_
- _2026-06-13 — P4 (savvas): **wired @P1's live account-minting — the live network grows NODES now, churn-free.** `stream_next` appends the batch's new accounts + returns enriched `new_nodes` (same shape as `/api/graph`); `pollLive` adds them as nodes FIRST (so rings/edges can attach), each **placed beside a connected neighbour** (`placeNewNodes`) with `physics:false` so the **frozen layout never re-runs** — new accounts slot in calmly instead of exploding the graph. **🟢 @P1 — heads-up/​fix:** your `LiveFeed.initial()` returns its `accounts` list *by reference* and `_mint` appends to it, so new accounts were already landing in `STATE`; my first `.extend()` double-added them → duplicate `account_id` → graph crashed at boot. Fixed with a dedup-safe extend, and added a defensive `dedupeById` in `renderGraph`. Additive (`new_nodes` key on `/api/stream/next`), §8 stable, 12/12 tests green. **Playwright-verified:** nodes grow 85→92 while existing node positions stay **frozen** (no churn), 0 console errors. — savvas_
- _2026-06-13 — P4 (savvas): **calmed the graph rendering — no more on-screen physics churn.** The vis-network used to run its stabilization visibly, so users watched every node fly around and re-settle (chaotic with a lot of nodes / during the live feed — "can't see it"). Now `renderGraph` settles **behind a `#graph-loading` overlay** ("Laying out network…") then **freezes physics and reveals the finished, static layout** — the churn is never on screen. Live feed: new transfers are added in their **final style (dropped the bright blue width-3 pulse)** with physics frozen, so the layout doesn't drift as the feed streams; also skip live edges whose id already exists (kills a `duplicate id` throw on mid-stream re-render). Pure frontend, §8 untouched, 12/12 tests green. **Playwright-verified:** overlay shows during layout then hides; node positions **identical across 17s of live streaming** (frozen); 146 edges streamed in with **0 console errors**. **🟡 @P1: saw your account-minting request** — will wire `batch.accounts` next; note new nodes must drop in *without* a physics re-churn (placed near a neighbour, layout stays frozen) to keep this calm. — savvas_
- _2026-06-13 — P1 (kiriakos): **LiveFeed now mints accounts live** — the network grows nodes, not just edges. New legit accounts open at random **1–10-tick** intervals (calm trickle, 1–3 at a time) + each ring is built from **brand-new** accounts (rings disjoint by construction; merge-fix now structural). Batch shape gains an `accounts` key. Verified: 40 ticks → +200 accounts, 15 separate rings, schema-valid, 12/12 green. **🔴 @P4: small wiring add needed** (append `batch["accounts"]` in `stream_next` + add the nodes in `liveTick` before the edge filter) — details in my §1 block; graceful without it (no crash, just no new nodes). — kiriakos_
- _2026-06-13 — P5 (Alexandros): **enforcement now actually stops frozen accounts transacting in the live feed.** Found the gap: `LiveFeed`/`/api/stream/next` emitted new transactions without ever checking `Account.status`, so a frozen/blocked/banned account kept moving money. Fix (additive, in `stream_next`): any freshly-streamed tx whose **sender OR receiver** is under enforcement is **prevented** — it never enters the dataset; if a planted burst's legs are all blocked the dead ring is dropped. Response gains a `prevented: [{src,dst,amount}]` list; the live banner shows a running **🛑 N blocked** stat + a toast per stop. Verified: threshold 0 → all 300 frozen → 100% of ticks blocked (0 allowed); threshold 0.9 → legit traffic flows (0 prevented); manual block on an account stops its sends. Touched `backend/api/main.py` (`_enforced_ids` + filter in `stream_next`) and `frontend/{app.js,style.css}`. — Alexandros_
- _2026-06-13 — P4 (savvas): **live feed now auto-starts on app load; Stop=freeze, Resume=continue.** The app opens already polling `/api/stream/next`. **Stop is now Pause** — it stops polling but **keeps the streamed data on screen and the server-side `LiveFeed` alive** (no more `/api/stream/stop` + fixture restore), banner switches to a muted **PAUSED**. **Resume continues the SAME stream** from exactly where it stopped (no `/api/stream/start` → no reset; the network keeps growing). Leaving the Graph view pauses (resumable); Generate ends the session; `pollLive` self-heals if the server stream vanished. Pure frontend, §8 untouched, 12/12 tests green. **Playwright-verified end-to-end:** auto-start (on@boot), freeze-on-pause (tx+edges frozen 143→143 over 5.5s), continue-on-resume (143→154, not reset), coexists with §6 freeze + dark mode + notifications. **⚠️ team heads-up: the app now lands in LIVE mode by default** — `?live=0` (or any fixture deep-link `?view=`/`?q=`/`?filters=`/`#ring`) opens on the committed fixture instead; `?live=1` forces live. **🟢 @P1:** your two-pool fix holds under live polling — 19 distinct rings, no mega-blob. — savvas_
- _2026-06-13 — P5 (Alexandros): **built the §6 freeze-&-review feature** on top of @kiriakos's `Account.status`. Backend (additive, §8-stable): `POST /api/freeze {threshold}`, `GET /api/frozen` (review queue), `POST /api/accounts/{id}/decision {block|ban|clear|freeze}`. UI: topbar 🔒 **Compliance panel** (risk-% slider + live "will freeze N" preview + Freeze button + review queue with per-account Block/Ban/Clear) and a status chip + decision buttons in the account inspector + a status chip in the Accounts table. Tested live: freeze@90%→15 frozen, block/clear flip status, frontend 200. **🟡 @savvas (P4):** I made **additive** edits to `api/main.py` + `frontend/{index.html,app.js,style.css}` for this — new freeze endpoints + a self-contained `#freeze-panel`/`fz*`/`enf-*` block + a status chip in `renderAccountsTable` + `INSPECTED_ACCT` in `showAccount`. No existing logic changed; pull before your next push. — Alexandros_
- _2026-06-13 — P1 (kiriakos): ⚠️ **FROZEN-SCHEMA CHANGE (additive, safe):** added `status` to `Account` (`active|frozen|blocked|banned`, **optional, default `active`**) for P5/P4's §6 freeze-&-review feature. Generator + LiveFeed emit `"active"`; `sample_data` regenerated. Backward-compatible — no existing consumer breaks; 12/12 tests green. @P4: field now flows through `/api/accounts` + graph nodes for your freeze/review UI. — kiriakos_
- _2026-06-13 — P1 (kiriakos): **fixed @P4's LiveFeed ring-merge bug** — bursts + legit traffic shared one account pool, bridging rings → Louvain merged them. Fix: two disjoint pools (legit-only traffic + a reserved mule-profiled ring pool consumed in fresh disjoint slices per burst). Repro now: 40 ticks → 15 bursts → **15 separate detected rings, biggest 10 accts** (was 2 rings / 62-acct blob). **Batch shape unchanged**, your `/api/stream/*` wiring needs no change. 12/12 tests green. — kiriakos_
- _2026-06-13 — P4 (savvas): shipped **dark mode** (topbar 🌙/☀️ toggle, persisted to localStorage, no-flash bootstrap in `<head>`) + a **grouped live-feed notifications inbox** (🔔 bell w/ unread badge): every live 🚨 ring alert is now persisted and shown **grouped by laundering pattern**, deduped per ring with an ×N count — replaces the vanishing 5s toasts so alerts stay reviewable. Pure `frontend/` (index.html/app.js/style.css), additive, §8 untouched, verified in-browser (light+dark + persistence across reload). **🔴 @P1 (kiriakos) — LiveFeed ring-merge bug (your lane, `backend/data/generator.py`):** as the stream runs, distinct rings collapse into **one** mega-ring. Reproduced: 40 ticks → 6 planted bursts, but detected rings stall at **2** while the biggest balloons to **62 of 120 accounts**. Root cause: every `_burst()`/`_legit()` draws hubs+spokes from the **same shared `self.acc_ids` pool** with reuse, so as `/api/stream/next` re-runs full detection on the cumulative graph, legit edges + reused accounts bridge the bursts → Louvain merges them into one community. Fix in your lane: give each burst its own **disjoint fresh accounts** (and keep legit traffic from wiring burst hubs together) so rings stay structurally separate. Happy to adjust the `/api/stream/*` wiring if your fix changes the batch shape. — savvas_
- _2026-06-13 — P2 (panagiotis): richer **structuring score** (count + closeness-to-T + burst tightness, §9 #1) — better ranking + one hub crossed τ (**recall 0.769→0.775, precision held 1.0, 12 tests**). Also rigorously tested the remaining-recall lever and **reject it as precision-unsafe**: the 9 missed mules are single-large-deposit collectors / <5-counterparty fan accounts with no structural signature; a consolidation rule catches 1 but adds 2 legit FPs → that's @Andreas's `network.py` lane + a precision trade-off, not a structural fix. My detectors are at their precision-safe frontier; FP-rings=0 so P3 can assert `==0`. — panagiotis_
- _2026-06-13 — P3 (Andreas): **🟡 @kiriakos heads-up — re your kingpin-#1 cancel:** I'd *already* implemented + verified it before your cancel synced, so I'm **keeping** it (my lane + a clean, defensible demo win). Added a **lifecycle bonus** to `build_rings` (`LIFECYCLE_BONUS=0.12`/typology beyond the 2nd): a full placement→layering→integration ring outranks a simple 2-party loop. **Flagship kingpin now ranks #1 (0.904)**; multi-typology rings fill the top of the queue. Additive only → can't drop a ring or spawn an FP: **precision 1.0, recall 0.775, ring-recall 1.0, 0 FP, 12/12 tests.** `scoring.py`+`test_scoring.py` only, no schema/API change. Shout if you object and I'll revert. — Andreas_
- _2026-06-13 — P5 (Alexandros): logged a **feature request — risk-threshold account freezing & manual review** (see new §6 below). 🟡 **@savvas (P4):** admin sets a risk-% threshold in the UI → auto-freeze accounts ≥ threshold → review queue → per-account **block/ban/clear** (extends your case workflow; additive API). 🟡 **@kiriakos (P1):** add an optional `status` field (`active|frozen|blocked|banned`, default `active`) to the Account schema/generator/`sample_data` (frozen-schema heads-up needed). Spec only — no code from me. — Alexandros_
- _2026-06-13 — P4 (savvas): **wired @kiriakos's `LiveFeed` real-time stream** — "▶ Live feed" now does a true server-side stream (new `POST /api/stream/start`, `GET /api/stream/next`, `POST /api/stream/stop` in `api/main.py`): polls every ~1–3s, streams in new edges, grows the network, fires 🚨 on freshly-detected rings, with a **1×/2×/4× speed control**; Stop restores the committed fixture. Additive, §8 stable, 11/11 tests green. (Replaced the earlier replay-based live mode.) — savvas_
- _2026-06-13 — P1 (kiriakos): **CANCELLED the kingpin "#1 ranking" ask to @P3** — no action needed from Andreas (he hadn't started it). Kingpin ring stays in the data as a normal fully-detected ring; we're not pinning it #1. No code/data change. — kiriakos_
- _2026-06-13 — P4 (savvas): added the two biggest real-AML must-haves — **watchlist screening** (synthetic sanctions/PEP/adverse-media: accounts-table column, account-inspector panel, ⚠ ring-exposure banner, red-bordered graph nodes, `watchlist` KPI + filter) and **goAML structured STR export** (`GET /api/rings/{id}/goaml` → downloadable XML). **Removed the threshold sandbox** + its `/api/eval/curve` endpoint (unnecessary, per review). Also QC: showRing 404 guard + destroy old graph network (leak). All additive; §8 stable. — savvas_
- _2026-06-13 — P1 (kiriakos): added a **`LiveFeed` streaming engine** (`backend/data/generator.py`) for live-mode demo — `initial(~100 tx)` + `next_batch()` emits new txns over a virtual clock (legit + ~25% a fresh laundering burst, returns the new ring for alerts). Additive, deterministic, schema-valid; committed fixture/pipeline untouched, **11/11 green**. 🔴 @P4: wire `LiveFeed` behind a `GET /api/stream/next` endpoint + poll it every random 1–10s in live mode + the replay speed-up (details in my §1 block). — kiriakos_
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

---

## 6. 📌 Feature request — Risk-threshold account freezing & manual review

**Requested by:** Alexandros (P5), for the demo narrative *detection → enforcement action*.
**Owners:** **P4 (savvas)** — API + UI (extends the existing case workflow). **P1 (kiriakos)** — the
account `status` field in the schema/dataset. *(P5 has an optional follow-up, below.)*

### Idea
An admin sets a **risk threshold from the UI** (e.g. 90%). Accounts with `risk ≥ threshold` are
**auto-frozen** and queued for **manual review**. The reviewer then decides per account:
**block**, **ban**, or **clear (unfreeze)**. Freezing is automatic by threshold; block/ban are
never automatic — they require human review.

### Account status — **P1** (schema + data)  *(this is the "update the dataset" part)*
- Add a `status` field to **Account**: `"active" | "frozen" | "blocked" | "banned"`, default `"active"`.
- `schemas.py` is **FROZEN** → post a heads-up in the Activity Log first; make the field
  optional/defaulted so existing consumers don't break.
- Generator emits `status: "active"` for every account; regenerate `sample_data/dataset.json`.
- The dataset carries the *baseline* status; live freeze/review decisions are runtime state (below).

### State machine
`active → frozen` (auto, when `risk ≥ threshold`) → reviewer sets `blocked` | `banned` |
`cleared (→ active)`.

### API — **P4** (additive, keep §8 stable)
- `POST /api/freeze {threshold}` (0..1) → set `status=frozen` on accounts with `risk ≥ threshold`;
  return the frozen list + count.
- `GET /api/frozen` → frozen / under-review accounts with their status.
- `POST /api/accounts/{id}/decision {action}` where `action ∈ {block, ban, clear}` → update status
  (`clear → active`).
- Hold status in the in-memory `STATE` so the graph/table reflect it (no DB — matches the local-only
  constraint), and/or persist via the existing localStorage case workflow.

### UI — **P4**
- A **Compliance** control: threshold **slider / % input** (default 90%) with a live preview
  ("will freeze **N** accounts ≥ 90%") and a **Freeze** button.
- Frozen accounts marked (🔒 / red chip) in the **accounts table**, **graph nodes**, and **inspector**.
- A **review queue** — filter the accounts table to *frozen / pending review*.
- In the account inspector: **Block · Ban · Clear (unfreeze)** buttons showing the current status.
- Reuse the existing case-workflow status chips + persistence rather than a parallel system.

### Optional follow-up — **P5** (Alexandros)
- Surface the existing `POST /api/accounts/{id}/analyze` AI verdict in the review panel so each
  frozen account shows an AI recommendation to inform the block/ban/clear decision.

### Definition of Done
Admin sets a %, clicks **Freeze** → matching accounts flip to `frozen` and appear in a review queue,
marked across table/graph/inspector; each can be **blocked/banned/cleared** from the UI; status
persists across reload; the Account schema + `sample_data` carry the `status` field; tests green.
