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
    # The strong detectors (structuring/circular/passthrough) never fire on a legit account
    # in this fixture, so a flagged account should always be a true mule. Calibration must not
    # trade this away for recall.
    assert METRICS["account"]["fp"] == 0, f"flagged a legit account: {METRICS['account']}"
    assert METRICS["account"]["precision"] == 1.0


def test_account_recall_recovers_single_signal_mules():
    # NORMALIZER was recalibrated so a single proven typology hit crosses τ. That recovers the
    # passthrough/circular/fan-only mules; recall jumps from 0.359 to ~0.77 (the remaining
    # misses are no-detector-fires collectors, tracked separately).
    assert METRICS["account"]["recall"] >= 0.74, f"recall regressed: {METRICS['account']}"


def test_ring_metrics_hold():
    # Lowering the account normalizer feeds ring scores; verify it did NOT spawn false-positive
    # rings or drop ring recall.
    assert METRICS["ring_recall"] == 1.0, f"ring recall regressed: {METRICS}"
    assert METRICS["false_positive_rings"] == 0, f"false-positive rings appeared: {METRICS}"


def test_no_legit_account_outscores_a_true_mule_floor():
    # Structural guarantee behind the precision: the highest-scoring legit account must stay
    # well below τ=0.5 (it only carries factor-suppressed fan/community signals).
    mules = set(LABELS["mule_accounts"])
    legit_max = max((a["risk"] for a in RESULT["account_risk"]
                     if a["account_id"] not in mules), default=0.0)
    assert legit_max < 0.45, f"a legit account scored {legit_max}, dangerously near τ"
