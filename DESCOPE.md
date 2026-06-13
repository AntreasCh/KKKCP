# 🪒 DESCOPE — MuleNet → Minimal Operator Console

> **Goal:** the project has grown **above** its hackathon requirements. Shrink to a **minimal,
> presentation-ready AML triage console**. Keep the UI minimal and usable for a live demo.
> Authored 2026-06-14 from a full whole-codebase audit (every endpoint/feature inventoried).
>
> **This is a plan — no code has changed yet.** Most edits land in **P4's lane** (`api/main.py`,
> `frontend/`). Detection (P1/P2/P3) and the P5 account-AI stay essentially untouched.
>
> ⚠️ **Read §8 (Breakage checklist) before deleting anything** — several *kept* functions call
> *removed* code; deleting naively will red the demo on load.

---

## 1. Target product (one paragraph)

A single-page, local (`uvicorn` + static frontend, no build step), **operator-focused** AML triage
console. On load it shows dataset KPIs and an **Accounts table — the primary view** — populated by
the kept pipeline: **P1 generator → P2 structural detectors → P3 network/scoring**. A **Generate**
button makes a fresh seeded dataset for the demo. Accounts at **risk ≥ 0.90 auto-freeze** (fixed
rule, no slider). The operator can **browse under-review/frozen accounts**, open the **P5 per-account
AI analysis**, and click **"Visual Review"** on a flagged account to open a **small risk-colored
graph** of that account + its suspicious/associated accounts — judging legit vs fraud at a glance.
Everything global, streaming, or ring-workflow-centric is removed.

## 2. At a glance

