"""Golden set for the moderation engine (spec §8). Covers each violation category across EN + Banglish,
obfuscation, and — most importantly — false-positive traps, because over-blocking is the failure we
fear most (spec principle #4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bulls.moderation import Action, Category, Context, decide, load_policy, normalize

CONFIG_DIR = Path(__file__).resolve().parents[3] / "tenants" / "bullsofdhaka" / "moderation"


@pytest.fixture(scope="module")
def policy():
    return load_policy(CONFIG_DIR)


# --- L0 normalization ---------------------------------------------------------------


def test_normalize_deobfuscates():
    n = normalize("B.U.Y  $GP  nooooow")
    assert "buy" in n.compact
    assert "$GP" not in n.folded  # cashtags are upper-extracted, folded is lower
    assert n.cashtags == ["GP"]
    assert "now" in n.compact  # repeats fully collapse in the compact view


def test_normalize_extracts_contact():
    n = normalize("join t.me/tips or call 01712345678")
    assert n.urls and n.phones
    assert n.has_contact


# --- violation categories -----------------------------------------------------------


@pytest.mark.parametrize(
    "text,action,category",
    [
        ("Guaranteed 20% profit on $XYZ this week", Action.BLOCK, Category.GUARANTEE),
        ("$GP target 145 by next month", Action.BLOCK, Category.ADVICE),
        ("buy $GP now before it flies", Action.HOLD, Category.ADVICE),
        ("$GP buy now before it flies", Action.HOLD, Category.ADVICE),
        ("$GP kinen akhon", Action.HOLD, Category.ADVICE),
        ("Everyone buy $ABC at open, circuit lagbe kalke", Action.BLOCK, Category.PUMP),
        ("$GP dividend confirmed next week, pakka", Action.HOLD, Category.RUMOUR),
        ("Join my telegram for daily tips t.me/xyz", Action.BLOCK, Category.SOLICITATION),
        ("amar source theke pelam, boro news ashche", Action.HOLD, Category.INSIDER),
    ],
)
def test_violations(policy, text, action, category):
    d = decide(text, policy)
    assert d.action == action, f"{text!r} -> {d.action} ({d.rule_ids})"
    assert category in d.categories


def test_obfuscated_guarantee_still_blocks(policy):
    # repeated letters collapse; still hits the guarantee rule
    assert decide("guaranteeed profit!!!", policy).action == Action.BLOCK


def test_profanity_masks(policy):
    d = decide("this analysis is crap honestly", policy)
    assert d.action == Action.MASK
    assert "****" in d.masked_body
    assert "crap" not in d.masked_body


def test_obfuscated_profanity_masks(policy):
    d = decide("this analysis is cr@p honestly", policy)
    assert d.action == Action.MASK
    assert "****" in d.masked_body
    assert "cr@p" not in d.masked_body


def test_threat_blocks(policy):
    assert decide("I will kill you if this dumps", policy).action == Action.BLOCK


# --- false-positive traps (must ALLOW) ----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "buy low sell high is the oldest rule in the book",  # generic wisdom, no cashtag
        "GP support looks strong near 120, just watching",  # descriptive, no $ / verb
        "$GP vs $ROBI — which has the better margins?",  # legit comparison
        "I think $GP is a solid long-term hold for me",  # 'hold' is not an advice verb here
        "Turnover on $BEXIMCO was unusually high today",  # pure observation
    ],
)
def test_false_positive_traps_allow(policy, text):
    d = decide(text, policy)
    assert d.action == Action.ALLOW, f"over-blocked {text!r} -> {d.action} ({d.rule_ids})"


# --- L2 risk band + context ---------------------------------------------------------


def test_new_account_urgency_holds_but_established_allows(policy):
    text = "$ABC moving fast, could easily do 15% today"  # no rule hit; L2 only
    assert decide(text, policy).action == Action.ALLOW  # neutral context
    new_acct = Context(account_age_days=1.0)
    assert decide(text, policy, new_acct).action == Action.HOLD
    # an official desk saying the same thing stays clean
    official = Context(account_age_days=1.0, is_official=True)
    assert decide(text, policy, official).action == Action.ALLOW


def test_coordinated_duplicates_hold(policy):
    d = decide("$ABC looking interesting here", policy, Context(near_duplicate_count=4))
    assert d.action == Action.HOLD
    assert d.reason_code == "risk_score"
