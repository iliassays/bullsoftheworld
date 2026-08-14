import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("./research-conditions.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText;
const helpers = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

test("Atlas links preserve the exact condition and optional cap filter", () => {
  assert.equal(
    helpers.buildAtlasConditionUrl(
      "https://research.bullsofwallst.com",
      "participation_expansion",
      "small",
    ),
    "https://research.bullsofwallst.com/conditions?condition=participation_expansion&cap=small",
  );
});

test("unknown conditions fail closed and same-session observations remain pending", () => {
  assert.equal(helpers.researchConditionFromSearch("buy_now"), null);
  assert.equal(helpers.researchConditionFromSearch("trend_alignment"), "trend_alignment");
  assert.equal(helpers.hasLaterConditionClose("2026-08-13", "2026-08-13"), false);
  assert.equal(helpers.hasLaterConditionClose("2026-08-13", "2026-08-14"), true);
});
