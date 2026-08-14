import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("./research-chart.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText;
const helpers = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

const condition = {
  key: "participation_expansion",
  state: "not_observed",
  title: "Participation expansion",
  why_it_matters: "why",
  limitation: "limit",
  checks: [
    { label: "Volume versus prior 20 sessions", fact_key: "relative_volume_20", observed: 1.62, expected: ">= 1.50x", unit: "multiple", passed: true },
    { label: "Completed-session price change", fact_key: "daily_return_pct", observed: -0.42, expected: "> 0%", unit: "percent", passed: false },
  ],
  transitions: Array.from({ length: 9 }, (_, index) => ({ date: `2026-07-${String(index + 1).padStart(2, "0")}`, close: 10 + index, sequence: index + 1 })),
};

test("condition summary and values remain descriptive", () => {
  assert.equal(helpers.conditionSummary(condition, "en"), "1 of 2 checks are present; the full condition is not observed.");
  assert.equal(helpers.conditionSummary(condition, "bn"), "2টির মধ্যে 1টি মিলেছে; সম্পূর্ণ শর্ত এখনো মেলেনি।");
  assert.equal(helpers.formatCheckValue(condition.checks[0]), "1.62x");
  assert.equal(helpers.formatCheckValue(condition.checks[1]), "-0.4%");
});

test("Bangla labels do not fall back to English for registered checks", () => {
  assert.equal(helpers.checkLabel(condition.checks[0], "bn"), "আগের ২০ সেশনের তুলনায় ভলিউম");
  assert.equal(helpers.conditionStateLabel("observed", "bn"), "শর্ত মিলেছে");
});

test("chart annotations are capped to the latest transitions", () => {
  assert.deepEqual(helpers.recentTransitions(condition, 3).map((item) => item.sequence), [7, 8, 9]);
});
