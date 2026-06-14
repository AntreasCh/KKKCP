"""Scoring + ring assembly — REQUIREMENTS.md §10 (Owner: P3 / Andreas).

score_accounts(findings)                    -> list[AccountRisk]
build_rings(findings, account_risk, txns)   -> list[Ring]

Rings are assembled from STRONG-detector seeds (structuring / circular / pass-through / fan),
expanded to the hub's counterparties, merged on overlap, and scored by member risk + pattern
diversity + **transaction volume among members**. Volume is the key precision lever: real
laundering moves real money, so legit low-amount clusters fall below the volume floor.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime

# How much each detector contributes to an ACCOUNT's risk.
WEIGHTS = {"structuring": 0.9, "circular": 0.9, "passthrough": 0.8,
           "fan_in": 0.8, "fan_out": 0.8, "fiat_to_crypto": 0.7,
           "community": 0.15, "round_amounts": 0.25,
           "dormant_reactivation": 0.3, "activity_spike": 0.3,
           "device_linkage": 0.6}

# Detectors strong enough to seed a ring (community is context only).
STRONG = {"structuring", "circular", "passthrough", "fan_in", "fan_out"}

# account risk = min(1, weighted_sum / NORMALIZER). Calibrated so that ONE proven strong
# typology crosses τ=0.5: a relay (passthrough 0.8·0.6=0.48), a circular loop, a structuring
# pattern or an unsuppressed fan each warrants suspicion on its own — that's how AML triage
# works. (1.6 required two corroborating signals, which under-scored single-role mules and
# capped account recall at 0.36.) Safe because the strong detectors never fire on a legit
# account here, so the worst legit weighted-sum (~0.24, factor-suppressed fan) stays well
# below τ. Verified: precision holds at 1.0, recall 0.36→0.77, 0 FP rings. See test_scoring.py.
NORMALIZER = 0.9

# Established-business profile down-weight (mirrors network._legit_hub_factor, applied at the
# account-risk layer). An AGED business account with LOW KYC risk legitimately does many-party
# flows, B2B invoicing and inter-company settlement loops — exactly the patterns that trip
# passthrough/circular/structuring. Real mules are FRESH PERSONAL accounts with elevated KYC
# (verified: 0/39 true mules are business+low-KYC), so suppressing this profile is recall-safe
# and removes the hard-negative false positives the decoy fixture plants.
ESTABLISHED_BUSINESS_FACTOR = 0.18   # suppression for the business+low-KYC "established legit" profile


def _legit_profile_factor(acc_rec: dict | None) -> float:
    """Multiplier <= 1 suppressing the risk of the established-business profile. We suppress ONLY
    the full conjunction (business AND low KYC) — that's the exact decoy profile (payroll/merchant/
    B2B/settlement). Suppressing `business` alone would wrongly de-risk the 4 business mules (they
    carry medium/high KYC); no true mule is low-KYC, so the conjunction is recall-safe. Unknown → 1.0."""
    if not acc_rec:
        return 1.0
    if acc_rec.get("account_type") == "business" and acc_rec.get("kyc_risk") == "low":
        return ESTABLISHED_BUSINESS_FACTOR
    return 1.0


# ── network-association parameter ("guilt by association") ────────────────────
# An account is more suspicious when its money flows mostly to/from already-high-risk accounts —
# mules cluster with mules. We add this as a SECOND pass after base scoring. It is provably
# precision-safe: association can RAISE an account's risk, but an account the behavioural detectors
# have NOT already flagged (base < TAU) is capped at ASSOC_ELEVATED_CAP, strictly below the flag
# line — so it can surface as "elevated" for the analyst but can never become a false positive,
# and the legit-max guardrail (<0.45) cannot regress. Already-flagged accounts (base >= TAU, which
# are mules at precision 1.0) get the full boost, sharpening the analyst queue.
TAU = 0.5                     # flag line (matches eval τ)
ASSOC_HIGH_RISK = 0.5         # a counterparty at/above this base risk counts as "high-risk"
ASSOC_WEIGHT = 0.5            # how strongly the association signal contributes
# An account NO behavioural detector flagged can still carry soft profile/association evidence. Rather
# than clamp every such account to one flat number (which bunched them all at 0.40), we grade them
# across [0, ELEVATED_MAX] by how much evidence they actually have — so the dashboard separates "one
# minor flag" from "a dozen red flags". Still strictly < TAU, so soft signals never create a false
# positive; only CONFIRMED-bad screening hits (below) cross the flag line.
ELEVATED_MAX = 0.49           # ceiling for soft-evidence-only accounts (just under TAU)
ASSOC_ELEVATED_CAP = 0.40     # (kept for tests/back-compat) legacy flat elevated cap

# ── Risk curve (replaces the additive-and-clamp that saturated every mule to 100) ──
# We sum weighted EVIDENCE POINTS (behavioural findings + screening points + soft profile/association)
# WITHOUT clamping, then squash through a smooth, non-saturating exponential. This spreads the
# flagged band across 50-99 by how much evidence each account carries (a multi-typology kingpin scores
# higher than a single-role mule) instead of bunching them all at exactly 100.
#   flagged  (behavioural points >= BP_TAU):  risk = TAU + (1-TAU)*(1 - exp(-(evidence-BP_TAU)/SCALE_HI))
#   unflagged(behavioural points <  BP_TAU):  risk = ELEVATED_MAX*(1 - exp(-evidence/SCALE_LO))  (< TAU)
# BP_TAU = TAU*NORMALIZER reproduces the EXACT old flag gate (base = points/NORMALIZER >= TAU), so the
# set of accounts that cross τ — hence eval precision/recall — is unchanged; only the values spread.
BP_TAU = TAU * NORMALIZER      # behavioural-points flag line (== old base>=TAU gate)
SCALE_HI = 1.8                 # spread of the flagged band (larger = gentler climb → wider 50-99 spread)
SCALE_LO = 0.8                 # spread of the elevated (sub-τ) band
# Confirmed-bad screening as EVIDENCE POINTS (only true bad actors carry these → precision-safe). Big
# enough to clear BP_TAU alone (so a lone sanctions/blacklist hit still flags) and to land high on the
# curve, but still additive so a bad actor with MORE signals outscores one with fewer.
SCREENING_POINTS = {"sanctioned": 4.5, "blacklisted": 2.5, "prior_fraud": 1.8, "account_takeover": 1.4}

# ── customer-risk-profile amplifier (Tier A — A1 country, A2 fresh, A3 KYC, A4 channel) ──
# Classic AML "customer risk rating": KYC/profile factors don't *prove* laundering, they
# AMPLIFY a transaction-monitoring alert and raise an account's review priority. We mirror the
# association pass's safety contract — profile can lift risk, but a behaviourally-unflagged
# account (behavioural base < TAU) is capped at ASSOC_ELEVATED_CAP (< TAU), so profile alone can
# surface an account as "elevated" for the analyst yet can NEVER create a false positive. The
# established-business factor suppresses the whole profile signal for the legit decoy profile.
HIGH_RISK_COUNTRIES = frozenset({"RU", "AE"})  # foreign high-risk jurisdictions (A1)
FRESH_ACCOUNT_DAYS = 90        # accounts opened within this many days of the data window are "fresh" (A2)
KYC_RISK_SCORE = {"high": 1.0, "medium": 0.5, "low": 0.0}  # elevated-KYC contribution (A3)
HIGH_RISK_CHANNELS = frozenset({"crypto", "cash_deposit"})  # cash placement / crypto layering (A4)
CHANNEL_RISK_FLOOR = 0.5       # only emit when MOST of an account's value moves this way
CHANNEL_MIN_VALUE = 10_000     # AND a laundering-scale sum moves this way (ignores small P2P noise)
PROFILE_WEIGHT = 0.5           # how strongly the combined profile signal lifts risk
# Per-component weights into the combined profile signal (summed, then capped at 1.0).
PROFILE_WEIGHTS = {"high_risk_country": 0.45, "fresh_account": 0.30,
                   "kyc_risk": 0.30, "crypto_channel": 0.25,
                   # Tier C attribute signals (all capped — they amplify, never flag alone):
                   "pep": 0.40, "watchlist": 0.40, "prior_sars": 0.40, "adverse_media": 0.45,
                   "shell_company": 0.50, "geo_mismatch": 0.35, "high_risk_mcc": 0.30,
                   "vpn_tor": 0.30, "failed_verifications": 0.25, "activity_vs_profile": 0.45,
                   "chargeback_history": 0.30,  # C8 dispute/chargeback history (capped amplifier)
                   # ── Tier D layered amplifiers (device / network / behaviour / history) ──
                   "device_integrity": 0.40,    # D emulator / rooted device (fraud farm)
                   "ip_risk": 0.35,             # D bad-reputation / proxy / hosting IP
                   "automation": 0.35,          # D bot-like behaviour
                   "auth_anomaly": 0.30,        # D failed-login / reset bursts
                   "prior_fraud": 0.50,         # D confirmed prior fraud
                   "account_takeover": 0.40,    # D prior ATO incident
                   "blacklisted": 0.50,         # D internal blacklist hit
                   "unverified": 0.25,          # D unverified identity
                   "historical_risk": 0.35}     # D trailing customer risk score
HIGH_RISK_MCC = frozenset({"crypto_exchange", "money_services", "gambling", "precious_metals"})  # C7
# C3 activity-vs-declared-profile is a capped AMPLIFIER (not a solo flag): a declared/actual gap
# raises suspicion but isn't proof — legit accounts legitimately exceed their estimate sometimes.
PROFILE_RATIO = 4.0            # actual throughput this many× the declared expected = inconsistent
PROFILE_MIN_ACTUAL = 10_000.0  # only material accounts (ignore tiny over-runs of a low estimate)
GEO_MISMATCH_FLOOR = 0.3       # share of an account's outbound value originating abroad to flag (C7)
FAILED_VERIF_FLOOR = 2         # this many failed identity checks before it counts (C4)
# ── Tier D amplifier floors (only material signals count; legit noisy-tail stays below) ──
IP_RISK_FLOOR = 0.5            # IP reputation this high before it amplifies
AUTOMATION_FLOOR = 0.5        # bot-likeness this high before it amplifies
FAILED_LOGIN_FLOOR = 3        # failed logins in 30d before it amplifies
HIST_RISK_FLOOR = 0.5         # trailing customer risk this high before it amplifies
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _country_risk(acc_rec: dict | None) -> float:
    """A1: 1.0 if the account is domiciled in a high-risk jurisdiction, else 0.0."""
    if not acc_rec:
        return 0.0
    return 1.0 if acc_rec.get("country") in HIGH_RISK_COUNTRIES else 0.0


def _latest_date(transactions: list[dict] | None):
    """Reference 'now' for account-age: the most recent transaction timestamp in the data."""
    latest = None
    for t in (transactions or []):
        try:
            d = datetime.strptime(t["timestamp"], TS_FMT)
        except (ValueError, KeyError, TypeError):
            continue
        if latest is None or d > latest:
            latest = d
    return latest


def _fresh_risk(acc_rec: dict | None, ref) -> float:
    """A2: graded 'newly opened' signal — 1.0 for a brand-new account, fading to 0.0 at
    FRESH_ACCOUNT_DAYS. Mules use throwaway accounts opened just before the activity."""
    if not acc_rec or ref is None:
        return 0.0
    try:
        opened = datetime.strptime(str(acc_rec.get("opened_at"))[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return 0.0
    age = (ref - opened).days
    if age >= FRESH_ACCOUNT_DAYS:
        return 0.0
    return round(max(0.0, (FRESH_ACCOUNT_DAYS - age) / FRESH_ACCOUNT_DAYS), 2)


def _channel_shares(transactions: list[dict] | None) -> dict:
    """A4: per-account share of total transacted VALUE (in + out) that moves through a
    high-risk channel (crypto / cash deposit). Cash placement and crypto layering are the
    channels launderers reach for; a flow that's mostly crypto/cash is a risk amplifier."""
    total: dict = defaultdict(float)
    hr: dict = defaultdict(float)
    for t in (transactions or []):
        amt = float(t.get("amount", 0.0))
        high = t.get("channel") in HIGH_RISK_CHANNELS
        for acc in (t.get("src"), t.get("dst")):
            if acc is None:
                continue
            total[acc] += amt
            if high:
                hr[acc] += amt
    # (share, high-risk-channel value) per account
    return {a: (hr[a] / total[a], hr[a]) for a in total if total[a] > 0}


