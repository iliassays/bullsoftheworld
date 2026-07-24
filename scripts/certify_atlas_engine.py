"""Print the deterministic Atlas portfolio-engine certification report as JSON."""

from bulls.analytics.model_certification import run_engine_certification


def main() -> None:
    report = run_engine_certification()
    print(report.model_dump_json(indent=2))
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
