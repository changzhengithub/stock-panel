import type { Prices } from "../../api";

type Point = Prices["points"][number];

export function indicators(points: Point[]) {
  const ma5: (number | null)[] = Array(points.length).fill(null);
  const ma10: (number | null)[] = Array(points.length).fill(null);
  const ma20: (number | null)[] = Array(points.length).fill(null);
  const ma60: (number | null)[] = Array(points.length).fill(null);
  const volumeMa5: (number | null)[] = Array(points.length).fill(null);
  const volumeMa10: (number | null)[] = Array(points.length).fill(null);
  const dif: (number | null)[] = Array(points.length).fill(null);
  const dea: (number | null)[] = Array(points.length).fill(null);
  const macd: (number | null)[] = Array(points.length).fill(null);
  const rsi: (number | null)[] = Array(points.length).fill(null);
  let closes: number[] = [];
  let volumes: number[] = [];
  let shortEma: number | null = null;
  let longEma: number | null = null;
  let signal: number | null = null;
  let difSeed: number[] = [];
  let gains: number[] = [];
  let losses: number[] = [];
  let avgGain: number | null = null;
  let avgLoss: number | null = null;

  points.forEach((point, index) => {
    const close = point.close;
    if (close === null) {
      closes = [];
      volumes = [];
      shortEma = longEma = signal = null;
      difSeed = [];
      gains = [];
      losses = [];
      avgGain = avgLoss = null;
      return;
    }
    const previous = closes.at(-1);
    closes.push(close);
    for (const [period, values] of [
      [5, ma5],
      [10, ma10],
      [20, ma20],
      [60, ma60],
    ] as const) {
      if (closes.length >= period)
        values[index] =
          closes.slice(-period).reduce((sum, value) => sum + value, 0) / period;
    }
    if (point.volume === null) volumes = [];
    else {
      volumes.push(point.volume);
      if (volumes.length >= 5)
        volumeMa5[index] =
          volumes.slice(-5).reduce((sum, value) => sum + value, 0) / 5;
      if (volumes.length >= 10)
        volumeMa10[index] =
          volumes.slice(-10).reduce((sum, value) => sum + value, 0) / 10;
    }
    if (shortEma === null && closes.length === 12)
      shortEma = closes.reduce((sum, value) => sum + value, 0) / 12;
    else if (shortEma !== null) shortEma += ((close - shortEma) * 2) / 13;
    if (longEma === null && closes.length === 26)
      longEma = closes.reduce((sum, value) => sum + value, 0) / 26;
    else if (longEma !== null) longEma += ((close - longEma) * 2) / 27;
    if (shortEma !== null && longEma !== null) {
      const currentDif = shortEma - longEma;
      dif[index] = currentDif;
      if (signal === null) {
        difSeed.push(currentDif);
        if (difSeed.length === 9)
          signal = difSeed.reduce((sum, value) => sum + value, 0) / 9;
      } else signal += ((currentDif - signal) * 2) / 10;
      if (signal !== null) {
        dea[index] = signal;
        macd[index] = 2 * (currentDif - signal);
      }
    }
    if (previous === undefined) return;
    const change = close - previous;
    const gain = Math.max(change, 0);
    const loss = Math.max(-change, 0);
    if (avgGain === null || avgLoss === null) {
      gains.push(gain);
      losses.push(loss);
      if (gains.length === 14) {
        avgGain = gains.reduce((sum, value) => sum + value, 0) / 14;
        avgLoss = losses.reduce((sum, value) => sum + value, 0) / 14;
      }
    } else {
      avgGain = (avgGain * 13 + gain) / 14;
      avgLoss = (avgLoss * 13 + loss) / 14;
    }
    if (avgGain !== null && avgLoss !== null)
      rsi[index] =
        avgLoss === 0
          ? avgGain === 0
            ? 50
            : 100
          : 100 - 100 / (1 + avgGain / avgLoss);
  });
  return { ma5, ma10, ma20, ma60, volumeMa5, volumeMa10, dif, dea, macd, rsi };
}
