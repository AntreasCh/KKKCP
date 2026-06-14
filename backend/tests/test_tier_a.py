"""Tier A — customer-risk-profile amplifier + round-amount detector (A1–A5).

These signals were absent from detection even though the data carried the fields:
high-risk country, account age, KYC tier, channel, and round amounts were never read
by any detector/scorer. Tier A wires them in as PRECISION-SAFE amplifiers — they can
raise an already-flagged account's risk and surface "elevated" accounts to the analyst,
but a behaviourally-unflagged account can never cross τ on profile alone (capped < τ),
so the precision==1.0 guardrail provably holds. Run: `pytest backend/tests -q`.
"""
from backend.detect import scoring, structural


def _acc(aid, country="GR", kyc="low", opened="2020-01-01", atype="personal"):
    return {"account_id": aid, "owner_name": aid, "account_type": atype,
            "country": country, "opened_at": opened, "kyc_risk": kyc, "status": "active"}


def _tx(s, d, amt, ts="2026-06-10T10:00:00Z", ch="wire"):
    return {"tx_id": f"T-{s}-{d}-{int(amt)}-{ch}", "timestamp": ts, "src": s, "dst": d,
            "amount": float(amt), "currency": "EUR", "channel": ch}


def _by_id(rows):
    return {a["account_id"]: a for a in rows}


# A flagged mule: one strong finding pushes its behavioural base over τ.
def _flagged_finding(aid, detector="passthrough", score=0.9):
    return {"detector": detector, "subject_type": "account", "subject_ids": [aid],
            "score": score, "evidence": {}}


# ── A1: high-risk country ─────────────────────────────────────────────────────
def test_high_risk_country_amplifies_flagged_account():
    accounts = [_acc("M1", country="RU"), _acc("X", country="GR")]
    findings = [_flagged_finding("M1")]
    txs = [_tx("X", "M1", 20_000)]
    out = _by_id(scoring.score_accounts(findings, accounts, txs))
    sigs = {s["detector"] for s in out["M1"]["top_signals"]}
    assert "high_risk_country" in sigs, f"no high_risk_country signal: {out['M1']}"


# ── A2: fresh / newly-opened account ──────────────────────────────────────────
def test_fresh_account_amplifies_flagged_account():
    accounts = [_acc("M2", opened="2026-05-25"), _acc("M2old", opened="2019-01-01"), _acc("X")]
    findings = [_flagged_finding("M2"), _flagged_finding("M2old")]
    txs = [_tx("X", "M2", 20_000, ts="2026-06-20T10:00:00Z"),
           _tx("X", "M2old", 20_000, ts="2026-06-20T10:00:00Z")]
    out = _by_id(scoring.score_accounts(findings, accounts, txs))
    fresh_sigs = {s["detector"] for s in out["M2"]["top_signals"]}
    aged_sigs = {s["detector"] for s in out["M2old"]["top_signals"]}
    assert "fresh_account" in fresh_sigs, f"new account missing fresh signal: {out['M2']}"
    assert "fresh_account" not in aged_sigs, f"aged account wrongly flagged fresh: {out['M2old']}"


# ── A3: KYC risk as a positive amplifier ──────────────────────────────────────
def test_kyc_risk_amplifies_flagged_account():
    accounts = [_acc("M3", kyc="high"), _acc("M3low", kyc="low"), _acc("X")]
    findings = [_flagged_finding("M3"), _flagged_finding("M3low")]
    txs = [_tx("X", "M3", 20_000), _tx("X", "M3low", 20_000)]
    out = _by_id(scoring.score_accounts(findings, accounts, txs))
    assert "kyc_risk" in {s["detector"] for s in out["M3"]["top_signals"]}, out["M3"]
    assert "kyc_risk" not in {s["detector"] for s in out["M3low"]["top_signals"]}, out["M3low"]


# ── A4: high-risk channel mix (crypto / cash) ─────────────────────────────────
def test_crypto_channel_amplifies_flagged_account():
    accounts = [_acc("M4"), _acc("M4clean"), _acc("X")]
    findings = [_flagged_finding("M4"), _flagged_finding("M4clean")]
    txs = [_tx("X", "M4", 20_000, ch="crypto"), _tx("M4", "X", 9_000, ch="crypto"),
           _tx("X", "M4clean", 20_000, ch="sepa"), _tx("M4clean", "X", 9_000, ch="card")]
    out = _by_id(scoring.score_accounts(findings, accounts, txs))
    assert "crypto_channel" in {s["detector"] for s in out["M4"]["top_signals"]}, out["M4"]
    assert "crypto_channel" not in {s["detector"] for s in out["M4clean"]["top_signals"]}, out["M4clean"]


def test_crypto_channel_ignores_trivial_value_crypto():
    # Majority-crypto by share, but pocket-change amounts → not a laundering-scale crypto flow.
    # (Stops noisy small P2P crypto/card from tripping the signal.)
    accounts = [_acc("M4small"), _acc("X")]
    findings = [_flagged_finding("M4small")]
    txs = [_tx("X", "M4small", 120.0, ch="crypto"), _tx("M4small", "X", 90.0, ch="crypto")]
    out = _by_id(scoring.score_accounts(findings, accounts, txs))
    assert "crypto_channel" not in {s["detector"] for s in out["M4small"]["top_signals"]}, out["M4small"]


# ── A5: round-number / clean-amount detector ──────────────────────────────────
def test_round_amounts_flags_round_number_transfers():
    accounts = [_acc("R1"), _acc("S"), _acc("D")]
    txs = [_tx("S", "R1", 5_000.0), _tx("S", "R1", 10_000.0),
           _tx("R1", "D", 2_000.0), _tx("R1", "D", 3_000.0)]
    findings = structural.detect_round_amounts(None, accounts, txs)
    flagged = {a for f in findings for a in f["subject_ids"]}
    assert "R1" in flagged, f"round-number account not flagged: {findings}"


def test_round_amounts_ignores_messy_amounts():
    accounts = [_acc("N1"), _acc("S"), _acc("D")]
    txs = [_tx("S", "N1", 4_137.22), _tx("S", "N1", 9_981.50),
           _tx("N1", "D", 2_073.11), _tx("N1", "D", 3_399.99)]
    findings = structural.detect_round_amounts(None, accounts, txs)
    flagged = {a for f in findings for a in f["subject_ids"]}
    assert "N1" not in flagged, f"messy-amount account wrongly flagged: {findings}"


# ── precision-safety invariant (must hold after every Tier A step) ────────────
def test_profile_alone_never_flags_unflagged_account():
    # Worst-case profile (high-risk country + brand new + high KYC + all-crypto flow) but
    # NO behavioural detector hit → must stay strictly below τ.
    accounts = [_acc("P", country="RU", kyc="high", opened="2026-05-20", atype="personal"),
                _acc("Q", country="GR")]
    txs = [_tx("Q", "P", 50_000, ch="crypto"), _tx("P", "Q", 9_000, ch="crypto")]
    res = scoring.score_accounts([], accounts, txs)
    p = next((a for a in res if a["account_id"] == "P"), None)
    if p is not None:
        assert p["risk"] < 0.5, f"profile alone flagged an account: {p}"
