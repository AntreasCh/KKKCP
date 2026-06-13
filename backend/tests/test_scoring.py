"""P3 scoring/pipeline tests — lock in the calibration on the sample fixture.

These are the integrated-metric guardrails for P3 (REQUIREMENTS.md §10/§12): account
scoring must stay PRECISE (no legit account flagged) while recovering the single-strong-signal
mules, and the ring metrics must not regress. Read thresholds from labels so the tests survive
data regeneration. Run: `pytest backend/tests -q`.
"""
import json
import pathlib

from backend.detect import pipeline
from backend.eval.evaluate import evaluate

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = json.loads((ROOT / "sample_data" / "dataset.json").read_text())
LABELS = json.loads((ROOT / "sample_data" / "labels.json").read_text())

RESULT = pipeline.run(DATASET)
METRICS = evaluate(RESULT, LABELS)


def test_account_precision_is_perfect():
    # The fixture plants unlabelled hard-negatives (aged business+low-KYC: payroll, merchants,
    # B2B invoices, settlement loops) that DO trip the strong detectors. The established-business
    # profile down-weight in scoring.py must keep all of them below τ → zero flagged legit accounts.
    assert METRICS["account"]["fp"] == 0, f"flagged a legit account: {METRICS['account']}"
    assert METRICS["account"]["precision"] == 1.0


def test_account_recall_recovers_single_signal_mules():
    # NORMALIZER was recalibrated so a single proven typology hit crosses τ. That recovers the
    # passthrough/circular/fan-only mules; recall jumps from 0.359 to ~0.77 (the remaining
    # misses are no-detector-fires collectors, tracked separately).
    assert METRICS["account"]["recall"] >= 0.74, f"recall regressed: {METRICS['account']}"


def test_ring_metrics_hold():
    # Ring recall is the headline — it must stay perfect.
    assert METRICS["ring_recall"] == 1.0, f"ring recall regressed: {METRICS}"
    # With P3's profile down-weight (structuring FP ring) + P2's settlement-loop skip (the 2
    # circular FP rings), the decoy fixture now yields ZERO false-positive rings — earned against
    # planted hard-negatives. Lock it in.
    assert METRICS["false_positive_rings"] == 0, f"false-positive rings appeared: {METRICS}"


def test_top_ranked_ring_is_a_full_lifecycle_ring():
    # The lifecycle bonus must surface a multi-typology ring (full placement→layering→integration)
    # to #1 of the analyst queue — a sophisticated ring should outrank a simple 2-party loop.
    rings = RESULT["rings"]
    assert rings, "no rings detected"
    max_patterns = max(len(r["patterns"]) for r in rings)
    assert max_patterns >= 3, "expected at least one full-lifecycle (3+ typology) ring in the fixture"
    assert len(rings[0]["patterns"]) == max_patterns, \
        f"top ring has {len(rings[0]['patterns'])} patterns; a full-lifecycle ring should rank #1"


def test_no_legit_account_outscores_a_true_mule_floor():
    # Behind the precision: even the worst hard-negative (the mega-merchant that trips
    # passthrough+circular and hit risk 1.0 before the fix) must be pulled well below τ=0.5 by the
    # established-business down-weight, leaving margin so data jitter can't flip it to a false flag.
    mules = set(LABELS["mule_accounts"])
    legit_max = max((a["risk"] for a in RESULT["account_risk"]
                     if a["account_id"] not in mules), default=0.0)
    assert legit_max < 0.45, f"a legit account scored {legit_max}, dangerously near τ"
