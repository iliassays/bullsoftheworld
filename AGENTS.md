# Repository agent instructions

Read `CLAUDE.md` for the platform contracts before changing this repository.

Before changing Atlas strategies, paper portfolios, backtests, execution assumptions, promotion
gates, or strategy-facing UI, also read `docs/research/atlas-investment-mandate.md`. That mandate is
normative. In particular:

- evidence and capital preservation take priority over strategy count or attractive returns;
- the owner's trend-pullback preference is a hypothesis, not permission to bypass validation;
- DSE and US data, users, calendars, costs, portfolios, and research state remain isolated;
- research urgency, thesis confidence, strategy performance, and portfolio risk stay separate;
- no strategy is preferable to a weak, untestable, or misleading strategy.

Before changing Atlas navigation, decision workflows, research surfaces, portfolio/risk views, or
operator controls, read `docs/research/institutional-investment-operating-model.md`. Atlas is
portfolio-first: signal, evidence, target, constraint, execution, position, outcome, attribution.

Preserve unrelated working-tree changes. Do not deploy or commit unless the user explicitly asks.
