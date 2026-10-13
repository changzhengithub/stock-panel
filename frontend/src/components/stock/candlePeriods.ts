import type { Prices } from "../../api";

type DailyPoint = Prices["points"][number];
export type CandlePeriod = "day" | "week" | "month";
export type CandlePoint = DailyPoint & {
  periodStart: string;
  periodEnd: string;
  issue: "price" | "volume" | null;
};

function utcDate(value: string): Date {
  return new Date(
    Date.UTC(
      Number(value.slice(0, 4)),
      Number(value.slice(4, 6)) - 1,
      Number(value.slice(6, 8)),
    ),
  );
}

function compactDate(value: Date): string {
  return `${value.getUTCFullYear()}${String(value.getUTCMonth() + 1).padStart(2, "0")}${String(value.getUTCDate()).padStart(2, "0")}`;
}

function bounds(value: string, period: CandlePeriod): [string, string] {
  if (period === "day") return [value, value];
  const day = utcDate(value);
  if (period === "week") {
    const start = new Date(day);
    start.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
    const end = new Date(start);
    end.setUTCDate(start.getUTCDate() + 6);
    return [compactDate(start), compactDate(end)];
  }
  const year = day.getUTCFullYear();
  const month = day.getUTCMonth();
  return [
    compactDate(new Date(Date.UTC(year, month, 1))),
    compactDate(new Date(Date.UTC(year, month + 1, 0))),
  ];
}

export function candlePeriods(
  daily: DailyPoint[],
  _basisDate: string | null,
  period: CandlePeriod,
  historyStart: string | null = null,
): CandlePoint[] {
  daily = daily.filter((point) => point.status !== "suspended");
  if (period === "day")
    return daily.map((point) => ({
      ...point,
      periodStart: point.date,
      periodEnd: point.date,
      issue:
        point.close === null
          ? "price"
          : point.volume === null
            ? "volume"
            : null,
    }));

  const result: CandlePoint[] = [];
  for (const day of daily) {
    const [periodStart, periodEnd] = bounds(day.date, period);
    let point = result.at(-1);
    if (!point || point.periodStart !== periodStart) {
      point = {
        status: day.status,
        date: day.date,
        periodStart,
        periodEnd,
        open: day.open,
        high: day.high,
        low: day.low,
        close: day.close,
        volume: day.volume,
        issue: null,
      };
      result.push(point);
    } else {
      point.date = day.date;
      if (day.high !== null)
        point.high =
          point.high === null ? day.high : Math.max(point.high, day.high);
      if (day.low !== null)
        point.low = point.low === null ? day.low : Math.min(point.low, day.low);
      if (day.close !== null) point.close = day.close;
      if (point.volume !== null && day.volume !== null)
        point.volume += day.volume;
    }
    if (
      [day.open, day.high, day.low, day.close].some((value) => value === null)
    )
      point.issue = "price";
    else if (day.volume === null && point.issue !== "price")
      point.issue = "volume";
  }

  // A requested history window can start inside a week or month. Never present
  // that first truncated bucket as a complete weekly/monthly candle.
  // Only the explicit fetch boundary can truncate a period, not the display range.
  return result
    .filter((point) => !historyStart || point.periodStart >= historyStart)
    .map((point) => ({
      ...point,
      open: point.issue === "price" ? null : point.open,
      high: point.issue === "price" ? null : point.high,
      low: point.issue === "price" ? null : point.low,
      close: point.issue === "price" ? null : point.close,
      volume: point.issue === null ? point.volume : null,
    }));
}
