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

# planted circular rings, read from the labels so the test survives data regeneration
TRUE_CIRCULAR = [set(r["account_ids"]) for r in LABELS["rings"]
                 if "circular" in r["patterns"]]


def _accounts_in(findings):
    out = set()
    for f in findings:
        out.update(f["subject_ids"])
    return out


def _overlaps(found_sets, true_set, frac=0.6):
    return any(len(true_set & fs) / len(true_set) >= frac for fs in found_sets)


def test_circular_finds_every_planted_ring():
    findings = structural.detect_circular(None, ACCOUNTS, TXS)
    found = [set(f["subject_ids"]) for f in findings]
    missed = [t for t in TRUE_CIRCULAR if not _overlaps(found, t)]
    assert not missed, f"circular detector missed planted loops: {missed}"


def test_circular_does_not_overfire():
    # before the time+retention filter this returned ~117 on the Phase-0 fixture;
    # correct behaviour is roughly one finding per planted loop, plus a little slack
    findings = structural.detect_circular(None, ACCOUNTS, TXS)
    assert len(findings) <= len(TRUE_CIRCULAR) + 3, \
        f"circular over-firing: {len(findings)} findings for {len(TRUE_CIRCULAR)} true rings"


def test_circular_evidence_is_traceable():
    findings = structural.detect_circular(None, ACCOUNTS, TXS)
    assert findings, "expected at least one circular finding"
    for f in findings:
        ev = f["evidence"]
        assert structural.CIRC_MIN_RETENTION <= ev["retention"] <= structural.CIRC_MAX_RETENTION
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


def test_passthrough_score_scales_with_ratio_and_speed():
    # REQUIREMENTS §9 #3: score by ratio and speed, not a flat constant. A flat score
    # pinned every relay mule at the same sub-threshold risk; scores must now vary.
    findings = structural.detect_passthrough(None, ACCOUNTS, TXS)
    scores = {f["score"] for f in findings}
    assert len(scores) > 1, f"passthrough score is still flat: {scores}"
    for f in findings:
        assert 0.0 <= f["score"] <= 1.0
        assert "completeness" in f["evidence"] and "speed" in f["evidence"]
