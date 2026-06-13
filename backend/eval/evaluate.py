"""Evaluation harness — REQUIREMENTS.md §12 (Owner: P5). Our headline metric.

evaluate(result, labels) -> {account precision/recall/f1, ring_recall, false_positive_rings}
"""
from __future__ import annotations


def evaluate(result: dict, labels: dict, tau: float = 0.5, ring_overlap: float = 0.6) -> dict:
    # ── account level ──
    true_mules = set(labels.get("mule_accounts", []))
    pred_mules = {a["account_id"] for a in result["account_risk"] if a["risk"] >= tau}
    tp = len(pred_mules & true_mules)
    fp = len(pred_mules - true_mules)
    fn = len(true_mules - pred_mules)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    # ── ring level ──
    detected = [set(r["account_ids"]) for r in result["rings"]]
    true_rings = [set(tr["account_ids"]) for tr in labels.get("rings", [])]
    matched = sum(1 for ta in true_rings
                  if ta and any(len(ta & d) / len(ta) >= ring_overlap for d in detected))
    ring_recall = matched / len(true_rings) if true_rings else 0.0
    fp_rings = sum(1 for d in detected if d and not any(len(d & t) / len(d) >= 0.3 for t in true_rings))

    n_det = len(detected)
    return {
        "account": {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
                    "tp": tp, "fp": fp, "fn": fn, "tau": tau},
        "ring_recall": round(ring_recall, 3),
        "rings_matched": matched, "rings_true": len(true_rings),
        "false_positive_rings": fp_rings, "rings_detected": n_det,
        # additive: fraction of detected rings that match nothing true (0..1)
        "false_positive_rate": round(fp_rings / n_det, 3) if n_det else 0.0,
    }


def format_report(m: dict) -> str:
    """Human-readable scoreboard for the terminal / demo."""
    a = m["account"]
    return (
        "┌─ MuleNet eval ─────────────────────────────────────────────┐\n"
        f"│ Accounts   precision {a['precision']:.3f}  recall {a['recall']:.3f}  f1 {a['f1']:.3f}"
        f"   (tp {a['tp']}, fp {a['fp']}, fn {a['fn']}, τ={a['tau']})\n"
        f"│ Rings      recall {m['ring_recall']:.3f}  "
        f"({m['rings_matched']}/{m['rings_true']} true rings found)\n"
        f"│ Detected   {m['rings_detected']} rings, {m['false_positive_rings']} false positive "
        f"(fp-rate {m['false_positive_rate']:.3f})\n"
        "└────────────────────────────────────────────────────────────┘"
    )


def _cli() -> None:
    """`python -m backend.eval.evaluate` — run the pipeline on sample_data and print the scoreboard."""
    import json
    from pathlib import Path

    from backend.detect import pipeline

    root = Path(__file__).resolve().parents[2]
    ds = json.loads((root / "sample_data" / "dataset.json").read_text(encoding="utf-8"))
    lb = json.loads((root / "sample_data" / "labels.json").read_text(encoding="utf-8"))
    metrics = evaluate(pipeline.run(ds), lb)
    print(format_report(metrics))


if __name__ == "__main__":
    _cli()
