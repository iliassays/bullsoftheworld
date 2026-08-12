import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("./search-target.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText;
const { chooseSearchTarget } = await import(
  `data:text/javascript,${encodeURIComponent(compiled)}`
);

const symbols = [{ code: "VOLUME" }, { code: "AAPL" }];
const desks = [{ handle: "BullsOfWallStVolume", name: "Unusual Volume" }];

test("exact ticker remains the first Enter action", () => {
  assert.deepEqual(chooseSearchTarget("$volume", symbols, desks), {
    kind: "symbol",
    value: symbols[0],
  });
});

test("exact agent name or handle opens the agent", () => {
  assert.equal(chooseSearchTarget("Unusual Volume", [], desks).kind, "desk");
  assert.equal(chooseSearchTarget("@bullsofwallstvolume", symbols, desks).kind, "desk");
});

test("results fall back to stock first and then agent", () => {
  assert.equal(chooseSearchTarget("vol", symbols, desks).kind, "symbol");
  assert.equal(chooseSearchTarget("vol", [], desks).kind, "desk");
  assert.equal(chooseSearchTarget("missing", [], []), null);
});
