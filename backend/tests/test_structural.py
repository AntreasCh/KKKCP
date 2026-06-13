"""P2 detector tests — prove each structural detector finds its planted pattern in the
sample fixture without drowning in false positives. Run: `pytest backend/tests -q`.

These are the DoD checks for P2 (REQUIREMENTS.md §13): each detector flags the planted
ring it's responsible for, and `detect_circular` no longer over-fires on random cycles.
"""
import json
import pathlib

from backend.detect import structural

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = json.loads((ROOT / "sample_data" / "dataset.json").read_text())
LABELS = json.loads((ROOT / "sample_data" / "labels.json").read_text())
ACCOUNTS, TXS = DATASET["accounts"], DATASET["transactions"]

# the one planted circular ring (labels.json TRUE_002)
TRUE_CIRCULAR = {"ACC00164", "ACC00325", "ACC00425"}


def _accounts_in(findings):
    out = set()
    for f in findings:
        out.update(f["subject_ids"])
    return out


def test_circular_finds_planted_ring():
    findings = structural.detect_circular(None, ACCOUNTS, TXS)
    # the planted loop must be one of the flagged cycles
    assert any(set(f["subject_ids"]) == TRUE_CIRCULAR for f in findings), \
        "lost the real circular ring — ring_recall would drop"


def test_circular_does_not_overfire():
    # before the time+retention filter this returned ~117; correct behaviour is a handful
    findings = structural.detect_circular(None, ACCOUNTS, TXS)
    assert len(findings) <= 8, f"circular over-firing again: {len(findings)} findings"


def test_circular_evidence_is_traceable():
    findings = structural.detect_circular(None, ACCOUNTS, TXS)
    ring = next(f for f in findings if set(f["subject_ids"]) == TRUE_CIRCULAR)
    ev = ring["evidence"]
    assert ev["retention"] >= structural.CIRC_MIN_RETENTION
    assert ev["hours"] <= structural.CIRC_WINDOW_H
    assert len(ev["tx_ids"]) == ev["length"]  # one real tx proving each hop


def test_structuring_finds_a_planted_ring():
    findings = structural.detect_structuring(None, ACCOUNTS, TXS)
    structuring_true = {a for r in LABELS["rings"] if "structuring" in r["patterns"]
                        for a in r["account_ids"]}
    assert _accounts_in(findings) & structuring_true, "missed every structuring ring"


def test_passthrough_is_bounded():
    # passthrough feeds account risk, not rings; just guard it stays specific, not spammy
    findings = structural.detect_passthrough(None, ACCOUNTS, TXS)
    assert len(findings) <= 30, f"passthrough over-firing: {len(findings)}"
