# 🏆 MuleNet — Hackathon Readiness & Winning Plan

> **Team KKKCP · iFX Hack 2026 · Track: Keep Money Safe**
> Status as of **Sat 13 June, evening**. Submission deadline **Sun 14 June, 12:00 noon**
> (~18 hours left). Presentations 14:00–15:30 — **3 min pitch + 2 min Q&A**.
>
> Judges score **out of 100**: Does It Work **40%** · Is It Worth Building **35%** ·
> Can You Pitch It **15%** · Is It Clever **10%**.
> Judges' #1 tip: *"A live, working demo beats a beautiful slideshow every time."*

---

## 1. TL;DR — where we stand

**MuleNet is a working, locally-running money-laundering network detector.** It ingests bank
transactions, builds a transaction graph, runs **6 independent graph detectors**, scores and
ranks laundering **rings**, visualises them, and drafts a **Suspicious Activity Report (SAR)**
per ring. The detection is ~90% deterministic graph algorithms — **the AI only writes the
report and answers questions, so the demo never depends on the network.**

**Verified headline metrics (run today on the committed fixture):**

| Metric | Value |
|---|---|
| **Ring-recall** | **1.000** — every planted ring caught (15/15) |
| **False-positive rings** | **0** (of 17 detected) |
| **Account precision** | **1.000** — zero legit accounts flagged |
| **Account recall** | **0.769** (30/39 mules) |
| **Account F1** | **0.870** |
| Determinism | identical every run (seeded) |
| Tests | **9/9 passing** |

**Honest readiness: ~80%.** The product works and the numbers are real. The gaps are **demo
polish, the AI key (copilot is currently disabled), an AWS story for the AWS judge, and two
clean dry-runs.** None are hard; all are doable before noon.

---

## 2. The 30-second project description (for grounding)

> "Money laundering hides in *networks*, not single transactions. Banks must file SARs but
> analysts drown in volume and miss the pattern — mule accounts that only relay money, deposits
> structured just under reporting limits, money that loops back to its origin. **MuleNet finds
> the pattern, ranks it by risk, and writes the paperwork.** And because detection is
> deterministic graph maths, it works with the AI switched off — the AI only drafts the report
> and lets you interrogate the network in plain English."

---

## 3. ✅ Work done (verified)

| Area | Owner | What works | Verified? |
|---|---|---|---|
| **Synthetic data** | P1 | 800 accounts / 4,097 transactions / 15 planted rings (3 per typology), realistic legit hubs (payroll/merchant/utility) + mule profiles; AMLSim-shaped; deterministic via seed | ✅ loads, validated |
| **Graph build** | P2 | `networkx` MultiDiGraph from transactions | ✅ |
| **Structural detectors** | P2 | #1 structuring, #2 circular (time-ordered, value-retaining loops), #3 pass-through | ✅ tests pass |
| **Network detectors** | P3 | #4 fan-in/out (temporal window + legit-hub down-weighting), #5 Louvain communities (seeded/deterministic) | ✅ |
| **Scoring + rings** | P3 | per-account risk, ring assembly (money-edge bounded, merge-on-overlap), peak+mean risk blend, recalibrated normalizer | ✅ tests pass |
| **API** | P4 | FastAPI: `/api/graph`, `/api/rings`, `/api/rings/{id}`, `/api/accounts/{id}`, `/api/eval`, `/api/dataset/generate`, SAR, ask, account-analyze | ✅ all routes live |
| **Frontend** | P4 | light analyst console (3-pane): ranked ring queue · vis-network graph · tabbed inspector; temporal **playback**, **case workflow** (escalate/clear/file), **⌘K search**, per-ring **risk-breakdown** bar, money-flow diagram | ⚠️ verify in dry-run |
| **SAR generator** | P5 | Claude/LLM SAR + **deterministic template fallback** | ✅ template works |
| **"Ask MuleNet" copilot** | P5 | tool-using agent over our data (`list_rings`/`get_ring`/`get_account`/`trace_path`/`compare_rings`) with tool-call trace | ⚠️ **needs API key — currently disabled** |
| **Account AI-analysis** | P5 | one-shot LLM verdict on an account + its neighbours, template fallback | ⚠️ needs key for live |
| **Eval harness** | P5 | precision/recall/F1 + ring-recall + FP-rate, CLI + `/api/eval` | ✅ |

**My contribution this session (P3):** root-caused the account-recall gap and recalibrated the
scoring normalizer (1.6→0.9) — recall **0.359→0.769**, precision held **1.000**, ring metrics
unchanged. Added a 4-test regression guardrail. Pushed to `main`.

---

## 4. 🎯 Scoring-criteria analysis (the 100 points)

### ⚙️ Does It Work? — 40% · *our strongest card*
**What they reward:** real, running, shown doing the thing live.
**Where we are:** **Strong.** One command starts it on localhost; graph renders; rings rank;
click → evidence + transactions; SAR drafts live; eval prints honest numbers. The detection is
deterministic, so the live demo is repeatable.
**Gaps to close to max this:**
- 🔴 **Copilot is disabled without an API key** — set `OPENROUTER_API_KEY` so the agent + tool
  trace runs live (this is also our "clever" moment).
