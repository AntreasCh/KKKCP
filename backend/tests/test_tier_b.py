"""Tier B — B3: rapid fiat→crypto conversion detector.

The placement→layering hop launderers reach for: receive fiat (sepa/wire/card/cash),
then push it straight into crypto within hours. Channel + timestamp are already on every
transaction; this typology was never detected. Specialises pass-through with channel typing.
Run: `pytest backend/tests -q`.
"""
import json
import pathlib

from backend.detect import pipeline, structural, temporal

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = json.loads((ROOT / "sample_data" / "dataset.json").read_text())
LABELS = json.loads((ROOT / "sample_data" / "labels.json").read_text())
RESULT = pipeline.run(DATASET)
_MULES = set(LABELS["mule_accounts"])
_RISK = {a["account_id"]: a["risk"] for a in RESULT["account_risk"]}


def _subjects(detector):
    return [f["subject_ids"][0] for f in RESULT["findings"] if f["detector"] == detector]


# ── fixture guardrails: the planted Tier-B typologies are caught on a true mule ──
def test_fixture_flags_dormant_reactivation_mule():
    hits = [a for a in _subjects("dormant_reactivation") if _RISK.get(a, 0) >= 0.5 and a in _MULES]
    assert hits, f"dormant_reactivation not on any flagged mule: {_subjects('dormant_reactivation')}"


def test_fixture_flags_activity_spike_mule():
    hits = [a for a in _subjects("activity_spike") if _RISK.get(a, 0) >= 0.5 and a in _MULES]
    assert hits, f"activity_spike not on any flagged mule: {_subjects('activity_spike')}"


def test_fixture_fiat_to_crypto_is_precise():
    subs = _subjects("fiat_to_crypto")
    assert subs, "no fiat_to_crypto findings on fixture"
    assert all(a in _MULES for a in subs), f"fiat_to_crypto fired on a legit account: {subs}"


def _acc(aid, country="GR", kyc="low", opened="2020-01-01", atype="personal"):
    return {"account_id": aid, "owner_name": aid, "account_type": atype,
            "country": country, "opened_at": opened, "kyc_risk": kyc, "status": "active"}


def _tx(s, d, amt, ts="2026-06-10T10:00:00Z", ch="wire"):
    return {"tx_id": f"T-{s}-{d}-{int(amt)}-{ch}-{ts[-9:-1]}", "timestamp": ts, "src": s, "dst": d,
            "amount": float(amt), "currency": "EUR", "channel": ch}


def _flagged(findings, aid):
    return any(aid in f["subject_ids"] for f in findings)


def test_fiat_to_crypto_flags_conversion():
    accounts = [_acc("C"), _acc("S"), _acc("D")]
    txs = [_tx("S", "C", 20_000, ts="2026-06-10T08:00:00Z", ch="wire"),
           _tx("C", "D", 18_000, ts="2026-06-10T14:00:00Z", ch="crypto")]
    findings = structural.detect_fiat_to_crypto(None, accounts, txs)
    assert _flagged(findings, "C"), f"fiat→crypto relay not flagged: {findings}"


def test_fiat_to_crypto_ignores_fiat_to_fiat():
    accounts = [_acc("C2"), _acc("S"), _acc("D")]
    txs = [_tx("S", "C2", 20_000, ts="2026-06-10T08:00:00Z", ch="wire"),
           _tx("C2", "D", 18_000, ts="2026-06-10T14:00:00Z", ch="sepa")]  # out is fiat, not crypto
    findings = structural.detect_fiat_to_crypto(None, accounts, txs)
    assert not _flagged(findings, "C2"), f"fiat→fiat wrongly flagged: {findings}"


def test_fiat_to_crypto_ignores_crypto_to_fiat_direction():
    # B3 is specifically conversion INTO crypto; crypto-in → fiat-out is the opposite (cash-out).
    accounts = [_acc("C3"), _acc("S"), _acc("D")]
    txs = [_tx("S", "C3", 20_000, ts="2026-06-10T08:00:00Z", ch="crypto"),
           _tx("C3", "D", 18_000, ts="2026-06-10T14:00:00Z", ch="wire")]
    findings = structural.detect_fiat_to_crypto(None, accounts, txs)
    assert not _flagged(findings, "C3"), f"crypto→fiat wrongly flagged as fiat→crypto: {findings}"


