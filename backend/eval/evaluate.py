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

    return {
        "account": {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
                    "tp": tp, "fp": fp, "fn": fn, "tau": tau},
        "ring_recall": round(ring_recall, 3),
        "rings_matched": matched, "rings_true": len(true_rings),
        "false_positive_rings": fp_rings, "rings_detected": len(detected),
    }
