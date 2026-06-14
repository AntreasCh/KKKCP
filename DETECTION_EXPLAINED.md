# MuleNet — How Our Fraud Detection Works (Judge Brief)

*A plain-English guide to the whole detection engine. No code needed to follow it.*

---

## 1. The one-sentence pitch

**MuleNet finds money-laundering networks** — not just one suspicious account, but the
whole ring of "mule" accounts criminals use to move dirty money — and it does it
**without falsely accusing innocent customers.**

---

## 2. The problem (why this is hard)

Criminals don't move stolen money in one big obvious transfer. They **split it across
dozens of ordinary-looking accounts** ("money mules") and shuffle it around until it
looks clean. Each account on its own looks innocent. The crime is only visible in the
**pattern across many accounts**.

Real banks have the opposite problem too: their alarm systems are so trigger-happy that
**~95% of alerts are false** — wasting investigators' time on innocent people (a grandma
who got a bonus, a shop having a sale). So the real challenge is:

> **Catch the launderers AND stop crying wolf on legitimate customers.**

---

## 3. The big idea

MuleNet looks at money from **two angles at once**:

1. **Behaviour** — *what* an account does (sudden bursts, money passing straight through, loops…).
2. **Identity & network** — *who* the account is and *who it deals with* (sanctioned? on a shared device with 5 other mules? transacting from abroad?).

It combines ~25 individual fraud signals into a single **risk score (0 = clean, 1 = almost
certainly a mule)** for every account, then **stitches the high-risk accounts back into
the laundering rings** they belong to.

---

## 4. How it works, in 5 steps

1. **Data in** — a list of accounts (with KYC details, country, device, etc.) and their
   transactions (amount, type, channel, origin country, etc.).
2. **Build the money graph** — every account is a dot, every payment is an arrow between dots.
3. **Run ~25 detectors** — each looks for one tell-tale sign of laundering (listed below).
4. **Score every account** — combine the signals into one risk number, the smart way (see §6).
5. **Assemble the rings** — group the connected high-risk accounts into named laundering
   networks, rank them, and explain *why* each was flagged.

The result is the dashboard: a risk-ranked list of accounts, the detected rings, the
evidence behind each flag, and an AI assistant that can write the suspicious-activity
report and answer questions.

---

## 5. The ~25 signals (grouped into 5 families)

You don't need to memorise these — the point for judges is **breadth**: MuleNet covers
every major angle a real anti-money-laundering team uses.

**A. Classic transaction patterns** (the textbook laundering shapes)
- **Structuring / smurfing** — many small deposits kept *just under* the €10,000 reporting limit.
- **Pass-through / layering** — money comes in and is pushed straight back out within hours.
- **Circular flow** — money leaves an account and loops back to it through a chain.
- **Fan-in / fan-out** — many accounts pay into one (or one pays out to many) in a short burst.

**B. Behaviour over time & payment channel**
- **Fiat→crypto conversion** — cash/wire turned into crypto fast (a classic cash-out move).
- **Activity spike** — a normally-quiet account suddenly erupts with activity.
- **Dormant reactivation** — an old, long-inactive account suddenly springs to life as a conduit.
- **Round amounts** — suspiciously "clean" numbers (exact multiples of €1,000).

**C. Who the customer is (KYC & screening)**
- **Sanctions hit** — the customer is on a sanctions list (an automatic red flag).
- **PEP** — a politically-exposed person (higher risk, but *not* a crime by itself).
- **Watchlist / adverse media** — internal watchlist or negative news.
- **Prior SARs** — has been reported before.
- **High-risk country**, **freshly-opened account**, **elevated KYC risk**.
- **Activity vs declared profile** — moves *far* more money than they said they would at sign-up.
- **Shell company**, **high-risk business type** (e.g. crypto exchange, gambling).

**D. Identity & device intelligence**
- **Device / IP linkage** — several "different" customers are actually run from **one device** (one operator).
- **VPN / TOR use**, **repeated failed identity checks**, **geography mismatch** (transacting from a different country than they live in).

**E. Network effects**
- **Guilt by association** — an account that mostly deals with *already-flagged* accounts is lifted.
- **Ring assembly** — the connected high-risk accounts are grouped into the actual laundering network.

