# C6 — Crypto Chain-Analysis: implementation preparation

**Status: PLAN ONLY — not implemented.** This is the prep for the last Tier-C item
(C6), deferred earlier because it's the heaviest. It needs a *crypto/wallet layer* the
current account↔transaction model doesn't have. Everything below is additive and follows
the same discipline as Tier A/B/C: optional/defaulted schema, generator correlates with
mules + plants hard-negatives, detectors are precision-safe, eval kept green, TDD.

## What C6 must detect (from the original brief)
1. **Mixer / tumbler exposure** — funds to/from a mixing service.
2. **Darknet-market exposure** — funds to/from a known darknet wallet.
3. **High-risk wallet exposure** — sanctioned/flagged wallets, scam addresses.
4. **Chain-hopping** — rapid asset/chain switches (BTC→ETH→USDT) to break the trail.
5. **Rapid fiat→crypto conversion** — *already shipped as B3* (`detect_fiat_to_crypto`); C6 enriches it with the wallet destination.
6. **Many wallets consolidating into one account** — crypto fan-in.

## The core problem: there is no wallet layer yet
Today a `Transaction` is account→account with a `channel` (incl. `crypto`), but a crypto
transfer has an **external wallet** on one side and **no on-chain context** (asset, the
counterparty address, that address's reputation). C6 is mostly about modelling that.

## Data model — two options

### Option A — lightweight wallet *tagging* (RECOMMENDED for the hackathon)
Don't model a full on-chain graph. Tag the external endpoint of each crypto transaction and
keep a small labelled-wallet "threat-intel" list. Additive to `schemas.py`:

```python
# New literal
WalletLabel = Literal["mixer", "darknet", "high_risk", "exchange", "clean"]

# Transaction — additive optional fields (only set for channel == "crypto")
crypto_asset: Optional[str] = None          # "BTC" | "ETH" | "USDT" | ...
counterparty_wallet: Optional[str] = None   # external wallet address on the other side
wallet_label: Optional[WalletLabel] = None  # reputation of that wallet (from the intel list)
```

Plus a tiny reference list emitted alongside the dataset (or inlined): a dict of
`wallet_address -> WalletLabel` (the "screening list"). This is enough for items 1, 2, 3,
5, 6 and a *simplified* 4.

**Pros:** ~one Tier-C-sized change. **Cons:** chain-hopping (item 4) can only be approximated
(a sequence of crypto txns with switching `crypto_asset`), not a true address graph.

### Option B — full wallet entities (only if you want real chain-hopping)
Add a `Wallet` entity and `WalletTransfer` edges (on-chain hops) as a separate graph, linked
to bank accounts at the on/off-ramp. Models chain-hopping properly (wallet→wallet→wallet
across assets). **Much** heavier: a second graph, its own build/detect path, much more
generator work. **Not recommended for the time budget** — do Option A, note the limitation.

> Decision needed before coding: **A or B.** Recommendation: **A**, ship items 1/2/3/5/6 well,
> approximate 4, and label the chain-hop detector as a simplified heuristic.

## Generator work (Option A)
- **Labelled-wallet list:** ~30–50 wallets, weighted mostly `clean`/`exchange`, a minority
  `mixer`/`darknet`/`high_risk`.
- **Tag existing crypto txns:** for each `channel=="crypto"` transaction, set `crypto_asset`,
  `counterparty_wallet`, and `wallet_label`. Legit crypto → `exchange`/`clean`; **mule** crypto
  legs → biased toward `mixer`/`darknet`/`high_risk` (the correlation that makes detection work).
- **New typologies (append, fresh IDs — preserves fixture):**
  - *Mixer cash-out:* a mule converts fiat→crypto (reuses B3 shape) then sends to a `mixer` wallet.
  - *Crypto consolidation:* many distinct `counterparty_wallet`s send crypto into one account in a
    short window (crypto fan-in).
  - *Chain-hop (approx):* one account makes a rapid sequence of crypto txns switching `crypto_asset`
    (BTC→ETH→USDT) within hours before an off-ramp.
- **Hard negatives:** legit heavy crypto users transacting only with `exchange`/`clean` wallets,
  so exposure detection stays precision-earned (mirrors the payroll/settlement decoys).

## Detectors — new `backend/detect/crypto.py`
| Detector | Logic | Strength |
|---|---|---|
| `detect_mixer_exposure` | account has crypto txns whose `wallet_label ∈ {mixer, darknet}` | **strong / near-auto-flag** (like `sanctions_hit`) — direct mixer/darknet use is conclusive; plant only on mules to keep precision |
| `detect_high_risk_wallet` | exposure to `high_risk` wallets; score by share/count | contributor (weight ~0.6) |
| `detect_wallet_consolidation` | ≥N distinct `counterparty_wallet`s funding one account in a window | contributor (crypto fan-in; reuse the temporal-window helper from `network.detect_fan`) |
| `detect_chain_hopping` | rapid `crypto_asset` switches by one account within a short window | capped amplifier (approximate signal) |

Rapid fiat→crypto (item 5) stays in B3; optionally enrich its evidence with the destination
`wallet_label`.

## Scoring integration (`scoring.py`)
- `mixer_exposure` → treat like **C1 `sanctions_hit`** (Pass-4 screening escalation) since direct
  mixer/darknet exposure is near-conclusive — **safe only if the generator labels those wallets on
  mules exclusively**, exactly as `sanctioned` is handled today.
- `high_risk_wallet`, `wallet_consolidation` → `WEIGHTS` contributors (NOT in `STRONG` → don't seed
  rings, mirroring `device_linkage`/`fiat_to_crypto`).
- `chain_hopping` → add as a capped component in the Pass-3 amplifier (`_profile_signals`/`PROFILE_WEIGHTS`).
- Add new detector names to `WEIGHTS`; keep them out of `STRONG`.

## Precision plan (the non-negotiable)
- The separating signal is the **wallet label**: `exchange`/`clean` = normal (a legit user buys
  crypto on Coinbase), `mixer`/`darknet`/`high_risk` = bad. Keep strong escalation only on
  `mixer`/`darknet`, and only plant those on mules → precision stays 1.0 by construction.
- Everything else is a capped amplifier (can't push an unflagged account over τ).
- Re-run `python -m backend.eval.evaluate` after each detector; the guardrail tests
  (`precision==1.0`, `legit_max<0.45`, `ring_recall==1.0`, `0 FP rings`) must stay green.

## UI / API
- Signals flow into `top_signals` automatically (no API change needed to *flag*).
- Nice-to-have: a "crypto exposure" sub-panel in the account detail showing the counterparty
  wallet + its label (touches `api/main.py` (P4) + `frontend/`).

## Effort & sequencing (Option A)
1. **Schema + generator** (wallet list, tag crypto txns, mixer/consolidation typologies, hard-negs) — ~½–1 unit.
2. **`detect_mixer_exposure` + scoring escalation** — TDD + eval. (Highest value, biggest "wow".)
3. **`detect_wallet_consolidation`** — TDD + eval.
4. **`detect_high_risk_wallet`** — TDD + eval.
5. **`detect_chain_hopping` (approx)** — TDD + eval; label clearly as heuristic.
6. Regenerate fixture; full suite + eval green; optional UI panel.

Roughly **2× a single Tier-C item** for Option A (it's a new data sub-domain + 3–4 detectors).
Option B is several times that.

## Files this will touch (for the Team-Sync / git workflow)
- `backend/schemas.py` (P1) — additive crypto fields (+ a labelled-wallet artifact)
- `backend/data/generator.py` (P1) — wallet labels, crypto tagging, new typologies
- **new** `backend/detect/crypto.py` (P2/P3)
- `backend/detect/pipeline.py`, `backend/detect/scoring.py` (P3)
- `backend/tests/test_tier_c6.py` (new)
- `sample_data/` regenerated (shared — flag to team)
- optional: `backend/api/main.py` (P4) + `frontend/` for the exposure panel

## Open questions to settle before implementing
1. **Option A or B?** (recommend A.)
2. Is `mixer_exposure` allowed to **auto-flag** (like sanctions), or stay a capped amplifier?
   (Recommend auto-flag for mixer/darknet, amplifier for high_risk.)
3. Do we want the optional crypto **exposure panel** in the UI, or signals-only?
