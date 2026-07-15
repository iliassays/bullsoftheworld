import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("./universe-policy.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText;
const { ALL_UNIVERSE, normalizeUniverseTier, universeStorageKey } = await import(
  `data:text/javascript,${encodeURIComponent(compiled)}`
);

test("accepts only tiers configured for the active market", () => {
  assert.equal(normalizeUniverseTier("large", ["large", "mid", "small", "micro"]), "large");
  assert.equal(
    normalizeUniverseTier("mega", ["large", "mid", "small", "micro"]),
    ALL_UNIVERSE,
  );
  assert.equal(normalizeUniverseTier("mega", ["mega", "large", "mid"]), "mega");
  assert.equal(normalizeUniverseTier("penny", ["mega", "large", "mid"]), ALL_UNIVERSE);
});

test("keeps persisted universe choices tenant-local", () => {
  assert.equal(universeStorageKey("bullsofdhaka"), "bulls.universe.bullsofdhaka");
  assert.equal(universeStorageKey("bullsofwallst"), "bulls.universe.bullsofwallst");
});
