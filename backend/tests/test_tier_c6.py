"""C6 — crypto chain-analysis (Option A: wallet tagging). Unit + fixture guardrails.

Mixer/darknet exposure is conclusive (auto-flag, high weight); high-risk wallet, consolidation
and chain-hopping are contributors/amplifiers. Suspicious wallet labels are planted only on
all-mule crypto legs, so exposure (attributed to both endpoints) never implicates a legit account.
Run: `pytest backend/tests -q`.
"""
import json
import pathlib

from backend.detect import crypto, pipeline, scoring


def _acc(aid, **kw):
    base = dict(account_id=aid, owner_name=aid, account_type="personal", country="GR",
                opened_at="2020-01-01", kyc_risk="low", status="active")
    base.update(kw)
    return base


def _ctx(s, d, amt=8_000, ts="2026-06-10T10:00:00Z", asset="BTC", wallet="0xw", label=None):
    return dict(tx_id=f"T-{s}-{d}-{ts[-9:-1]}-{asset}", timestamp=ts, src=s, dst=d, amount=float(amt),
                currency="EUR", channel="crypto", crypto_asset=asset,
                counterparty_wallet=wallet, wallet_label=label)


def _subjects(findings):
    return {a for x in findings for a in x["subject_ids"]}


# ── mixer / darknet exposure ──────────────────────────────────────────────────
def test_mixer_exposure_flags_both_endpoints():
    accounts = [_acc("A"), _acc("B")]
    f = crypto.detect_mixer_exposure(None, accounts, [_ctx("A", "B", label="mixer", wallet="0xmix")])
    assert {"A", "B"} <= _subjects(f), f"mixer exposure not flagged: {f}"


def test_mixer_exposure_ignores_clean_and_exchange():
    accounts = [_acc("A"), _acc("B")]
    f = crypto.detect_mixer_exposure(None, accounts, [_ctx("A", "B", label="exchange")])
    assert not f, f"clean/exchange wrongly flagged as mixer exposure: {f}"


# ── high-risk wallet exposure ─────────────────────────────────────────────────
def test_high_risk_wallet_exposure():
    accounts = [_acc("A"), _acc("B")]
    f = crypto.detect_high_risk_wallet(None, accounts, [_ctx("A", "B", label="high_risk")])
    assert {"A", "B"} <= _subjects(f), f"high-risk wallet not flagged: {f}"


# ── wallet consolidation (crypto fan-in over distinct suspicious wallets) ──────
def test_wallet_consolidation_flags_collector():
    accounts = [_acc("C")] + [_acc(f"s{i}") for i in range(4)]
    txs = [_ctx(f"s{i}", "C", ts=f"2026-06-10T0{i}:00:00Z", wallet=f"0xw{i}", label="high_risk")
           for i in range(4)]
    f = crypto.detect_wallet_consolidation(None, accounts, txs)
    assert "C" in _subjects(f), f"consolidation collector not flagged: {f}"


def test_wallet_consolidation_ignores_clean_wallets():
    accounts = [_acc("C")] + [_acc(f"s{i}") for i in range(4)]
    txs = [_ctx(f"s{i}", "C", ts=f"2026-06-10T0{i}:00:00Z", wallet=f"0xw{i}", label="exchange")
           for i in range(4)]
    f = crypto.detect_wallet_consolidation(None, accounts, txs)
    assert "C" not in _subjects(f), f"clean-wallet inflows wrongly flagged as consolidation: {f}"


# ── chain-hopping (rapid asset switches) ──────────────────────────────────────
def test_chain_hopping_flags_asset_switches():
    accounts = [_acc("H"), _acc("D")]
    txs = [_ctx("H", "D", ts="2026-06-10T00:00:00Z", asset="BTC", label="high_risk"),
           _ctx("H", "D", ts="2026-06-10T02:00:00Z", asset="ETH", label="high_risk"),
           _ctx("H", "D", ts="2026-06-10T04:00:00Z", asset="USDT", label="high_risk")]
    f = crypto.detect_chain_hopping(None, accounts, txs)
    assert "H" in _subjects(f), f"chain-hopping not flagged: {f}"


def test_chain_hopping_ignores_single_asset():
    accounts = [_acc("H"), _acc("D")]
    txs = [_ctx("H", "D", ts=f"2026-06-10T0{i}:00:00Z", asset="BTC", label="high_risk") for i in range(3)]
    f = crypto.detect_chain_hopping(None, accounts, txs)
    assert "H" not in _subjects(f), f"single-asset crypto wrongly flagged as chain-hop: {f}"


# ── precision-safety: clean/exchange crypto never flags a legit account ───────
def test_clean_crypto_does_not_flag_legit_account():
    accounts = [_acc("L"), _acc("X")]
    txs = [_ctx("X", "L", label="exchange"), _ctx("L", "X", label="clean")]
    res = scoring.score_accounts([], accounts, txs)
    l = next((a for a in res if a["account_id"] == "L"), None)
    if l is not None:
        assert l["risk"] < 0.5, f"clean crypto flagged a legit account: {l}"


# ── fixture guardrails: the planted crypto cell is caught on true mules ────────
ROOT = pathlib.Path(__file__).resolve().parents[2]
_DS = json.loads((ROOT / "sample_data" / "dataset.json").read_text())
_LB = json.loads((ROOT / "sample_data" / "labels.json").read_text())
_RES = pipeline.run(_DS)
_MULES = set(_LB["mule_accounts"])
_RISK = {a["account_id"]: a["risk"] for a in _RES["account_risk"]}


def _fix_subjects(detector):
    return [f["subject_ids"][0] for f in _RES["findings"] if f["detector"] == detector]


def test_fixture_mixer_exposure_is_precise_and_present():
    subs = _fix_subjects("mixer_exposure")
    assert subs, "no mixer_exposure findings on fixture"
    assert all(a in _MULES for a in subs), f"mixer_exposure fired on a legit account: {[a for a in subs if a not in _MULES]}"


def test_fixture_has_wallet_consolidation_and_chain_hopping():
    assert any(a in _MULES and _RISK.get(a, 0) >= 0.5 for a in _fix_subjects("wallet_consolidation")), \
        "wallet_consolidation not on a flagged mule"
    assert any(a in _MULES and _RISK.get(a, 0) >= 0.5 for a in _fix_subjects("chain_hopping")), \
        "chain_hopping not on a flagged mule"
