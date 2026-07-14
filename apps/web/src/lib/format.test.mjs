import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("./format.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText;
const { formatOrdinal } = await import(`data:text/javascript,${encodeURIComponent(compiled)}`);

test("formatOrdinal handles English suffixes and teen exceptions", () => {
  assert.deepEqual(
    [0, 1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 100].map(formatOrdinal),
    ["0th", "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "100th"],
  );
});
