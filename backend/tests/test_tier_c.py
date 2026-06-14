"""Tier C — KYC / screening / identity signals (C1, C2, C3, C4, C5, C7).

These read the Tier-C account/transaction fields added to schemas.py. Attribute signals are
PRECISION-SAFE amplifiers (capped < τ for behaviourally-unflagged accounts, like the Tier-A
profile pass); `sanctioned` is the one screening escalation that flags on its own (a confirmed
sanctions hit), which is safe because only confirmed-bad accounts carry it. Run: `pytest backend/tests -q`.
"""
from backend.detect import kyc, scoring


def _acc(aid, **kw):
    base = dict(account_id=aid, owner_name=aid, account_type="personal", country="GR",
                opened_at="2020-01-01", kyc_risk="low", status="active",
                pep=False, sanctioned=False, watchlist=False, prior_sars=0,
                occupation=None, business_category=None, expected_monthly_volume=None,
                account_purpose=None, device_id=f"dev-{aid}", signup_ip=f"ip-{aid}",
                vpn_tor=False, failed_verifications=0, adverse_media=False, nominee_owner=False)
    base.update(kw)
    return base


def _tx(s, d, amt, ch="wire", ts="2026-06-10T10:00:00Z", **kw):
    base = dict(tx_id=f"T-{s}-{d}-{int(amt)}-{ch}-{ts[-9:-1]}", timestamp=ts, src=s, dst=d,
                amount=float(amt), currency="EUR", channel=ch, tx_type="transfer",
                merchant_category=None, tx_country=None)
    base.update(kw)
    return base


def _flag(aid, score=0.9):
    return {"detector": "passthrough", "subject_type": "account", "subject_ids": [aid],
            "score": score, "evidence": {}}


def _out(findings, accounts, txs):
    return {a["account_id"]: a for a in scoring.score_accounts(findings, accounts, txs)}


def _sigs(rec):
    return {s["detector"] for s in rec["top_signals"]}


# ── C1: sanctions / PEP / watchlist ───────────────────────────────────────────
def test_sanctioned_account_is_auto_flagged():
    # a confirmed sanctions hit crosses τ even with no behavioural finding (screening escalation)
    accounts = [_acc("S1", sanctioned=True), _acc("X")]
    out = _out([], accounts, [_tx("X", "S1", 9_000)])
    assert "S1" in out and out["S1"]["risk"] >= 0.9, f"sanctioned account not auto-flagged: {out.get('S1')}"
    assert "sanctions_hit" in _sigs(out["S1"])


def test_pep_amplifies_flagged_account():
    accounts = [_acc("M", pep=True), _acc("X")]
    out = _out([_flag("M")], accounts, [_tx("X", "M", 20_000)])
    assert "pep" in _sigs(out["M"]), out["M"]


def test_pep_alone_does_not_flag():
    # PEP is not proof of crime — alone it must stay below τ
    accounts = [_acc("P", pep=True), _acc("X")]
    out = _out([], accounts, [_tx("X", "P", 9_000), _tx("P", "X", 5_000)])
    p = out.get("P")
    if p is not None:
        assert p["risk"] < 0.5, f"PEP alone flagged an account: {p}"


def test_watchlist_amplifies_flagged_account():
    accounts = [_acc("M", watchlist=True), _acc("X")]
    out = _out([_flag("M")], accounts, [_tx("X", "M", 20_000)])
    assert "watchlist" in _sigs(out["M"]), out["M"]


# ── C2: prior SARs ────────────────────────────────────────────────────────────
def test_prior_sars_amplifies_flagged_account():
    accounts = [_acc("M", prior_sars=3), _acc("Mclean", prior_sars=0), _acc("X")]
    out = _out([_flag("M"), _flag("Mclean")], accounts, [_tx("X", "M", 20_000), _tx("X", "Mclean", 20_000)])
    assert "prior_sars" in _sigs(out["M"]), out["M"]
    assert "prior_sars" not in _sigs(out["Mclean"]), out["Mclean"]


# ── C5: adverse media / shell company ─────────────────────────────────────────
def test_adverse_media_amplifies_flagged_account():
    accounts = [_acc("M", adverse_media=True), _acc("X")]
    out = _out([_flag("M")], accounts, [_tx("X", "M", 20_000)])
    assert "adverse_media" in _sigs(out["M"]), out["M"]


