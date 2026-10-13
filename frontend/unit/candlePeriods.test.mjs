import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/components/stock/candlePeriods.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { candlePeriods } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);

function point(date, open, high, low, close, volume) {
  return { date, open, high, low, close, volume };
}

test("weekly and monthly candles use first open, last close, extremes and summed volume", () => {
  const daily = [
    point("20260129", 10, 12, 9, 11, 100),
    point("20260130", 11, 13, 10, 12, 200),
    point("20260202", 12, 14, 11, 13, 300),
  ];
  const weeks = candlePeriods(daily, "20260202", "week");
  assert.deepEqual(
    weeks.map(({ periodStart, periodEnd, open, high, low, close, volume }) => ({
      periodStart,
      periodEnd,
      open,
      high,
      low,
      close,
      volume,
    })),
    [
      {
        periodStart: "20260126",
        periodEnd: "20260201",
        open: 10,
        high: 13,
        low: 9,
        close: 12,
        volume: 300,
      },
      {
        periodStart: "20260202",
        periodEnd: "20260208",
        open: 12,
        high: 14,
        low: 11,
        close: 13,
        volume: 300,
      },
    ],
  );
  const months = candlePeriods(daily, "20260202", "month");
  assert.equal(months[0].periodStart, "20260101");
  assert.equal(months[0].periodEnd, "20260131");
  assert.equal(months[0].open, 10);
  assert.equal(months[0].close, 12);
  assert.equal(months[0].high, 13);
  assert.equal(months[0].low, 9);
  assert.equal(months[0].volume, 300);
});

test("a missing daily price suppresses its period, while missing volume only suppresses volume", () => {
  const priceGap = candlePeriods(
    [
      point("20260202", 10, 11, 9, 10, 100),
      point("20260203", null, null, null, null, null),
      point("20260204", 11, 13, 10, 12, 200),
    ],
    "20260204",
    "week",
  )[0];
  assert.equal(priceGap.issue, "price");
  assert.equal(priceGap.open, null);
  assert.equal(priceGap.close, null);
  assert.equal(priceGap.volume, null);

  const volumeGap = candlePeriods(
    [
      point("20260202", 10, 11, 9, 10, 100),
      point("20260203", 11, 12, 10, 12, null),
    ],
    "20260203",
    "week",
  )[0];
  assert.equal(volumeGap.issue, "volume");
  assert.equal(volumeGap.open, 10);
  assert.equal(volumeGap.close, 12);
  assert.equal(volumeGap.volume, null);
});

test("the first period cut by a one-year history window is omitted", () => {
  const daily = [
    point("20251009", 10, 11, 9, 10, 100),
    point("20251010", 10, 12, 9, 11, 200),
    point("20251013", 11, 13, 10, 12, 300),
    point("20251103", 12, 14, 11, 13, 400),
  ];
  assert.equal(candlePeriods(daily, "20261009", "day").length, 4);
  assert.deepEqual(
    candlePeriods(daily, "20261009", "week", "20251009").map((row) => row.periodStart),
    ["20251013", "20251103"],
  );
  assert.deepEqual(
    candlePeriods(daily, "20261009", "month", "20251009").map((row) => row.periodStart),
    ["20251101"],
  );
});

test("confirmed suspension does not invalidate a week or reset the effective daily series", () => {
  const daily=[point('20260202',10,12,9,11,100),{...point('20260203',null,null,null,null,null),status:'suspended'},point('20260204',11,13,10,12,200)];
  const week=candlePeriods(daily,'20260204','week')[0];
  assert.equal(week.close,12);assert.equal(week.volume,300);assert.equal(week.issue,null);
  assert.equal(candlePeriods(daily,'20260204','day').length,2);
});

test("multi-year monthly series is not silently cut back to one year", async () => {
  const daily=[];
  for(let year=2016;year<=2025;year++) for(let month=1;month<=12;month++)daily.push(point(`${year}${String(month).padStart(2,'0')}15`,10,12,9,11,100));
  const months=candlePeriods(daily,'20260105','month','20160101');
  assert.equal(months.length,120);
  const module=ts.transpileModule(readFileSync(new URL('../src/components/stock/indicators.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  const {indicators}=await import(`data:text/javascript;base64,${Buffer.from(module).toString('base64')}`);
  const result=indicators(months);
  for(const key of ['ma60','macd','rsi'])assert.notEqual(result[key].at(-1),null);
});