---

## 6. The secret to accuracy (this is the clever bit)

Here's the key design idea — **explain this one to the judges, it's what makes us different:**

Signals are split into two kinds:

- **Strong evidence** (structuring, a sanctions hit, device linkage…) — these can **flag an
  account on their own**, because they're conclusive.
- **Risk amplifiers** (high-risk country, PEP, VPN, fresh account, crypto channel…) — these
  **can only *raise* the score of an account that's already behaving suspiciously. On their
  own they can NEVER push a clean customer over the line.**

Why this matters: living in a high-risk country, being a PEP, or buying crypto are **not
crimes**. A naive system flags them and drowns in false alarms. MuleNet treats them as
*context that sharpens a real suspicion*, never as a reason to accuse someone. This
"amplify-but-cap" rule is **mathematically guaranteed** not to create a false positive.

---

## 7. How we *prove* it works

We don't just claim accuracy — we measure it.

- The dataset contains **planted laundering rings** (with a hidden answer key) **and
  "decoys": perfectly legitimate things that look like laundering** — a company's payday
  payroll burst, a shop's flash-sale rush, sub-€10k B2B invoices, inter-company settlement
  loops, even legitimate PEPs.
- A naive detector flags the decoys. **Ours has to tell them apart** — that's what makes the
  accuracy *earned*, not given.
- An automatic scoreboard then grades every run.

**Our current scores:**

| Metric | Score | Plain meaning |
|---|---|---|
| **Precision** | **1.00** | **Zero false accusations** — every account we flag is a real mule. |
| **Recall** | **0.85** | We catch **85% of the mules**. |
| **Ring recall** | **1.00 (19/19)** | We find **every** laundering network planted. |
| **False-positive rings** | **0** | We never invent a fake ring out of legitimate activity. |
| **Automated tests** | **57 passing** | The whole engine is covered by tests. |

> The remaining ~15% we miss are deliberately "thin" accounts that touch the ring only
> once and leave no behavioural trace — they still appear in our **"elevated — review"**
> tier for a human analyst, just below the auto-flag line. That's a deliberate,
> honest trade-off, not a gap we're hiding.

---

## 8. Why it matters (industry impact)

- **Fewer wasted investigations.** Precision-first means analysts chase real criminals, not grandmas.
- **Catches networks, not just individuals.** We surface the whole ring and the kingpin, which is how laundering actually works.
- **Speaks the industry's language.** Sanctions, PEP, structuring, SARs, KYC — every signal maps to a control real AML teams already use.
- **Explainable.** Every flag comes with its evidence, and an AI assistant drafts the regulatory report — so a human can act on it immediately.

---

## 9. Glossary (for quick reference)

- **Money mule** — an account used to move criminal funds, often an ordinary person's account.
- **Structuring / smurfing** — splitting deposits to stay under the reporting threshold.
- **Layering** — passing money through many hops to hide its origin.
- **KYC** — "Know Your Customer": the identity info a bank collects at sign-up.
- **PEP** — Politically Exposed Person (higher-risk customer category).
- **SAR** — Suspicious Activity Report, the filing a bank sends regulators.
- **Precision** — of the accounts we flagged, how many were actually bad.
- **Recall** — of all the bad accounts, how many we caught.

---

## 10. 60-second demo script

1. Click **Generate** → "Here are ~800 accounts and ~4,300 transactions, with hidden laundering rings."
2. Point at the top of the list → "These are auto-flagged. Notice the evidence chips — *structuring, sanctions hit, device linkage*."
3. Open a flagged account → "Every flag is explained. This one shares a device with 5 other accounts — one operator."
4. Show the scoreboard → "**100% precision** — we never falsely accuse. We catch **85%** of mules and **every** ring, with **zero** false rings — and that's against decoys built to fool us."
5. (Optional) Ask the **Ask MuleNet** assistant a question / show the generated SAR.

*MuleNet is a hackathon prototype running locally on synthetic-but-realistic data. The
detection engine is real; the dataset is generated so we can measure accuracy against a
known answer key.*