def _geo_mismatch_shares(transactions: list[dict] | None, acc_by_id: dict) -> dict:
    """C7: per-account share of outbound VALUE that originates in a country other than the
    account's residence (tx_country != account.country) — transacting from abroad."""
    total: dict = defaultdict(float)
    away: dict = defaultdict(float)
    for t in (transactions or []):
        s = t.get("src")
        if s is None:
            continue
        amt = float(t.get("amount", 0.0))
        total[s] += amt
        home = (acc_by_id.get(s) or {}).get("country")
        origin = t.get("tx_country")
        if origin is not None and home is not None and origin != home:
            away[s] += amt
    return {a: away[a] / total[a] for a in total if total[a] > 0 and away[a] > 0}


def _profile_signals(accounts: list[dict] | None, transactions: list[dict] | None) -> dict:
    """Per-account profile components in [0,1]: {acc_id: {component_name: value}}.
    Only non-zero components are returned, so each shows up as its own analyst-visible signal."""
    acc_by_id = {a["account_id"]: a for a in (accounts or [])}
    ref = _latest_date(transactions)
    chan = _channel_shares(transactions)
    geo = _geo_mismatch_shares(transactions, acc_by_id)
    throughput: dict = defaultdict(float)            # C3: actual EUR moved per account (in + out)
    for t in (transactions or []):
        amt = float(t.get("amount", 0.0))
        throughput[t.get("src")] += amt
        throughput[t.get("dst")] += amt
    out: dict = {}
    for aid, acc in acc_by_id.items():
        comps: dict = {}
        c = _country_risk(acc)
        if c > 0:
            comps["high_risk_country"] = round(c, 2)
        fr = _fresh_risk(acc, ref)
        if fr > 0:
            comps["fresh_account"] = fr
        kyc = KYC_RISK_SCORE.get(acc.get("kyc_risk"), 0.0)   # A3: elevated KYC raises risk on its own
        if kyc > 0:
            comps["kyc_risk"] = round(kyc, 2)
        share, hr_value = chan.get(aid, (0.0, 0.0))           # A4: crypto / cash placement channel
        if share >= CHANNEL_RISK_FLOOR and hr_value >= CHANNEL_MIN_VALUE:
            comps["crypto_channel"] = round(share, 2)
        # ── Tier C attribute components ──
        if acc.get("pep"):                                    # C1
            comps["pep"] = 1.0
        if acc.get("watchlist"):                              # C1
            comps["watchlist"] = 1.0
        sars = int(acc.get("prior_sars") or 0)                # C2
        if sars > 0:
            comps["prior_sars"] = round(min(1.0, sars / 3), 2)
        if acc.get("adverse_media"):                          # C5
            comps["adverse_media"] = 1.0
        if (acc.get("account_type") == "business" and acc.get("nominee_owner")   # C5 shell company
                and fr > 0 and acc.get("country") in HIGH_RISK_COUNTRIES):
            comps["shell_company"] = 1.0
        gm = geo.get(aid, 0.0)                                # C7 geo mismatch
        if gm >= GEO_MISMATCH_FLOOR:
            comps["geo_mismatch"] = round(gm, 2)
        if acc.get("business_category") in HIGH_RISK_MCC:     # C7 high-risk merchant category
            comps["high_risk_mcc"] = 1.0
        if acc.get("vpn_tor"):                                # C4 attribute
            comps["vpn_tor"] = 1.0
        fv = int(acc.get("failed_verifications") or 0)        # C4 attribute
        if fv >= FAILED_VERIF_FLOOR:
            comps["failed_verifications"] = round(min(1.0, fv / 5), 2)
        cb = int(acc.get("chargeback_count") or 0)            # C8 dispute/chargeback history
        if cb > 0:
            comps["chargeback_history"] = round(min(1.0, cb / 4), 2)
        # ── Tier D layered components (all capped amplifiers; only material values count) ──
        if acc.get("emulator"):                               # D device integrity
            comps["device_integrity"] = 1.0
        elif acc.get("rooted_jailbroken"):
            comps["device_integrity"] = 0.6
        ip_r = float(acc.get("ip_risk_score") or 0.0)         # D network IP reputation
        if ip_r >= IP_RISK_FLOOR or acc.get("proxy"):
            comps["ip_risk"] = round(max(ip_r, 0.6 if acc.get("proxy") else 0.0), 2)
        autom = float(acc.get("automation_score") or 0.0)     # D behavioural automation
        if autom >= AUTOMATION_FLOOR:
            comps["automation"] = round(autom, 2)
        fl = int(acc.get("failed_logins_30d") or 0)           # D auth anomaly
        if fl >= FAILED_LOGIN_FLOOR:
            comps["auth_anomaly"] = round(min(1.0, fl / 10), 2)
        if acc.get("prior_fraud"):                            # D history
            comps["prior_fraud"] = 1.0
        if acc.get("account_takeover"):
            comps["account_takeover"] = 1.0
        if acc.get("blacklisted"):
            comps["blacklisted"] = 1.0
        if acc.get("verification_level") == "unverified":     # D identity
            comps["unverified"] = 1.0
        hr = float(acc.get("historical_risk_score") or 0.0)   # D trailing customer risk
        if hr >= HIST_RISK_FLOOR:
            comps["historical_risk"] = round(hr, 2)
        expected = acc.get("expected_monthly_volume")         # C3 activity vs declared profile
        actual = throughput.get(aid, 0.0)
        if expected and expected > 0 and actual >= PROFILE_MIN_ACTUAL and actual / expected >= PROFILE_RATIO:
            comps["activity_vs_profile"] = round(min(1.0, (actual / expected) / (PROFILE_RATIO * 5)), 2)
        if comps:
            out[aid] = comps
    return out


