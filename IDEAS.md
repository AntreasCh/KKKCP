# 💡 Project Ideas — Track: "Keep Money Safe"

**Team:** KKKCP · **Event:** iFX Hack 2026 · **Sponsor:** AWS
**Constraints (decided):** runs **locally only** (no server/hosting; demo on `localhost`) ·
AI layer is **Anthropic Claude** (via AWS **Bedrock** for sponsor points, or the Anthropic API) ·
**hybrid: rule-based engine + AI** · team of **5** each running Claude Code.

> ⚠️ **THE RULE: don't build a wrapper.** A "paste text → call Claude → print answer" app
> loses. Every idea below is built so the **LLM is one signal/layer among several**, sitting
> on top of a **rule-based / algorithmic core that does real work and runs with the AI turned
> off**. That core is the differentiator, the engineering substance, and what fills 20 hours
> for 5 people. If a component can't be explained without saying "we ask Claude," it's a
> wrapper — push the logic into code.

> **How to use this file:** read, add 👍 on the **Votes** line, comment with your name. Lock
> the decision at the bottom.

---

## ⭐ Recommendation

Both top picks are genuine systems, not wrappers, and split cleanly across 5 people:

1. **Idea 1 — MuleNet** (AML graph detection) — *most* engineering substance; the AI is ~5%
   of it. Best "this is real software" story.
2. **Idea 2 — ScamBroker Shield** (multi-signal risk engine) — most relatable demo for an
   online-trading audience; AI is 1 of ~5 scoring signals.

Pick one to build, keep the other as the backup pitch.

---

## Idea 1 — 🕸️ MuleNet — Money-Laundering Network Detector

**Detect laundering *rings* in transaction data — the AI only writes the report.**

The win: 90%+ of this is **graph algorithms + data engineering**. The LLM does one small,
clearly-bounded job (drafting the suspicious-activity narrative). Impossible to mistake for a
wrapper.

**Architecture (layers = depth):**
1. **Synthetic data generator** — emit realistic transaction datasets with *planted* laundering
   patterns and ground-truth labels (mule fan-in/out, layering chains, circular flows,
   structuring just under a €10k report threshold). Pure code.
2. **Graph engine** — build a directed transaction graph (NetworkX / igraph).
3. **Detection algorithms (no LLM):** structuring/smurfing detection · mule-hub fan-in/out +
   temporal bursts · cycle detection (circular flows) · community detection (Louvain) to find
   rings · rapid pass-through (money in→out within N hours) · per-account & per-cluster risk
   scoring.
4. **Interactive graph UI** — Cytoscape.js / vis.js / D3; filter by risk, click a ring to inspect.
5. **AI layer (small):** given a flagged cluster + evidence, Claude drafts a **SAR (Suspicious
   Activity Report)** narrative via structured output. *This is the only LLM call.*
6. **Evaluation harness** — precision/recall vs the planted labels. Judges love "we catch 94%
   of laundering rings with X% false positives."

**5-person split:** P1 data generator + labels · P2 graph build + structuring/cycle algorithms ·
P3 mule-hub + community detection + risk scoring · P4 graph visualization + interaction · P5 SAR
generator (Bedrock) + eval harness + demo.

**Demo:** load dataset → graph renders → "3 laundering rings detected" → click one → see the
pattern + an auto-drafted SAR. **Local-only:** local Python backend + browser viz; no hosting.
**Wrapper check:** ✅ algorithms do the detection; AI only narrates.
- **Votes:**
- **Comments:**

---

## Idea 2 — 🎣 ScamBroker Shield — Multi-Signal Scam/Broker Risk Engine

**"Is this broker/message a scam?" scored by ~5 independent signals — Claude is one of them.**

The win: the engine reaches a verdict by combining **independent rule-based detectors**; the LLM
is one weighted input, not the whole app. The regulator/typosquat/domain logic is the part
nobody else builds.

**Architecture (layers):**
1. **Lexical/heuristic detector (no LLM):** weighted scoring of scam patterns — "guaranteed
   returns", urgency/pressure, crypto-wallet asks, "your account manager", etc.
2. **Domain forensics (no LLM):** WHOIS domain age, suspicious TLDs, cert/HTTPS checks.
3. **Typosquat / lookalike detector (no LLM):** edit-distance + homoglyph check against a curated
   list of *real* regulated brokers — catches `eToreo.com` impersonating `eToro`.
4. **Regulator registry check (no LLM):** offline dataset of CySEC/FCA license numbers — verify a
   *claimed* license number is real and matches the named entity. **This is the killer signal.**
5. **OCR layer:** accept WhatsApp/website screenshots → extract text (local Tesseract, or AWS
   Textract).
6. **AI layer (Claude/Bedrock):** nuanced read of the message — social-engineering tactics — and
   **structured extraction** of claimed entity / license / promised returns to feed signal 4.
7. **Aggregation engine:** explainable weighted risk score; show *which* signals fired and how
   much each contributed (not a black box).
8. **Frontend + eval:** paste/upload → risk gauge + per-signal evidence cards; small curated
   real-vs-scam test set → accuracy metric.

**5-person split:** P1 lexical/heuristic engine + weights · P2 domain forensics + typosquat +
regulator dataset/checker · P3 OCR + Claude analysis (structured output) · P4 aggregation +
explainability + frontend · P5 test-set curation + eval + demo polish.

**Demo:** paste a real scam pitch → "HIGH RISK 92%" with reasons (fake license #, lookalike
domain, pressure language); paste a regulated broker → "LOW RISK, license verified." **Local-only:**
local backend + frontend. **Wrapper check:** ✅ LLM is 1 of ~5 signals.
- **Votes:**
- **Comments:**

---

## Idea 3 — 🛡️ Fraud Radar — Real-Time Transaction Fraud Engine *(solid alternative)*

**Live fraud scoring: feature engineering + anomaly model + rules; AI only explains.**

**Architecture:** synthetic transaction-stream generator · feature engineering (velocity,
geo-mismatch, amount z-score, new-device, odd-hour) · rules + a lightweight anomaly model
(Isolation Forest / statistical) for the score · live dashboard scoring a streaming feed ·
**Claude** turns a flagged transaction's features into a plain-English reason · eval vs labels.

**5-person split:** P1 stream generator · P2 feature engineering · P3 scoring (rules + anomaly
model) · P4 dashboard/UI · P5 explanation layer + eval.

**Wrapper check:** ✅ the model + features do the scoring. *Slightly more "generic dashboard" than
Ideas 1–2, but a strong, safe build.*
- **Votes:**
- **Comments:**

---

## Demoted (given our constraints)

- **DeepKYC (deepfake/fake-ID):** AWS Rekognition **Face Liveness** needs the hosted Amplify flow —
  awkward under local-only and risky in 24h. Skip unless someone has it working fast.
- **ScamGuard (chat-overlay scam interceptor):** hard to make it *not* a wrapper — most of the
  value is the LLM read. Fold its best ideas into Idea 2 instead.

---

## ✅ Decision

- **Chosen idea:** _(fill in once we vote)_
- **One-line pitch:** _________________________________________________
- **Who's doing what:** mirror the 5-person split into `CLAUDE.md` → Team Sync
- **Decided on / by:** _______________