- 🔴 **Two clean dry-runs** (judges' explicit tip). Time the 3 minutes.
- 🟡 Have a **terminal `python -m backend.eval.evaluate`** ready as the proof shot.
**Target: 36–40/40.**

### 💰 Is It Worth Building? — 35% · *the business case*
**What they reward:** genuine problem, real business, who pays.
**The pitch:** AML is a **legally mandated, multi-billion-dollar** burden. Banks, EMIs/fintechs,
payment processors and crypto exchanges **must** file SARs (EU AMLD/6AMLD); false-positive rates
in legacy rule engines run **>90%**, and analysts manually chase alerts. MuleNet cuts the noise
(0 false-positive rings here) and **auto-drafts the SAR** — the exact artifact a compliance team
must produce.
- **Who pays:** Tier-2/3 banks & fintechs without a big in-house FCC team; RegTech vendors;
  PSPs; crypto exchanges; **and it's locally hyper-relevant — Cyprus is a financial-services hub
  under heavy AML/MONEYVAL scrutiny.**
- **Wedge:** sell the network-level "ring" view + SAR drafting as an analyst copilot layered on
  top of existing transaction monitoring.
**Gaps:** articulate this crisply in the pitch + one market-size line. **Target: 30–34/35.**

### 🎤 Can You Pitch It? — 15%
**What they reward:** clear problem→solution→user→next-steps; confident, **honest** demo.
**Plan:** rehearse the §7 script; lead with the live demo, not slides; be candid about
account-recall 0.77 and the AI being additive. **Target: 13–15/15.**

### 💡 Is It Clever? — 10%
**The angle (lead with this):**
1. **"Detection without AI, AI without hallucination."** 90% deterministic graph maths;
   the LLM only writes the report and investigates — so it can't fabricate a detection.
2. **The copilot is an *agent over our own findings*, not a chatbot** — it calls real tools
   (`trace_path`, `compare_rings`) and we **show the tool-call trace** so judges watch it
   investigate.
3. **Networks, not transactions** — we catch the *pattern* (rings/mules/loops), which is where
   real laundering hides and where rule engines fail.
**Target: 8–10/10.**

> **Realistic ceiling: 87–93 / 100** if we close the P0 gaps below.

---

## 5. 👨‍⚖️ Meet the judges — tailored angles

| Judge | Role | Cares most about | How we win them |
|---|---|---|---|
| **Elena Georgiou Strouthos** | CTO, Cocoon Creations | Technical execution, does-it-actually-work, clean product | Show the live, repeatable demo + the eval numbers + "not a wrapper" architecture. Engineer-to-engineer credibility. |
| **Nikiforos Botis** | Sr. Solutions Architect, **AWS** Public Sector | Cloud architecture, scalability, **AWS services** | ⚠️ **We pivoted off Bedrock to OpenRouter.** Prepare a crisp **AWS deployment story**: Bedrock for SAR/copilot, detection on Lambda/Fargate, transactions in S3, graph in **Amazon Neptune**, Textract/Rekognition for KYC docs. Ideally re-enable the **Bedrock fallback path** so we can say "the AI runs on Bedrock" truthfully. This judge is the sponsor — give him an AWS hook. |
| **Panis Pieri** | Founder, Panis.News · Cyprus Computer Society | Societal impact, clarity, originality, local relevance | Lead with the **Cyprus AML / financial-crime** angle and the clear story. Make it understandable to a non-banking audience. |
| **Dr. Andreas Artemiou** | Vice Rector, University of Limassol (statistics/data-science background) | Methodological rigor, sound algorithms, honest evaluation | Emphasise the **eval methodology** (precision/recall/ring-recall vs labelled ground truth), determinism, and that we *measured* false positives. Be honest about the recall trade-off — he'll respect candor over hand-waving. |

---

## 6. 🚧 Requirements left — prioritized gap list (to noon Sun)

### 🔴 P0 — demo-blocking / must-do
| # | Task | Owner | Est. | Why |
|---|---|---|---|---|
| 1 | **Set `OPENROUTER_API_KEY`** (gitignored `.env`) and confirm copilot returns a live answer + tool-call trace | P5 | 15 min | Our cleverest feature is currently disabled |
| 2 | **Update `DEMO.md`** — it's stale: says Anthropic key (now OpenRouter), "600 accts/2,500 tx" (now 800/4,097), and "Louvain non-deterministic / ≈24–26 FP rings" (now deterministic, 17 rings, 0 FP). Fix numbers + the AI-key line | P5 | 20 min | Demo script must match reality |
| 3 | **AWS story** for Nikiforos: re-enable Bedrock fallback **or** prepare the deployment-architecture answer | P5 + P3 | 45 min | AWS is the sponsor & a judge |
| 4 | **Two clean dry-runs**, timed to 3:00 | whole team | 40 min | Judges' explicit #1 tip |
| 5 | **Decide the demo machine**, confirm `pip install -r backend/requirements.txt` clean, server boots, browser loads | P4 | 20 min | No surprises on stage |

### 🟡 P1 — high value
| # | Task | Owner | Est. |
|---|---|---|---|
| 6 | One **slide / title card**: problem · solution · market · ask (backup only — demo leads) | P5 | 30 min |
| 7 | Rehearse the **business case** + market-size line + Cyprus relevance | pitcher | 20 min |
| 8 | Confirm frontend features (playback, case workflow, ⌘K, risk bar) work end-to-end | P4 | 30 min |
| 9 | Q&A prep — rehearse answers to the hard questions in §7 | whole team | 30 min |

### 🟢 P2 — nice-to-have (only if time)
| # | Task | Owner |
|---|---|---|
| 10 | Push account-recall past 0.77 (new consolidation/collector signal in `network.py`) — **risks precision; only if a precision-safe version verifies** | P3 |
| 11 | Visual polish, empty-state handling, mobile-safe layout | P4 |

---

## 7. 🎤 The 3-minute pitch + 2-min Q&A

### Beat-by-beat (rehearse to 3:00)
| # | Time | Beat | Say / do |
|---|---|---|---|
| 1 | 0:20 | **Problem** | "Laundering hides in networks. Banks must file SARs; analysts drown and miss the pattern." |
| 2 | 0:20 | **The data** | Open the app: "800 accounts, ~4,000 transactions, with laundering rings hidden inside." |
| 3 | 0:20 | **Graph** | "Red clusters = high-risk accounts MuleNet surfaced — automatically, with no AI." |
| 4 | 0:40 | **Inspect** | Click the top ring → show the structuring + circular evidence and the *actual transactions* that prove it. |
| 5 | 0:30 | **Clever — copilot** | Ask: *"Trace how money flows through the top ring and why it's suspicious."* Show the **tool-call trace** — the agent investigating our own data. |
| 6 | 0:25 | **SAR** | "Generate SAR" → the report an analyst would file (template fallback if offline). |
| 7 | 0:25 | **Proof** | `python -m backend.eval.evaluate`: "**Ring-recall 1.0, zero false-positive rings**, and it runs locally — the AI only writes the report." |

### Honest disclosures (say these — Artemiou & the tips reward candor)
- "Account-level recall is **77%** with **100% precision** — we deliberately don't flag a legit
  account to chase the last few mules; in compliance, false positives are the expensive problem."
- "Data is synthetic but **AMLSim-shaped**; the detection is real graph maths, not a demo trick."
- "The AI is **additive** — turn it off and detection still works."

### Anticipated Q&A (prep answers)
- *"How is this different from existing transaction-monitoring?"* → We work at the **network/ring**
  level and auto-draft the SAR; rule engines fire per-transaction with >90% false positives.
- *"Does it use AWS?"* → (P0 #3) "Detection is cloud-agnostic; the AI layer runs on **Bedrock**
  [if re-enabled] / is Bedrock-ready, and the production architecture is Neptune + Lambda + S3."
- *"How do you know it works on real data?"* → "We evaluate against **labelled ground truth** —
  precision/recall/ring-recall — and report false positives honestly."
- *"What's the business model / who pays?"* → Tier-2/3 banks, fintechs, PSPs, crypto exchanges,
  RegTech vendors; locally relevant given Cyprus's AML obligations.
- *"What would you build next?"* → real-time scoring on streaming transactions; analyst feedback
  loop; explainability export for regulators.

---

## 8. ⚠️ Risks & mitigations

| Risk | Mitigation |
|---|---|
| Copilot/AI fails live (no key / rate limit / 401) | Template SAR + "AI is additive" framing; demo the deterministic detection regardless. **Set the key and test before stage.** |
| AWS judge asks "where's AWS?" | §6 P0 #3 — Bedrock fallback or the deployment-architecture answer. |
| Demo machine hiccup | Decide the machine early; pre-install; demo on the committed `sample_data/` (no live generate needed). |
| Over-running 3 minutes | Rehearse twice; cut beat #6 (SAR) first if short on time. |
| "Synthetic data" objection | Be upfront; stress AMLSim shape + real graph algorithms + honest eval. |

---

## 9. Final pre-submission checklist
- [ ] `OPENROUTER_API_KEY` set; copilot returns a live answer **with a tool-call trace**
- [ ] `DEMO.md` numbers + AI-key line corrected
- [ ] AWS story ready (Bedrock path or architecture answer)
- [ ] `pip install -r backend/requirements.txt` clean on the demo machine; server boots; browser loads
- [ ] `python -m backend.eval.evaluate` prints the scoreboard (ring-recall 1.0)
- [ ] Click top ring → evidence + transactions render
- [ ] "Generate SAR" returns a narrative
- [ ] **Two full dry-runs done, timed to 3:00**
- [ ] Pitcher + Q&A roles assigned; honest-disclosure lines rehearsed
- [ ] Code committed & pushed; `main` green (9/9 tests)