def test_fiat_to_crypto_ignores_trivial_value():
    accounts = [_acc("C4"), _acc("S"), _acc("D")]
    txs = [_tx("S", "C4", 200, ts="2026-06-10T08:00:00Z", ch="wire"),
           _tx("C4", "D", 180, ts="2026-06-10T14:00:00Z", ch="crypto")]
    findings = structural.detect_fiat_to_crypto(None, accounts, txs)
    assert not _flagged(findings, "C4"), f"pocket-change conversion wrongly flagged: {findings}"


def test_fiat_to_crypto_ignores_slow_conversion():
    # fiat in, crypto out 5 days later → not a rapid conversion
    accounts = [_acc("C5"), _acc("S"), _acc("D")]
    txs = [_tx("S", "C5", 20_000, ts="2026-06-10T08:00:00Z", ch="wire"),
           _tx("C5", "D", 18_000, ts="2026-06-15T08:00:00Z", ch="crypto")]
    findings = structural.detect_fiat_to_crypto(None, accounts, txs)
    assert not _flagged(findings, "C5"), f"slow conversion wrongly flagged: {findings}"


# ── B2: dormant → active reactivation ─────────────────────────────────────────
def test_dormant_reactivation_flags_aged_conduit():
    # an account opened years ago suddenly relays a material sum (receive → forward)
    accounts = [_acc("R", opened="2019-01-01"), _acc("S"), _acc("D")]
    txs = [_tx("S", "R", 40_000, ts="2026-06-25T08:00:00Z", ch="wire"),
           _tx("R", "D", 36_000, ts="2026-06-25T14:00:00Z", ch="wire")]
    findings = temporal.detect_dormant_reactivation(None, accounts, txs)
    assert _flagged(findings, "R"), f"aged conduit not flagged: {findings}"


def test_dormant_reactivation_ignores_young_account():
    # same relay shape but a fresh account → it's a normal fresh mule, not a *reactivation*
    accounts = [_acc("Y", opened="2026-05-01"), _acc("S"), _acc("D")]
    txs = [_tx("S", "Y", 40_000, ts="2026-06-25T08:00:00Z", ch="wire"),
           _tx("Y", "D", 36_000, ts="2026-06-25T14:00:00Z", ch="wire")]
    findings = temporal.detect_dormant_reactivation(None, accounts, txs)
    assert not _flagged(findings, "Y"), f"young account wrongly flagged as reactivation: {findings}"


# ── B1: activity velocity / spike vs baseline ─────────────────────────────────
def test_activity_spike_flags_burst_against_quiet_baseline():
    accounts = [_acc("H"), _acc("D")] + [_acc(f"s{i}") for i in range(8)]
    txs = [_tx("H", "D", 200, ts="2026-06-02T10:00:00Z"),    # quiet baseline
           _tx("H", "D", 150, ts="2026-06-08T10:00:00Z"),
           _tx("D", "H", 300, ts="2026-06-14T10:00:00Z")]
    for i in range(8):                                        # sudden burst in <8h
        txs.append(_tx(f"s{i}", "H", 6_000, ts=f"2026-06-25T0{i}:00:00Z"))
    findings = temporal.detect_activity_spike(None, accounts, txs)
    assert _flagged(findings, "H"), f"burst-against-quiet-baseline not flagged: {findings}"


def test_activity_spike_ignores_steady_activity():
    # an account active at a steady rate all month → no single-window spike (legit hub)
    accounts = [_acc("HUB")] + [_acc(f"c{i}") for i in range(28)]
    txs = [_tx(f"c{i}", "HUB", 500, ts=f"2026-06-{i+1:02d}T10:00:00Z") for i in range(28)]
    findings = temporal.detect_activity_spike(None, accounts, txs)
    assert not _flagged(findings, "HUB"), f"steady activity wrongly flagged as spike: {findings}"
