"""Tests for the no-advice compliance gate. Pure and deterministic — always run."""

from __future__ import annotations

from bulls.ai.compliance import contains_advice
from bulls.ai.evals.compliance import run_eval, score
from bulls.ai.evals.dataset import ADVICE_EVAL_SET, AdviceExample


def test_flags_clear_advice():
    assert contains_advice("Buy $GP now, great entry.").is_advice
    assert contains_advice("Set a stop-loss at 240.").is_advice
    assert contains_advice("টার্গেট ৩২০, লাভ তুলে নিন।").is_advice
    assert contains_advice("এখন কিনুন।").is_advice


def test_passes_descriptive_text():
    assert not contains_advice("$GP rose 2% on heavy volume; RSI elevated at 72.").is_advice
    assert not contains_advice("Buyers stepped in after the stock sold off.").is_advice
    assert not contains_advice("Support sits near 250, resistance near 257.").is_advice
    assert not contains_advice("শেয়ারটি ২০০ দিনের গড়ের নিচে রয়েছে।").is_advice


def test_dataset_covers_both_classes():
    labels = {ex.is_advice for ex in ADVICE_EVAL_SET}
    assert labels == {True, False}


def test_eval_recall_is_perfect_and_precision_high():
    report = run_eval()
    # never miss real advice — recall must be 1.0
    assert report.recall == 1.0, f"gate let advice through: {report.missed}"
    # tolerate a little over-flagging, but keep it tight
    assert report.precision >= 0.9, f"too many false alarms: {report.false_alarms}"


def test_score_pure():
    exs = [
        AdviceExample(text="buy now", is_advice=True),
        AdviceExample(text="price rose", is_advice=False),
    ]
    report = score(exs, [True, False])
    assert report.recall == 1.0 and report.precision == 1.0
    assert report.true_positives == 1 and report.true_negatives == 1
