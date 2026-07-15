import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("./locale-route.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2020, target: ts.ScriptTarget.ES2020 },
}).outputText;
const { invalidLocaleRedirectTarget } = await import(
  `data:text/javascript,${encodeURIComponent(compiled)}`
);
const portalLocales = ["bn", "en"];

test("preserves unprefixed account-recovery routes and their tokens", () => {
  assert.equal(
    invalidLocaleRedirectTarget(
      "/reset",
      "?token=test-token",
      "reset",
      "bn",
      portalLocales,
    ),
    "/bn/reset?token=test-token",
  );
  assert.equal(
    invalidLocaleRedirectTarget(
      "/verify",
      "?token=test-token",
      "verify",
      "en",
      portalLocales,
    ),
    "/en/verify?token=test-token",
  );
});

test("preserves other legacy single-segment application routes", () => {
  for (const path of ["/forgot", "/me", "/ideas", "/markets", "/portfolio"]) {
    assert.equal(
      invalidLocaleRedirectTarget(path, "", path.slice(1), "bn", portalLocales),
      `/bn${path}`,
    );
  }
});

test("replaces a known locale that the active tenant does not support", () => {
  assert.equal(
    invalidLocaleRedirectTarget(
      "/bn/reset",
      "?token=test-token",
      "bn",
      "en",
      portalLocales,
    ),
    "/en/reset?token=test-token",
  );
});