def test_shell_company_signal():
    # business + nominee owner + freshly incorporated + high-risk jurisdiction = shell-company shape
    accounts = [_acc("SC", account_type="business", nominee_owner=True,
                      opened_at="2026-05-20", country="AE"), _acc("X")]
    out = _out([_flag("SC")], accounts, [_tx("X", "SC", 20_000)])
    assert "shell_company" in _sigs(out["SC"]), out["SC"]


# ── C7: geo mismatch / high-risk MCC ──────────────────────────────────────────
def test_geo_mismatch_amplifies_flagged_account():
    # account resident in GR but its outbound transactions originate in RU
    accounts = [_acc("M", country="GR"), _acc("D")]
    txs = [_tx("M", "D", 20_000, tx_country="RU"), _tx("M", "D", 15_000, tx_country="RU")]
    out = _out([_flag("M")], accounts, txs)
    assert "geo_mismatch" in _sigs(out["M"]), out["M"]


def test_high_risk_mcc_amplifies_flagged_account():
    accounts = [_acc("M", account_type="business", business_category="crypto_exchange"), _acc("X")]
    out = _out([_flag("M")], accounts, [_tx("X", "M", 20_000)])
    assert "high_risk_mcc" in _sigs(out["M"]), out["M"]


# ── C3: activity vs declared expected profile (capped amplifier) ──────────────
def test_activity_vs_profile_amplifies_flagged_account():
    accounts = [_acc("M", expected_monthly_volume=2_000.0), _acc("X")]
    txs = [_tx("X", "M", 50_000), _tx("M", "X", 45_000)]   # ~95k actual vs 2k declared
    out = _out([_flag("M")], accounts, txs)
    assert "activity_vs_profile" in _sigs(out["M"]), out["M"]


def test_activity_vs_profile_ignores_consistent_account():
    accounts = [_acc("L", expected_monthly_volume=90_000.0), _acc("X")]
    txs = [_tx("X", "L", 50_000), _tx("L", "X", 45_000)]   # ~95k actual vs 90k declared → consistent
    out = _out([_flag("L")], accounts, txs)
    assert "activity_vs_profile" not in _sigs(out["L"]), out["L"]


def test_activity_vs_profile_does_not_flag_legit_overrun():
    # a LEGIT account that exceeds its declared estimate (no behavioural finding) must stay below τ —
    # a declared/actual gap is an indicator, not proof.
    accounts = [_acc("Over", expected_monthly_volume=2_000.0), _acc("X")]
    txs = [_tx("X", "Over", 50_000), _tx("Over", "X", 45_000)]
    out = _out([], accounts, txs)
    o = out.get("Over")
    if o is not None:
        assert o["risk"] < 0.5, f"legit profile over-run was flagged: {o}"


# ── C4: device / IP linkage ───────────────────────────────────────────────────
def test_device_linkage_flags_shared_device_cluster():
    accounts = [_acc(f"m{i}", device_id="dev-shared", signup_ip="1.2.3.4") for i in range(4)]
    accounts.append(_acc("u", device_id="dev-unique", signup_ip="9.9.9.9"))
    f = kyc.detect_device_linkage(None, accounts, [])
    flagged = {a for x in f for a in x["subject_ids"]}
    assert {"m0", "m1", "m2", "m3"} <= flagged, f"shared-device cluster not flagged: {flagged}"
    assert "u" not in flagged, "unique-device account wrongly linked"


def test_device_linkage_ignores_unique_devices():
    accounts = [_acc(f"u{i}", device_id=f"dev-{i}", signup_ip=f"10.0.0.{i}") for i in range(5)]
    f = kyc.detect_device_linkage(None, accounts, [])
    assert not f, f"unique devices wrongly produced linkage findings: {f}"


# ── precision-safety: all bad attributes EXCEPT sanctions, no finding → below τ ──
def test_kyc_attributes_alone_never_flag():
    accounts = [_acc("Z", pep=True, watchlist=True, prior_sars=3, adverse_media=True,
                     vpn_tor=True, failed_verifications=5, country="RU",
                     business_category="gambling", account_type="business", nominee_owner=True,
                     opened_at="2026-05-20"),
                _acc("X")]
    txs = [_tx("X", "Z", 30_000, tx_country="RU"), _tx("Z", "X", 9_000, tx_country="RU")]
    out = _out([], accounts, txs)
    z = out.get("Z")
    if z is not None:
        assert z["risk"] < 0.5, f"KYC attributes alone flagged an account: {z}"