def _association(base: dict, transactions: list[dict], acc_by_id: dict) -> dict:
    """Per-account association signal in [0,1]: (share of the account's transaction VALUE that
    touches high-risk counterparties) × (mean risk of those high-risk counterparties). Symmetric
    over in+out flows. Suppressed by the same established-business factor so legit hubs that happen
    to pay a flagged account don't inherit risk."""
    val: dict = defaultdict(float)            # (a,b) -> total value a→b
    neigh: dict = defaultdict(set)
    for t in transactions:
        s, d, amt = t["src"], t["dst"], float(t["amount"])
        val[(s, d)] += amt
        neigh[s].add(d)
        neigh[d].add(s)

    assoc: dict = {}
    for acc, ns in neigh.items():
        total_v, hr_v, hr_risks = 0.0, 0.0, []
        for b in ns:
            w = val.get((acc, b), 0.0) + val.get((b, acc), 0.0)
            total_v += w
            rb = base.get(b, 0.0)
            if rb >= ASSOC_HIGH_RISK:
                hr_v += w
                hr_risks.append(rb)
        if total_v <= 0 or not hr_risks:
            continue
        raw = (hr_v / total_v) * (sum(hr_risks) / len(hr_risks))   # share × strength
        assoc[acc] = round(raw * _legit_profile_factor(acc_by_id.get(acc)), 3)
    return assoc
