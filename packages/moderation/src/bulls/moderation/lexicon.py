"""Per-tenant config loader (spec §6). Turns `tenants/<name>/moderation/` files into a compiled
`Policy`. Config is data, not code — hot-reloadable, and each tenant ships its own lexicons/patterns.

Files:
- `patterns.yml`     — regulatory regex rules + L2 thresholds.
- `abuse_mask.txt`   — words that get MASKed (mild profanity). One entry per line; `#` comments.
- `abuse_block.txt`  — slurs / threats that get BLOCKed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .types import Action, Category


@dataclass(frozen=True)
class PatternRule:
    id: str
    category: Category
    action: Action
    regex: re.Pattern
    target: str = "folded"  # which normalized view to match: "folded" | "compact"
    reason_code: str | None = None
    # When true, a match is suppressed if a negation sits next to it (e.g. "wouldn't buy $GP",
    # "$GP kinen na") — so disclaimed/negated phrasing isn't held as advice. See rules.py.
    guard_negation: bool = False


@dataclass(frozen=True)
class Thresholds:
    # L2 risk bands: < gray_low → ALLOW, >= gray_high → BLOCK, between → HOLD (gray zone).
    gray_low: float = 0.35
    gray_high: float = 0.80


@dataclass(frozen=True)
class Policy:
    pattern_rules: list[PatternRule] = field(default_factory=list)
    mask_words: list[str] = field(default_factory=list)
    block_words: list[str] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)


def _read_words(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s.lower())
    return out


def load_policy(config_dir: str | Path) -> Policy:
    d = Path(config_dir)
    rules: list[PatternRule] = []
    thresholds = Thresholds()

    patterns_file = d / "patterns.yml"
    if patterns_file.exists():
        doc = yaml.safe_load(patterns_file.read_text(encoding="utf-8")) or {}
        for raw in doc.get("rules", []):
            rules.append(
                PatternRule(
                    id=raw["id"],
                    category=Category(raw["category"]),
                    action=Action(raw["action"]),
                    regex=re.compile(raw["pattern"], re.I),
                    target=raw.get("target", "folded"),
                    reason_code=raw.get("reason_code"),
                    guard_negation=bool(raw.get("guard_negation", False)),
                )
            )
        t = doc.get("thresholds") or {}
        thresholds = Thresholds(
            gray_low=float(t.get("gray_low", Thresholds.gray_low)),
            gray_high=float(t.get("gray_high", Thresholds.gray_high)),
        )

    return Policy(
        pattern_rules=rules,
        mask_words=_read_words(d / "abuse_mask.txt"),
        block_words=_read_words(d / "abuse_block.txt"),
        thresholds=thresholds,
    )