| Disposition | Items |
|---|---|
| ✅ **KEEP** | Data generation + Generate button · P2+P3 detection/scoring (incl. `build_rings` & `detect_communities`) · P5 account AI-analysis · Accounts table + inspector · browse frozen/under-review · auto+manual freeze · the **account-scoped ego-graph** (it's the Visual Review backend) |
| ❌ **REMOVE** | Live feed / streaming (engine + 3 endpoints + UI + notifications inbox) · global whole-market graph (`GET /api/graph` + render path + "show all" toggle) · custom freeze-threshold **slider** |
| 🔧 **CHANGE** | Graph is **account-scoped only** (no persistent Graph tab) · freeze threshold → **fixed `0.90` constant** |
| ➕ **ADD** | **"Visual Review"** button on flagged accounts → small ego graph (reuses existing `/api/graph/account/{id}`) |
| ❓ **DISCUSS → recommended CUT** | ring queue + ring detail UI · per-ring SAR · goAML export · Ask-MuleNet copilot · watchlist/sanctions screening · temporal playback · ⌘K command palette · filters drawer · dark mode · eval **card** (keep endpoint) · `p2.html` |

---

## 3. KEEP (core — do not touch the logic)

| Feature | Where | Note |
|---|---|---|
| P1 data generation + "more data" lever | `data/generator.py` `generate_dataset` (61–394); `POST /api/dataset/generate` (104–110); `#gen` button (`app.js` ~1479) | Each seed = fresh hard-negative mix. |
| Detection pipeline (P2+P3) | `pipeline.run` (12–26); `structural.py`; `network.py` `detect_fan`; `scoring.py` `score_accounts`+`build_rings` | Everything reads `STATE['result']`. **Keep `build_rings`** — it backs Visual Review ring-coloring. |
| Accounts panel + detail + browse frozen | `GET /api/accounts` (308–325), `/api/accounts/{id}` (349–360), `/api/frozen` (434–449); `app.js` `loadAccounts`/`renderAccountsTable`/`showAccount`; "Under review only" filter; `openReview` modal | Primary view. |
| Freeze (auto + manual) | `_apply_freeze` (379–390), `POST /api/accounts/{id}/decision` (452–463), `GET /api/freeze` (417–421); `Account.status`/`AccountStatus` (`schemas.py`) | Now **fixed 0.90** (§5). |
| P5 AI account analysis | `ai/analysis.py` `analyze_account` (113–141); `POST /api/accounts/{id}/analyze` (363–369); `app.js` `runAccountAnalysis` (~872) | Depends only on `llm.py` + `__init__.py`. Unaffected by removals. |
| **Account-scoped ego graph** | `GET /api/graph/account/{id}` (264–305) + `_enriched_nodes` (126–138) + `_enriched_edges` (114–123); `app.js` `focusOnAccount` (275–294), `renderGraph`/`nodeStyle`/`edgeStyle`, `#focus-bar`, `#legend` | **This is the Visual Review backend — keep all of it.** |
| Schemas / eval / static mount / toasts | `schemas.py` (frozen, no edits); `evaluate()`; static mount (540–542); `toast()`/`dismissToast()` | Keep `evaluate()` callable for tests + a metrics slide. |

## 4. REMOVE

### 4.1 Live feed / streaming
- **Backend:** delete `class LiveFeed` + `BURSTS` (`generator.py` 398–544); change `main.py` import (line 21) to `from backend.data.generator import generate_dataset` (drop `LiveFeed`); delete `stream_start` (141–148), `stream_next` (158–212), `stream_stop` (215–220), and `_enforced_ids` (151–155, only used by `stream_next`). Remove `STATE['live']` (line 32) + its reset in `gen()` (106). **KEEP `_enriched_nodes`/`_enriched_edges`** (shared with `graph_account`).
- **Frontend:** delete the live block in `app.js` (~1249–1457: live state, `fireRingAlert`, `setLiveUI`, `startLive`, `pause/resumeLive`, `endLive`, `scheduleLive`, `placeNewNodes`, `pollLive`) **but keep `toast()`/`dismissToast()`**; delete the notifications block (1157–1247). `index.html`: delete `#live-btn`, `#live-bar`, `#notif-btn`/`#notif-badge`/`#notif-panel` (keep `#toasts`). `style.css`: delete `.live-*`/`@livepulse`, `.notif-*`.
- ⚠️ See §8 — `pauseLive()`/`startLive()`/`endLive()` are called from **kept** code.

### 4.2 Global whole-market graph
- **Backend:** delete `graph()` (228–261) + its route. **Keep `graph_account` + the two `_enriched_*` helpers.**
- **Frontend:** delete `loadGraph()` (136–139) and its callers; delete the `showAll` variable (40) and the `showAll ||` branches in `renderGraph` (143,146); remove `$('showall')` writes (290,320,1322,1485); delete `#showall` toggle in `index.html`. **Keep `renderGraph`/`nodeStyle`/`edgeStyle`/`highlightGraph`/`showGraphLoading`** — reused by Visual Review.
- ⚠️ See §8 — removing `showAll` naively **hides legit counterparties** and breaks the feature; `clearFocus()` calls the deleted `loadGraph()`.

### 4.3 Custom freeze-threshold slider
- **Backend:** delete `POST /api/freeze` setter `freeze()` (424–431) + `FreezeReq` (409–410). (Keep `GET /api/freeze` for the under-review count.)
- **Frontend:** delete `applyThreshold()` (~1514–1520), the `#fz-threshold` wiring (~1571–1574), and the slider-sync lines in `syncFreeze` (1017–1018); **keep** the `#fz-count` update (1019). `index.html`: replace the slider (`.af-ctl`, ~116–118) with a static **"Auto-freeze ≥ 90%"** label. `style.css`: delete `.af-ctl`/`.af-count`.

## 5. CHANGE

- **Graph is account-scoped only.** Default the app to the Accounts view (`curView='accounts'`).
  Remove the two `.vt` view-toggle buttons (`index.html` 57–60). The `#graph` canvas appears **only**
  when `focusOnAccount()` is invoked by Visual Review; `#focus-clear` returns to Accounts. Keep
  `#graph`, the vis-network `<script>`, `#focus-bar`, `#legend`.
- **Freeze rule → fixed constant.** Add `FREEZE_THRESHOLD = 0.90` at the top of `api/main.py`
  (replacing `STATE['freeze_threshold']`). In `_apply_freeze` (379–390) and `_freeze_reason`
  (393–406), use the constant. `GET /api/freeze` returns the constant (or drops the field). Deleting
  the POST setter means the threshold can never be changed. Manual override via
  `POST /api/accounts/{id}/decision` is unaffected.

## 6. ➕ NEW — "Visual Review" (the one feature to build)

**The backend already exists** — `GET /api/graph/account/{id}` returns the ego-network from existing
pipeline output. No new endpoint strictly required. The work is ~80% frontend wiring.

- **Data source:** `GET /api/graph/account/{id}?hops=1`. Nodes carry `risk` (from `score_accounts`)
  and `ring` (from `build_rings`); edges carry `suspicious` (src/dst risk ≥ 0.5) and `ring` (tx in a
  ring's `tx_ids`). So "suspicious associated accounts" = neighbors with risk ≥ 0.5 (red) + ring
  members (ring-colored); "fraudulent transactions" = the edges flagged `suspicious`/`ring`.
- **Frontend:** relabel the existing "⊙ Txns" button in `renderAccountsTable` (~1043) to
  **"Visual Review"**, wired to `focusOnAccount(id)` (it already fetches this route and renders into
  `#graph`). Optionally also place it in the `showAccount` inspector header. `#focus-clear` is the
  "← Back to Accounts" control. `#legend` is the color key.
- **🎯 Recommended refinement (do this, not defer):** add a `suspicious_only=true` query param to
  `graph_account` so the small graph shows the account **+ only its suspicious/ring counterparties**
  — which is literally what the directive asks ("the suspicious accounts associated with it").
  Without it, a legit hub (payroll/merchant) returns *all* counterparties (bounded by `max_nodes=400`)
  — not "small." Keep a **"show all counterparties"** toggle for context if you want legit-vs-fraud
  comparison.
- **UX:** Accounts table → spot a frozen/high-risk account → **Visual Review** → small ego graph
  (center, risk-colored, suspicious edges highlighted, legend visible) → judge → **← Back to Accounts**.
- **Design decision (confirm):** show the graph **in the center pane** (reuse `#graph`, least new
  code) **or** as a **small modal/overlay** over the table (cleaner "home = Accounts", matches "opens
  a small graph"). Recommend in-pane for minimal effort; modal if time allows.

## 7. ❓ DISCUSS — cut/keep decisions (recommendations folded in)

> You said "shrink as much as possible / minimal UI," so the default is **CUT**. Two of the
> auto-synthesized cuts were **overruled** by the adversarial review as out-of-scope/risky — noted.

| Feature | Rec | Why |
|---|---|---|
| Ring queue + ring detail panel UI (`/api/rings*`, `loadRings`/`showRing`) | **CUT (UI)** | Accounts + Visual Review is the operator path. **Keep `build_rings`** + ring-color load so Visual Review can color ring members. `/api/rings` may stay defined but unwired. |
| Per-ring SAR (`sar.py`, `POST /api/rings/{id}/sar`) + goAML (`GET /api/rings/{id}/goaml`) | **CUT both together** | goAML calls `generate_sar`. Kept AI surface is per-account analysis. Also drop the L20 `sar` import + now-dead `datetime`/`_xesc`. |
| Ask-MuleNet copilot (`copilot.py`, `POST /api/ask`, Ask tab) | **CUT** | Second AI surface, not in KEEP. Clean (lazy import). Collapses right-rail to Inspector only. |
| Watchlist / sanctions / PEP screening | **CUT (atomically)** | Decorative synthetic enrichment woven through many payloads. ⚠️ §8 — must cut backend + all frontend touch-points in one pass or the kept Accounts table references missing fields. |
| Eval card (UI) | **CUT card, KEEP endpoint** | Judging artifact, not operator triage. Keep `/api/eval` + `evaluate()` for the verification check + a metrics slide. |
| Filters drawer · ⌘K palette · dark mode · temporal playback | **CUT all** | Keep only the "Under review only" checkbox + the `focusMembers` scoping gate. |
| `frontend/p2.html` | **CUT** | Dev tuning page; no code references it. Delete the file. |
| Case-management workflow (status chips/localStorage) | **CUT** | Lives inside the ring-detail panel being cut — falls out naturally. |
| **`detect_communities` (network.py #5) + python-louvain** | **KEEP** ⚖️ *(overrules auto-cut)* | Cutting perturbs `account_risk` → could move accounts across the 0.90 freeze line. Directive says keep the *whole* pipeline. No-ops gracefully if dep missing. |
| **Block/Ban enforcement verbs** | **KEEP all 4** ⚖️ *(overrules auto-cut)* | Already wired; backend `decision` endpoint kept. Cutting = pure churn + 3 inconsistent render sites = demo breakage risk, zero minimality win. |

## 8. ⚠️ Breakage checklist — *kept* code that references *removed* code

Deleting the blocks above without these edits will throw on load or on the first Visual Review click.

1. **`clearFocus()` (app.js 316–323)** calls deleted `loadGraph()` (321) and `$('showall')` (320).
   → Rewrite: reset `focusAcct`/`focusMembers`/`focusHops`, `setFocusUI(null)`, then
   `setView('accounts')` + `renderAccountsTable()`. **Do not** call `loadGraph()` / touch `showall`.
2. **`renderGraph` `showAll` branch** — when `focusAcct` is set, render **ALL** nodes/edges from
   `lastGraph` (the bounded ego set), *not* filtered by `inFocus`/`suspicious`. Otherwise legit
   counterparties (risk<0.5, no ring) vanish and the operator can't judge legit-vs-fraud.
   → `viewNodes = focusAcct ? dedupeById(lastGraph.nodes) : dedupeById(lastGraph.nodes.filter(inFocus))` (same for edges).
3. **`pauseLive()`/`startLive()`/`endLive()` call sites** in kept code: `focusOnAccount` (278),
   `setView` (1127), Generate (1483), boot (1505). → Remove these calls. Then `grep` confirms
   `pauseLive|startLive|endLive|resumeLive|scheduleLive|pollLive|setLiveUI|fireRingAlert` = 0 refs.
4. **Screening cut must be ATOMIC** — backend `_screening`/`_ahash` (39–62) + the `screening`/`screened`
   keys in `/api/accounts` (325), `/api/accounts/{id}` (360), `_enriched_nodes` (137), `_summary`
   (89,93) **and** frontend `setKpis` (s.screening_hits), `acctPasses`, `renderAccountsTable`
   column+sortkeys, `showAccount` panel, `index.html` Screening `<th>` + `#f-watchlist`. Cut **all
   together** or keep whole. (Recommend cut.)
5. **`switchTab` (892–897)** is called by kept `showAccount` (713). After the Ask tab is removed,
   make `switchTab` a no-op / direct show of `#tab-inspector`; keep `showAccount`'s call intact.
6. **`boot()`/`refresh()` deep-links** call deleted code: `refresh()` (1466) `loadGraph()`; (1468)
   `showRing`; (1471/1473) `$('filter-panel')`/`openSearch`. → Remove all four or first paint throws.
7. **`showAccount` back-button (722–724)** uses `activeRing ? showRing(...) : clearSelection()`.
   → Hardcode to `clearSelection()`. In `clearSelection`, drop `destroyFlow()`/`hidePlayback()` (cut
   features) and reword empty-state to "Select an account to inspect."
8. **Don't over-delete** — the enforcement block (`app.js` ~1508–1578, `INSPECTED_ACCT`/`FZ_QUEUE`,
   Freeze/Clear actions) sits **right after** the live block. Keep it.
9. **Empty left rail** — if ring queue **and** eval card are both cut, the whole `.rail-left` aside
   (`index.html` 47–52) is empty → remove it and regrid `.three-pane` from 3 → 2 columns.

## 9. Per-lane work + ordering hazards

- **P1 (`generator.py`):** delete `LiveFeed` + `BURSTS` (398–544). No change to `generate_dataset`/
  plant/decoys/CLI. ⚠️ **Coordinate with P4:** the `LiveFeed` deletion and the `main.py` line-21 import
  fix **must land in the same push** or `uvicorn` fails to import on `main`.
- **P2 (`structural.py`):** no functional edits. (Optional cosmetic comment cleanup only.)
- **P3 (`scoring.py`/`network.py`):** **no edits.** `score_accounts`/`build_rings`/`detect_fan`/
  `detect_communities` all stay — they produce the risk + ring membership Visual Review consumes.
- **P4 (`api/main.py` + `frontend/`):** the bulk. Backend: remove global graph + 3 stream endpoints +
  `_enforced_ids` + POST `/api/freeze` + `FreezeReq` + `STATE['live']`; add `FREEZE_THRESHOLD=0.90`
  and rewire `_apply_freeze`/`_freeze_reason`/`freeze_config`; **keep** `_enriched_*` + `graph_account`;
  add the `suspicious_only` param (§6). Frontend: all of §4 + §5 + §8 + the Visual Review wiring (§6).
- **P5 (`ai/`):** no edits to `analysis.py`/`llm.py`/`__init__.py`. ⚠️ **Coordinate with P4:** cutting
  `sar.py`/`copilot.py` requires P4 to drop the corresponding imports + routes (`/api/ask`,
  `/api/rings/{id}/sar`, `/api/rings/{id}/goaml`) **in the same push** or startup breaks / routes 500.

## 10. Verification checklist

- [ ] App boots: `uvicorn backend.api.main:app --reload --port 8000` — no `ImportError` (line-21 import drops `LiveFeed`; no dangling `from backend.ai.sar import generate_sar`, no unused `datetime`/`_xesc`).
- [ ] **Tests stay green:** `pytest backend/` (test_structural + test_scoring have **no** coupling to stream/global-graph/freeze_threshold/screening — verified). **Do NOT regenerate/commit `sample_data/`** as part of this work (tests assert against the committed fixture).
- [ ] No dead refs: `grep -n 'showall\|stream/\|fz-threshold\|loadGraph\|startLive\|pauseLive' frontend/app.js` → empty; `grep -n "'/api/graph'" frontend/app.js` → empty (only `/api/graph/account/` survives).
- [ ] Demo path: (1) lands on Accounts + KPIs; (2) **Generate** repopulates; (3) risk≥90% rows show `frozen` automatically; (4) "Under review only" lists frozen/under-review + Review modal shows reason; (5) **Visual Review** opens a small risk-colored ego graph (account + suspicious counterparties + ring members) with legend, and **← Back** returns to Accounts; (6) AI analysis returns a verdict (LLM or template fallback).
- [ ] Freeze fixed: `GET /api/freeze` → 0.90 (or omits); **no** `POST /api/freeze`; high-risk ring auto-freezes ≥0.90; manual Clear unfreezes and is sticky across recompute.
- [ ] Visual Review uses only existing pipeline output (account_risk + build_rings), no new endpoint beyond the optional `suspicious_only` param.
