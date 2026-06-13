# 💡 Project Ideas — Track: "Keep Money Safe"

**Team:** KKKCP · **Event:** iFX Hack 2026 (13–14 June, University of Limassol) · **Sponsor:** AWS

Track goal: *Protect people, businesses, and financial systems from fraud, scams, and
financial crime.* Sub-themes: fraud detection · identity verification · AML · financial
security · consumer protection.

> **How to use this file:** Read the ideas, add comments under each one (sign with your
> name), and vote with 👍 in the "Votes" line. We lock in a decision at the bottom.
> This is the *online-trading* expo (iFX), so ideas that touch **trading / broker / forex /
> crypto fraud** will land hardest with the judges (Industry Impact).

---

## ⭐ Recommendation (read this first)

For a 24-hour build with a strong live demo and high relevance to an **online-trading**
audience, the two strongest bets are:

1. **Idea 1 — ScamBroker Shield** (consumer protection, most relatable demo, AI-heavy)
2. **Idea 4 — MuleNet** (AML graph detection, most technically impressive)

Both are demoable, both map cleanly to AWS services, and both hit all five judging
criteria. Pick one as the build, keep the other as the backup pitch.

---

## Idea 1 — 🎣 ScamBroker Shield
**"Is this broker/investment a scam?" — instant AI verdict**

- **Problem:** "Pig-butchering" and fake-broker scams are the #1 fraud in online trading.
  Victims get a slick WhatsApp/Telegram pitch, a fake trading dashboard, and "guaranteed
  returns." They have no easy way to check legitimacy before wiring money.
- **Solution:** Paste a broker URL, a chat screenshot, or a message. The app returns a
  **risk score + red-flag breakdown**: unregulated/fake license number, domain age,
  "guaranteed profit" language, pressure tactics, mismatched company details, lookalike
  domains of real brokers.
- **Demo (the money shot):** Paste a real scam message → red "HIGH RISK 92%" with a list
  of reasons. Paste a legit regulated broker → green "LOW RISK" with verified license.
- **Stack:** Frontend (React/Next). **Amazon Bedrock** (Claude) for message/text analysis
  and red-flag extraction. **Amazon Textract** to read uploaded chat/website screenshots.
  Optional: scrape/check public regulator registries (CySEC, FCA) + WHOIS domain age.
- **Why it wins:** Innovation (AI scam-pattern detection), Demo (instant + relatable),
  Industry Impact (directly protects retail traders — iFX's whole audience).
- **24h MVP:** Text-in → risk score + reasons. Stretch: screenshot OCR + regulator lookup.
- **Votes:**
- **Comments:**

---

## Idea 2 — 🛡️ Real-Time Transaction Fraud Radar
**Live fraud scoring with human-readable explanations**

- **Problem:** Card/payment fraud needs to be caught in milliseconds, but black-box models
  that just say "fraud: yes/no" don't help analysts act or stay compliant.
- **Solution:** A streaming dashboard that scores each transaction for fraud risk and shows
  **why** (velocity, geo-mismatch, amount anomaly, new device). Analyst can approve/block.
- **Demo:** A simulated live feed of transactions scrolls in; suspicious ones light up red
  with reason tags; click to see the explanation and block.
- **Stack:** Rules engine + lightweight ML (anomaly detection) in Python. **Amazon Bedrock**
  to generate plain-English explanations. Optional **Amazon Fraud Detector** for scoring.
  WebSocket feed → React dashboard.
- **Why it wins:** Technical Execution + Functionality. Very "fintech ops" credible.
- **24h MVP:** Pre-recorded/synthetic transaction stream + rules + explanation panel.
- **Votes:**
- **Comments:**

---

## Idea 3 — 🤳 DeepKYC — Deepfake & Fake-ID Defense
**Stop AI-generated IDs and face-spoofing at onboarding**

- **Problem:** Fraudsters now onboard with AI-generated faces, deepfake selfies, and
  forged/edited ID documents — a massive identity-verification problem for brokers/banks.
- **Solution:** An onboarding check that does **liveness detection** + **document
  tamper/forgery detection** and flags AI-generated faces.
- **Demo:** Try to onboard with a static photo / screen / edited ID → "SPOOF DETECTED."
  Real live selfie + valid ID → "VERIFIED."
- **Stack:** **Amazon Rekognition Face Liveness** (built for exactly this) + Rekognition
  for face match, **Amazon Textract** for ID field extraction, image-forensics checks.
- **Why it wins:** Highly topical (deepfakes), strong AWS-native story, clear demo.
- **Risk:** Face Liveness needs the AWS Amplify SDK flow — get this working *early* or fall
  back to a simpler image-tamper check.
- **Votes:**
- **Comments:**

---

## Idea 4 — 🕸️ MuleNet — Money-Laundering Network Detector
**See the laundering ring, not just the transaction**

- **Problem:** Money laundering hides in *networks* — mule accounts, layering, structuring
  ("smurfing"). Single-transaction checks miss the pattern.
- **Solution:** Build a transaction **graph** and surface suspicious structures: rapid
  fan-in/fan-out (mule hubs), circular flows, and structuring just under reporting limits.
  Visual, interactive graph with risk-ranked clusters.
- **Demo:** Load a transaction dataset → graph renders → "3 suspicious rings detected" →
  click a ring to see the laundering pattern and a generated SAR (Suspicious Activity
  Report) summary.
- **Stack:** Graph analysis (NetworkX, or **Amazon Neptune** for the wow factor),
  visualization (D3 / Cytoscape / vis.js), **Amazon Bedrock** to auto-draft the SAR.
- **Why it wins:** Most technically impressive; great visual; strong Industry Impact (AML).
- **24h MVP:** Synthetic dataset + NetworkX pattern rules + graph viz. Neptune is a stretch.
- **Votes:**
- **Comments:**

---

## Idea 5 — 💬 ScamGuard — Social-Engineering Scam Interceptor
**Browser/chat assistant that warns you mid-conversation**

- **Problem:** Romance/investment ("pig butchering") and impersonation scams play out over
  weeks in chat. Victims don't realize until the money's gone.
- **Solution:** A browser extension / chat overlay that reads the conversation locally and
  flags grooming + investment-pitch patterns ("move to Telegram", "guaranteed 20%/week",
  "send crypto to this wallet") with a real-time warning banner.
- **Demo:** Paste/replay a scam chat → escalating warnings appear as the manipulation
  unfolds; ends with "🚨 This looks like an investment scam — do not send money."
- **Stack:** Browser extension (or web chat sim) + **Amazon Bedrock** for conversation
  classification. Keep analysis privacy-respecting.
- **Why it wins:** Strong consumer-protection + UX story; emotionally resonant demo.
- **Votes:**
- **Comments:**

---

## ✅ Decision

- **Chosen idea:** _(fill in once we vote)_
- **One-line pitch:** _________________________________________________
- **Who's doing what:** see `CLAUDE.md` → Team Sync
- **Decided on / by:** _______________
