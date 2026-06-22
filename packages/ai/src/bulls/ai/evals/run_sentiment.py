"""Run the sentiment eval and print a report.

    ANTHROPIC_API_KEY=... uv run python -m bulls.ai.evals.run_sentiment

No AI feature merges without passing this. Treat a regression here as a build failure.
"""

from __future__ import annotations

import asyncio

from bulls.ai.client import default_model
from bulls.ai.evals.sentiment import LABELS, run_eval


async def _main() -> None:
    report = await run_eval()
    print(f"\nmodel: {default_model()}")
    print(f"accuracy: {report.correct}/{report.total} = {report.accuracy:.1%}")
    print("per-label:", {k: f"{v:.0%}" for k, v in report.per_label_accuracy.items()})

    print("\nconfusion (rows = expected, cols = predicted):")
    print("            " + "".join(f"{p:>9}" for p in LABELS))
    for exp in LABELS:
        row = report.confusion[exp]
        print(f"  {exp:>9} " + "".join(f"{row[p]:>9}" for p in LABELS))

    if report.mistakes:
        print(f"\n{len(report.mistakes)} mistakes:")
        for m in report.mistakes:
            print(f"  expected {m.expected:>7}, got {m.predicted:>7}: {m.text[:60]}")


if __name__ == "__main__":
    asyncio.run(_main())
