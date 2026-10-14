import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";
const source = readFileSync(
  new URL("../src/utils/browseOrigin.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { browseOrigin } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);
test("known market and hot board origins preserve their query", () => {
  for (const path of [
    "/market?industry_level=2",
    "/industry-chains/power-battery?revision=abc&node=cell",
    "/industry-chains/power-battery/compare?node=cell&stock_ids=1,2",
    "/hot-sectors?period=5d&selected=EM-concept-BK1136",
    "/hot-sectors/EM-industry-BK1340?period=10d",
  ])
    assert.equal(browseOrigin(path), path);
});
test("external and malformed origins cannot become return targets", () => {
  for (const path of [
    null,
    "/industry-chains/power-battery/other",
    "/industry-chains/power-battery/../../elsewhere",
    "/industry-chains//evil",
    [],
    "//evil.invalid/market",
    "https://evil.invalid/market",
    "/market/../../evil",
    "/market\\evil",
    "/hot-sectors/not-a-board",
    "/hot-sectors-other",
    "/hot-sectors/EM-concept-BK1/../../elsewhere",
  ])
    assert.equal(browseOrigin(path), "/market");
});
