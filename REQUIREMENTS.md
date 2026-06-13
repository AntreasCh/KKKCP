# 🕸️ MuleNet — Requirements & Build Spec

**Money-Laundering Network Detector** · Team KKKCP · iFX Hack 2026 · Track: **Keep Money Safe**

> **Read this whole file before you start your part.** It is the contract. The §7 Data
> Contracts and §8 API Contract are frozen — code against them and your piece will compose with
> everyone else's. If you need to change a contract, post in `CLAUDE.md` → Team Sync **before**
> changing it, because it affects everyone.

---

## 1. One-liner

MuleNet ingests a stream of bank transactions, builds a transaction **graph**, and uses graph
algorithms + heuristics to surface **money-laundering rings** (mule accounts, layering chains,
circular flows, structuring). It scores and visualizes the rings, and Claude auto-drafts a
**Suspicious Activity Report (SAR)** for each one.

**Why it's not a wrapper:** detection is ~90% deterministic graph algorithms that run with the AI
turned off. Claude only writes the report at the end.

## 2. Problem & motivation

Money laundering hides in *networks*, not single transactions. Banks must file SARs but analysts
drown in volume and miss the *patterns* — accounts that exist only to relay money (mules),
deposits structured just under reporting limits, and money that loops back to its origin. MuleNet
finds the pattern, ranks it by risk, and produces the paperwork.

## 3. Goals / Non-goals

**Goals (must ship):**
- Generate a realistic synthetic transaction dataset with *planted* laundering rings + labels.
- Detect rings via ≥4 independent algorithms; score accounts and rings.
- Interactive graph UI: see the network, risk-colored; click a ring to inspect it.
- Auto-draft a SAR per ring (Claude); template fallback if AI is unavailable.
- Evaluation: precision / recall / ring-recall vs the planted ground truth.
- Runs **entirely on `localhost`** — one command.

**Non-goals (do NOT build — protects our 24h):**
- No real bank data / external data feeds / scraping.
- No hosting, deployment, auth, user accounts, or database server (in-memory + JSON files only).
- No real-time streaming infra (we *simulate* a feed; no Kafka/queues).
- No mobile app. No multi-page SPA. One page is enough.

## 4. System architecture

```
                ┌─────────────────────────────────────────────┐
   (P1)         │              BACKEND  (Python, local)        │
 generator ──▶  │  dataset.json ─▶ graph.build ─▶ detectors ─▶ │
 + schemas      │     (P1)           (P2)         (P2,P3)      │
                │                                  │           │
                │                          scoring + rings(P3) │
                │                                  │           │
                │     ┌────────────── FastAPI (P4) ┘           │
                │     │   /api/graph /api/rings /api/eval       │
                │     │   /api/rings/{id}/sar ──▶ SAR (P5,Claude)│
                │     │   /api/eval ──▶ eval harness (P5)        │
                └─────┼───────────────────────────────────────┘
                      │ JSON over HTTP (localhost:8000)
                ┌─────▼───────────────────────────────────────┐
   (P4)         │   FRONTEND  (static HTML + vis.js)           │
                │   graph render · risk colors · click ring →  │
                │   detail panel + SAR text                    │
                └─────────────────────────────────────────────┘
```

## 5. Tech stack & how to run