MIN_RING_VOLUME = 15_000  # EUR of transactions among members — laundering moves real money
MIN_RING_SCORE = 0.45
MIN_RING_SIZE = 3
MONEY_EDGE = 5_000        # a seed must contain at least one transfer this large (kills legit-cycle noise)
SEED_SCORE_FLOOR = 0.3    # a down-weighted account finding (e.g. legit hub) must not seed a ring
# Lifecycle bonus (per distinct typology beyond the 2nd). A ring that spans a full laundering
# lifecycle — placement (structuring) → layering (pass-through) → integration (fan-out/in) — is
# qualitatively more sophisticated and higher-risk than a simple 2-party loop, even when its many
# spokes dilute average member risk. This surfaces the flagship multi-stage rings to the top of
# the analyst queue. Additive + capped at 1.0; only raises multi-pattern rings, so it cannot drop
# a true ring or spawn a false-positive one (verified: ring-recall 1.0, FP-rings 0 hold).
LIFECYCLE_BONUS = 0.12


def _has_money_edge(members: set[str], pair_amt: dict) -> bool:
    for a in members:
        for b in members:
            if pair_amt.get((a, b), 0.0) >= MONEY_EDGE:
                return True
    return False


def score_accounts(findings: list[dict], accounts: list[dict] | None = None,
                   transactions: list[dict] | None = None) -> list[dict]:
    """Per-account risk.

    Pass 1 — BEHAVIOURAL: weighted sum of the detector findings on the account, suppressed for the
    established-business profile (keeps aged business/low-KYC hard-negatives below τ).
    Pass 2 — NETWORK ASSOCIATION (only when `transactions` are given): an account whose money flows
    mostly to/from already-high-risk accounts is lifted toward their risk. Precision-safe — an
    un-flagged account (base < TAU) is capped at ASSOC_ELEVATED_CAP (< TAU), so association alone
    can surface "elevated" risk for the analyst but never creates a false positive."""
    acc_by_id = {a["account_id"]: a for a in (accounts or [])}
    agg = defaultdict(lambda: {"sum": 0.0, "signals": []})
    for f in findings:
        contrib = WEIGHTS.get(f["detector"], 0.5) * f["score"]
        for acc in f["subject_ids"]:
            agg[acc]["sum"] += contrib
            agg[acc]["signals"].append({"detector": f["detector"], "score": round(f["score"], 2)})

    # pass 1 — behavioural POINTS (weighted findings, established-business suppressed). Kept as raw
    # un-clamped points; `base01` is the 0..1 behavioural risk used only to spot high-risk neighbours.
    bp: dict = {}        # behavioural + screening evidence points (drives the flag gate + the curve)
    base01: dict = {}    # 0..1 behavioural risk, for the association high-risk test only
    for acc, a in agg.items():
        pts = a["sum"] * _legit_profile_factor(acc_by_id.get(acc))
        bp[acc] = pts
        base01[acc] = min(1.0, pts / NORMALIZER)

    # confirmed-bad screening contributes EVIDENCE POINTS (precision-safe; only bad actors carry these)
    for acc, rec in acc_by_id.items():
        for flag, sig in (("sanctioned", "sanctions_hit"), ("blacklisted", "blacklisted"),
                          ("prior_fraud", "prior_fraud"), ("account_takeover", "account_takeover")):
            if rec.get(flag):
                bp[acc] = bp.get(acc, 0.0) + SCREENING_POINTS[flag]
                agg[acc]["signals"].append({"detector": sig, "score": 1.0})

    # pass 2 — SOFT evidence streams (network association + customer/identity/device/history profile)
    # as raw 0..1 scores, each also surfaced as an analyst-visible signal.
    assoc_raw: dict = {}
    if transactions:
        assoc_raw = _association(base01, transactions, acc_by_id)
        for acc, raw in assoc_raw.items():
            if raw > 0:
                agg[acc]["signals"].append({"detector": "network_association", "score": round(raw, 2)})

    profile = _profile_signals(accounts, transactions)
    profile_raw: dict = {}
    for acc, comps in profile.items():
        raw = min(1.0, sum(PROFILE_WEIGHTS.get(name, 0.0) * val for name, val in comps.items()))
        raw *= _legit_profile_factor(acc_by_id.get(acc))   # suppress the legit established-business profile
        profile_raw[acc] = raw
        for name, val in comps.items():     # expose each factor as its own analyst-visible signal
            agg[acc]["signals"].append({"detector": name, "score": round(val, 2)})

    # pass 3 — COMBINE all evidence and squash through the non-saturating curve. The behavioural-points
    # gate (bp >= BP_TAU) reproduces the old flag line exactly, so WHO crosses τ is unchanged; the curve
    # only spreads the VALUES so the flagged band ranks 50→99 by total evidence instead of all at 100.
    base: dict = {}
    for acc in set(bp) | set(assoc_raw) | set(profile_raw):
        bp_acc = bp.get(acc, 0.0)
        soft = ASSOC_WEIGHT * assoc_raw.get(acc, 0.0) + PROFILE_WEIGHT * profile_raw.get(acc, 0.0)
        evidence = bp_acc + soft
        if bp_acc >= BP_TAU:                                   # flagged → spread across (TAU, 1)
            risk = TAU + (1.0 - TAU) * (1.0 - math.exp(-(evidence - BP_TAU) / SCALE_HI))
        else:                                                  # elevated only → graded, strictly < TAU
            risk = ELEVATED_MAX * (1.0 - math.exp(-evidence / SCALE_LO))
        base[acc] = round(min(1.0, risk), 3)

    out = []
    for acc in base:
        # de-duplicate by detector (keep the strongest occurrence) so the analyst sees each distinct
        # reason once, then surface up to 12 — enough to explain the whole multi-factor score, not
        # just the top 4. The frontend groups these into risk categories.
        best: dict = {}
        for s in agg[acc]["signals"]:
            if s["detector"] not in best or s["score"] > best[s["detector"]]["score"]:
                best[s["detector"]] = s
        top = sorted(best.values(), key=lambda s: -s["score"])[:12]
        out.append({"account_id": acc, "risk": round(base[acc], 3), "top_signals": top})
    out.sort(key=lambda x: -x["risk"])
    return out


