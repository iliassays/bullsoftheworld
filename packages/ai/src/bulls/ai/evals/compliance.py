"""Compliance-gate eval: how well does the no-advice detector separate advice from description?

The detector is deterministic, so this eval is PURE (no network) and always runs in CI. We track
recall on advice (must be ~1.0 — never miss a real recommendation) and precision (false positives
just trigger a safe fallback, so some are tolerable).
"""

from __future__ import annotations

from pydantic import BaseModel

from bulls.ai.compliance import contains_advice
from bulls.ai.evals.dataset import ADVICE_EVAL_SET, AdviceExample


class ComplianceReport(BaseModel):
    total: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    missed: list[str]  # advice the gate let through (the dangerous failures)
    false_alarms: list[str]  # descriptive text wrongly flagged


def score(examples: list[AdviceExample], predictions: list[bool]) -> ComplianceReport:
    """Pure scorer comparing gold `is_advice` labels to detector predictions."""
    if len(examples) != len(predictions):
        raise ValueError("examples and predictions must be the same length")

    tp = fp = fn = tn = 0
    missed: list[str] = []
    false_alarms: list[str] = []
    for ex, pred in zip(examples, predictions, strict=True):
        if ex.is_advice and pred:
            tp += 1
        elif ex.is_advice and not pred:
            fn += 1
            missed.append(ex.text)
        elif not ex.is_advice and pred:
            fp += 1
            false_alarms.append(ex.text)
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return ComplianceReport(
        total=len(examples),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=round(precision, 3),
        recall=round(recall, 3),
        missed=missed,
        false_alarms=false_alarms,
    )


def run_eval() -> ComplianceReport:
    """Run the detector over the labeled set and score it. Pure — no network."""
    preds = [contains_advice(ex.text).is_advice for ex in ADVICE_EVAL_SET]
    return score(ADVICE_EVAL_SET, preds)