- **Language:** Python 3.11+
- **Backend:** FastAPI + uvicorn (serves the API *and* the static frontend on `localhost:8000`)
- **Graph:** `networkx`; community detection via `python-louvain` (`import community as community_louvain`)
- **Numbers:** `numpy`, `pandas`
- **AI:** Claude — `boto3` (AWS Bedrock) preferred for sponsor points; `anthropic` SDK as fallback.
  Model: `claude-haiku-4-5` for the SAR (cheap/fast; it's a writing task).
- **Frontend:** plain `index.html` + `app.js` + `vis-network` via CDN. **No build step.**

**Run (target):**
```bash
pip install -r backend/requirements.txt
uvicorn backend.api.main:app --reload --port 8000
# open http://localhost:8000
```
AI is optional: set `ANTHROPIC_API_KEY` (or AWS creds for Bedrock). With neither, SAR falls back
to a template.

## 6. Repo structure (create this skeleton in Phase 0)

```
mulenet/
  backend/
    schemas.py              # (P1) SHARED data contracts — define FIRST, freeze early
    data/generator.py       # (P1) synthetic dataset + labels
    graph/build.py          # (P2) tx list -> networkx graph
    detect/structural.py    # (P2) structuring, cycles, pass-through
    detect/network.py       # (P3) fan-in/out hubs, Louvain communities -> rings
    detect/scoring.py       # (P3) findings -> per-account risk + ring scores
    detect/pipeline.py      # (P3/P4) orchestrator: dataset -> {findings, risk, rings}
    ai/sar.py               # (P5) Claude SAR generator + template fallback
    eval/evaluate.py        # (P5) precision/recall vs labels
    api/main.py             # (P4) FastAPI app + static mount
    requirements.txt
  frontend/
    index.html  app.js  style.css      # (P4)
  sample_data/
    dataset.json  labels.json          # (P1) committed early as the shared fixture
  README.md
```

---

## 7. DATA CONTRACTS (frozen — everyone depends on these)

All amounts EUR floats; all timestamps ISO-8601 UTC strings; all IDs strings.
`backend/schemas.py` is the single source of truth — P1 writes it first as Pydantic models or
dataclasses. **Detectors never see ground-truth labels** — those live only in `labels.json`.

**Account**
```json
{ "account_id": "ACC00001", "owner_name": "Maria K.", "account_type": "personal|business",
  "country": "CY", "opened_at": "2025-02-10", "kyc_risk": "low|medium|high" }
```

**Transaction**
```json
{ "tx_id": "TX000123", "timestamp": "2026-06-13T14:32:00Z",
  "src": "ACC00001", "dst": "ACC00042", "amount": 9450.0, "currency": "EUR",
  "channel": "wire|sepa|card|crypto|cash_deposit" }
```

**dataset.json** = `{ "accounts": [Account...], "transactions": [Transaction...] }`

**labels.json** (ground truth, eval only) =
```json
{ "mule_accounts": ["ACC..."],
  "rings": [ { "ring_id": "TRUE_001", "account_ids": ["ACC..."], "tx_ids": ["TX..."],
               "patterns": ["structuring","circular","mule_fanin","mule_fanout","layering"] } ] }
```

**Finding** — what every detector returns (a `List[Finding]`):
```json
{ "detector": "structuring", "subject_type": "account|edge|subgraph",
  "subject_ids": ["ACC..."], "score": 0.0,            // 0..1
  "evidence": { "free": "detector-specific dict" },
  "window": { "start": "ISO", "end": "ISO" } }        // optional
```

**AccountRisk** (scoring output):
```json
{ "account_id": "ACC...", "risk": 0.0, "top_signals": [ {"detector":"...","score":0.0} ] }
```

**Ring** (final detected cluster; `narrative` filled by SAR step):
```json
{ "ring_id": "DET_001", "account_ids": ["ACC..."], "tx_ids": ["TX..."],
  "score": 0.0, "patterns": ["circular","structuring"],
  "key_accounts": ["ACC..."], "narrative": null }
```

**Detector function signature (the integration interface):**
```python
def detect_xxx(graph, accounts: list[dict], transactions: list[dict]) -> list[Finding]: ...
```
`pipeline.run(dataset) -> {"findings": [...], "account_risk": [...], "rings": [Ring...]}`

## 8. API CONTRACT (P4 owns; P5/frontend consume)

Base: `http://localhost:8000`. All responses JSON.

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| POST | `/api/dataset/generate` | `{n_accounts, n_legit_tx, n_rings, seed}` | `{dataset_id, summary}` |
| GET | `/api/graph` | `?max_nodes=` | `{nodes:[{id,label,risk,type}], edges:[{id,source,target,amount,suspicious}]}` |
| GET | `/api/rings` | — | `[Ring without narrative]` (sorted by score desc) |
| GET | `/api/rings/{ring_id}` | — | `Ring + {accounts:[...], transactions:[...], findings:[...]}` |
| GET | `/api/accounts/{id}` | — | `{account, risk, findings, transactions}` |
| POST | `/api/rings/{ring_id}/sar` | — | `{narrative, structured:{summary,parties,activity,recommendation}}` |
| GET | `/api/eval` | — | `{account:{precision,recall,f1}, ring_recall, false_positive_rate, counts}` |

## 9. Detection algorithms (the substance)

Defaults are starting points — tune against §12 eval. Reporting threshold `T = 10_000` EUR.

1. **Structuring / smurfing** (P2, `structural.py`) — an account with ≥3 transactions each in
   `[0.7·T, T)` within a 72h window that sum to ≥ T. Evidence: count, total, window. Score scales
   with count and closeness to T.
2. **Circular flow** (P2) — directed simple cycles of length 2–5 (`networkx.simple_cycles`) where
   timestamps increase around the loop and amount is retained ≥ 0.8 end-to-end within 72h. Score
   by retention × tightness.
3. **Rapid pass-through / layering** (P2) — account receives X then sends ≥ 0.8·X within 24h to a
   *different* counterparty. Classic mule relay. Score by ratio and speed.
4. **Fan-in / fan-out hub** (P3, `network.py`) — account with ≥ F distinct senders (fan-in) or
   recipients (fan-out) within window W (`F=6`, `W=48h`), especially when funds then consolidate.
   Score by degree and temporal burst.
5. **Community detection → rings** (P3) — Louvain on the weighted undirected projection; each
   community scored by density of flagged accounts/edges inside it. Communities above a threshold
   become **Ring** candidates.
6. **(stretch) Bipartite mule layer** — detect a middle layer of accounts that only relay
   (high pass-through, low balance retention).

## 10. Scoring (P3, `scoring.py`)

- **Per account:** `risk = clamp(Σ wᵢ·scoreᵢ)` over findings touching the account, normalized 0..1.
  Default weights: structuring 0.9, circular 1.0, passthrough 0.7, fan 0.8. Keep `top_signals` for
  explainability — the UI shows *why*.
- **Per ring:** combine community density + mean member risk + count of distinct pattern types.
  Output `rings` sorted by score; assign `ring_id = DET_001…`, pick `key_accounts` (top risk).

## 11. SAR generator (P5, `ai/sar.py`)

Input: a detected Ring + its accounts/transactions/findings. Call Claude with **structured output**
(JSON schema) → `{summary, parties, suspicious_activity, recommended_action}`, then format a short
SAR narrative. Use Bedrock if AWS creds present, else Anthropic API, else a deterministic template
that fills from the evidence (so the demo never depends on the network). This is the **only** LLM
call in the system.

## 12. Evaluation (P5, `eval/evaluate.py`)

- **Account-level:** predicted mules = accounts with `risk ≥ τ` (default 0.5). Compute
  precision/recall/F1 vs `labels.mule_accounts`.
- **Ring-level:** a true ring counts as detected if some detected ring overlaps ≥ 60% of its
  accounts. Report ring-recall and the count of false-positive rings.
- Print a table and expose via `/api/eval`. **This is our headline metric for judges.**

---

## 13. WORK BREAKDOWN — one section per agent

Claim your block in `CLAUDE.md` → Team Sync. Each part lists what you own, what you depend on,
and your **definition of done**. Build against `sample_data/` until the real generator lands.

### 👤 P1 — Data & Schemas  *(unblocks everyone — go first)*
- **Owns:** `schemas.py`, `data/generator.py`, `sample_data/dataset.json`, `sample_data/labels.json`.
- **Build:** (1) Define & freeze the §7 schemas. (2) Generator: emit N accounts + legit background
  transactions, then *plant* `n_rings` laundering rings (structuring, circular, fan-in/out,
  layering) and record them in `labels.json`. Deterministic via `seed`.
- **Depends on:** nobody. **Deliver in Phase 0:** a committed `sample_data/` fixture so all others
  can start.
- **DoD:** `python -m backend.data.generator --accounts 1000 --rings 6 --seed 42` writes a valid
  `dataset.json` + `labels.json`; planted patterns are real (a human can trace one).

### 👤 P2 — Graph & Structural Detection
- **Owns:** `graph/build.py`, `detect/structural.py`.
- **Build:** build a `networkx.DiGraph` from transactions (nodes=accounts, edges=txns w/ amount &
  timestamp). Implement detectors **#1 structuring, #2 circular flow, #3 pass-through** returning
  `List[Finding]` per §7.
- **Depends on:** P1 schemas + sample data.
- **DoD:** each detector finds its planted pattern in the sample data and returns valid Findings;
  unit-checkable against `labels.json`.

### 👤 P3 — Network Detection, Scoring & Pipeline
- **Owns:** `detect/network.py`, `detect/scoring.py`, `detect/pipeline.py`.
- **Build:** detectors **#4 fan-in/out** and **#5 Louvain communities → ring candidates**;
  `scoring.py` (§10); `pipeline.run(dataset)` that calls all detectors (P2 + P3) and returns
  `{findings, account_risk, rings}`.
- **Depends on:** P1 schemas; P2 detector signatures (agreed in §7, so you can stub them).
- **DoD:** `pipeline.run(sample_dataset)` returns ranked rings that overlap the planted ones.

### 👤 P4 — API & Frontend  *(owns the integration surface)*
- **Owns:** `api/main.py`, `frontend/` (`index.html`, `app.js`, `style.css`).
- **Build:** FastAPI app implementing every §8 endpoint (calls `pipeline.run`, serves frontend
  static files). Frontend: render the graph with **vis-network**, color nodes by risk, list rings,
  click a ring → detail panel showing pattern + transactions + a "Generate SAR" button that hits
  `/api/rings/{id}/sar`.
- **Depends on:** P3 pipeline shape (stub it from §7 until ready); build UI against a static
  `sample_graph.json` first.
- **DoD:** open `localhost:8000`, see the graph, click a ring, see its detail + SAR.

### 👤 P5 — AI (SAR), Evaluation & Demo
- **Owns:** `ai/sar.py`, `eval/evaluate.py`, demo script, README, final polish.
- **Build:** SAR generator (§11) with template fallback; eval harness (§12) wired to `/api/eval`;
  write the 3-minute demo script (§17); fixed demo seed; help integrate.
- **Depends on:** P3 ring/finding shapes; P1 labels for eval.
- **DoD:** SAR produces a credible report from a ring; `/api/eval` prints precision/recall/ring-
  recall; demo runs start-to-finish twice without a hitch.

## 14. Parallelization plan (how 5 people don't block each other)

1. **Phase 0 (first ~1–2h):** P1 commits `schemas.py` + `sample_data/`. Everyone clones, creates
   the §6 skeleton, and stubs their module returning fake-but-valid §7 objects.
2. Everyone codes against `sample_data/` and the §7 contracts — **no waiting**. P4 builds UI against
   a static graph JSON; P3 stubs P2's detectors via their signatures; P5 evals against labels.
3. Integration happens by swapping stubs for real implementations — interfaces already match.

## 15. Milestones (deadline **Sun 14 June 12:00**)

| When | Target |
|---|---|
| **Phase 0** (afternoon, ~2h) | Skeleton + frozen schemas + sample data committed; everyone stubbed |
| **Phase 1** (evening) | Each module works standalone on sample data; API skeleton returns graph + rings; UI renders sample graph |
| **Phase 2** (overnight) | Real pipeline wired into API; UI hits live endpoints; click→detail→SAR works; scoring tuned |
| **Phase 3** (morning) | Eval numbers in; detection tuned; demo script + 2 dry runs; README |
| **12:00** | Submit |

## 16. Definition of Done (the whole project)

- One command starts it; opens on `localhost`.
- Generate a dataset → graph renders, risk-colored.
- ≥4 detectors active; rings ranked by score.
- Click a ring → pattern + transactions + an auto-drafted SAR.
- `/api/eval` reports precision/recall + ring-recall on the planted labels.
- Works with the AI turned off (template SAR) — AI is additive, not load-bearing.

## 17. Demo script (~3 min)

1. **Problem (15s):** "Laundering hides in networks. Analysts miss the pattern."
2. **Generate (20s):** live → "1,000 accounts, 8,000 transactions, with hidden rings."
3. **Graph (20s):** network renders; red clusters = high risk.
4. **Detect (20s):** "MuleNet flagged 6 rings ranked by risk."
5. **Inspect (40s):** click the top ring → show the structuring + circular-flow pattern and the
   transactions that prove it.
6. **SAR (30s):** "Generate SAR" → Claude drafts the report an analyst would file.
7. **Proof (20s):** `/api/eval` → "94% ring-recall, 3% false positives — and it all runs locally;
   the AI only writes the report."

## 18. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Graph viz eats time / looks bad | Use vis-network with minimal config; fixed layout; cap nodes shown |
| No AWS/Bedrock access | SAR template fallback; AI optional, demo never depends on it |
| Synthetic data too easy/hard | Start simple, add patterns incrementally; **freeze the demo seed** |
| Modules don't integrate | Freeze §7/§8 contracts in Phase 0; build to stubs; small commits |
| Detectors flag everything | Tune thresholds against §12 eval before tuning anything else |
| Git conflicts | Follow `CLAUDE.md` workflow: own your files, `pull --rebase` before push |

## 19. Conventions

Module ownership is in §13 — **stay in your files.** Cross-cutting changes (esp. `schemas.py`,
`pipeline.py`, `api/main.py`) get a heads-up in `CLAUDE.md` → Team Sync first. Branching/commit
discipline: see `CLAUDE.md` → Git workflow.