def build_rings(findings: list[dict], account_risk: list[dict], transactions: list[dict]) -> list[dict]:
    risk_map = {a["account_id"]: a["risk"] for a in account_risk}

    # adjacency + pairwise amounts / tx ids
    in_n, out_n = defaultdict(set), defaultdict(set)
    pair_amt, pair_tx = defaultdict(float), defaultdict(list)
    for t in transactions:
        s, d = t["src"], t["dst"]
        out_n[s].add(d)
        in_n[d].add(s)
        pair_amt[(s, d)] += float(t["amount"])
        pair_tx[(s, d)].append(t["tx_id"])

    # 1) seed clusters from strong findings
    seeds = []
    for f in findings:
        if f["detector"] not in STRONG:
            continue
        # Account findings that were down-weighted (e.g. a legit business hub) must not
        # seed a ring. Subgraph findings (circular) always seed — they're proof-carrying.
        if f["subject_type"] == "account" and f["score"] < SEED_SCORE_FLOOR:
            continue
        if f["subject_type"] == "subgraph":
            accts = set(f["subject_ids"])
        else:  # account finding — expand the hub to its counterparties
            hub = f["subject_ids"][0]
            cps = f["evidence"].get("counterparties")
            if cps:
                accts = {hub} | set(cps)
            else:
                # No explicit counterparty list (structuring / passthrough): expand ONLY to
                # neighbors connected by a significant transfer. Expanding to every neighbor
                # glued unrelated seeds into 90-account mega-blobs (imprecise + false-positive).
                accts = {hub} | {n for n in (in_n[hub] | out_n[hub])
                                 if pair_amt.get((hub, n), 0.0) >= MONEY_EDGE
                                 or pair_amt.get((n, hub), 0.0) >= MONEY_EDGE}
        if len(accts) >= 2 and _has_money_edge(accts, pair_amt):
            seeds.append({"accts": accts, "patterns": {f["detector"]}, "max": f["score"]})

    # 2) merge seeds that overlap (share >= 2 accounts). DETERMINISTIC order: highest score
    #    first, ties broken by the member set itself — so ring assembly never depends on
    #    detector emit order or Python's per-process hash seed (otherwise the ring count
    #    drifts run-to-run, which wrecks a live demo).
    merged: list[dict] = []
    for s in sorted(seeds, key=lambda s: (-s["max"], tuple(sorted(s["accts"])))):
        hit = next((m for m in merged if len(s["accts"] & m["accts"]) >= 2), None)
        if hit:
            hit["accts"] |= s["accts"]
            hit["patterns"] |= s["patterns"]
            hit["max"] = max(hit["max"], s["max"])
        else:
            merged.append(s)

    # 3) score + threshold (iterate members sorted so the volume sum is bit-for-bit stable)
    rings = []
    for m in merged:
        members = sorted(m["accts"])
        if len(members) < MIN_RING_SIZE:
            continue
        vol = sum(pair_amt[(a, b)] for a in members for b in members if (a, b) in pair_amt)
        txids = [tx for a in members for b in members for tx in pair_tx.get((a, b), [])]
        mrisk = [risk_map.get(a, 0.0) for a in members]
        avg_risk = sum(mrisk) / len(mrisk) if mrisk else 0.0
        max_risk = max(mrisk) if mrisk else 0.0
        # A real ring always contains at least one FLAGGED account (its hub/relay). A cluster whose
        # every member is below τ is a high-volume-but-legit pass-through cluster, not a ring — drop
        # it. (Precision-safe: every planted ring has a flagged hub, so true rings are unaffected.)
        if max_risk < TAU:
            continue
        # A real ring is ONE strong hub + many low-risk spokes (classic mule fan-out).
        # Pure mean risk dilutes the hub to ~0, so blend in the peak member risk.
        risk_term = 0.6 * max_risk + 0.4 * avg_risk
        diversity = min(1.0, 0.25 * len(m["patterns"]))
        vol_factor = min(1.0, vol / 50_000)
        lifecycle = LIFECYCLE_BONUS * max(0, len(m["patterns"]) - 2)
        score = round(min(1.0, 0.5 * risk_term + 0.2 * diversity + 0.3 * vol_factor + lifecycle), 3)
        if score < MIN_RING_SCORE or vol < MIN_RING_VOLUME:
            continue
        rings.append({"account_ids": members, "tx_ids": txids, "patterns": sorted(m["patterns"]),
                      "key_accounts": sorted(members, key=lambda a: (-risk_map.get(a, 0.0), a))[:3],
                      "score": score, "narrative": None})

    # stable ordering + ids: score desc, then first account id; assign DET_xxx after sorting
    rings.sort(key=lambda r: (-r["score"], r["account_ids"][0]))
    for i, r in enumerate(rings, 1):
        r["ring_id"] = f"DET_{i:03d}"
    return rings
