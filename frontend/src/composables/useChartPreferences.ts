import { shallowRef, watch } from "vue";
import type { CandlePeriod } from "../components/stock/candlePeriods";
export type ChartRange = "1m" | "3m" | "1y" | "3y" | "5y" | "10y";
function saved(key: string, values: string[], fallback: string) {
  try {
    const value = localStorage.getItem(key);
    return value && values.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}
const period = shallowRef(
  saved("guanshi-period", ["day", "week", "month"], "day") as CandlePeriod,
);
const range = shallowRef(
  saved(
    "guanshi-range",
    ["1m", "3m", "1y", "3y", "5y", "10y"],
    "3m",
  ) as ChartRange,
);
const adjustment = shallowRef(
  saved("guanshi-adjustment", ["qfq", "none"], "qfq") as "qfq" | "none",
);
const indicator = shallowRef(
  saved("guanshi-indicator", ["volume", "macd", "rsi"], "volume") as
    "volume" | "macd" | "rsi",
);
for (const [key, value] of [
  ["period", period],
  ["range", range],
  ["adjustment", adjustment],
  ["indicator", indicator],
] as const)
  watch(value, (v) => {
    try {
      localStorage.setItem("guanshi-" + key, v);
    } catch {
      /* Session preferences still work. */
    }
  });
watch(period, (value) => {
  if (value === "month" && ["1m", "3m", "1y"].includes(range.value))
    range.value = "5y";
  else if (value === "week" && range.value === "1m") range.value = "1y";
});
export function useChartPreferences() {
  return { period, range, adjustment, indicator };
}
