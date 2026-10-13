import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/components/stock/indicators.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { indicators } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);

function points(closes) {
  return closes.map((close, index) => ({
    date: `202601${String(index + 1).padStart(2, "0")}`,
    open: close,
    high: close,
    low: close,
    close,
    volume: close === null ? null : 100,
  }));
}

test("MACD waits for 26 and 9 closes; flat prices yield zero", () => {
  const result = indicators(points(Array(40).fill(10)));
  assert.equal(result.dif[24], null);
  assert.equal(result.dif[25], 0);
  assert.equal(result.dea[32], null);
  assert.equal(result.dea[33], 0);
  assert.equal(result.macd[39], 0);
  assert.equal(result.rsi[14], 50);
});

test("RSI uses 14 changes and resets after a missing day", () => {
  const rising = Array.from({ length: 40 }, (_, index) => index + 1);
  const result = indicators(points([...rising, null, ...rising]));
  assert.equal(result.rsi[13], null);
  assert.equal(result.rsi[14], 100);
  assert.equal(result.macd[40], null);
  assert.equal(result.dif[65], null);
  assert.notEqual(result.dif[66], null);
  assert.equal(result.macd[73], null);
  assert.notEqual(result.macd[74], null);
  assert.equal(result.rsi[54], null);
  assert.equal(result.rsi[55], 100);
});

test("price and volume averages need complete windows and restart after gaps", () => {
  const input = points([...Array(65).fill(10), null, ...Array(65).fill(20)]);
  input[69].volume = null;
  const result = indicators(input);
  assert.equal(result.ma5[3], null);
  assert.equal(result.ma5[4], 10);
  assert.equal(result.ma60[58], null);
  assert.equal(result.ma60[59], 10);
  assert.equal(result.ma5[65], null);
  assert.equal(result.ma5[69], null);
  assert.equal(result.ma5[70], 20);
  assert.equal(result.ma60[124], null);
  assert.equal(result.ma60[125], 20);
  assert.equal(result.volumeMa5[68], null);
  assert.equal(result.volumeMa5[69], null);
  assert.equal(result.volumeMa5[74], 100);
  assert.equal(result.volumeMa10[78], null);
  assert.equal(result.volumeMa10[79], 100);
});
