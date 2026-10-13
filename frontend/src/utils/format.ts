export function money(value: number | null | undefined) {
  if (value == null) return "—";
  const abs = Math.abs(value);
  return abs >= 1e8
    ? (value / 1e8).toFixed(2) + " 亿"
    : abs >= 1e4
      ? (value / 1e4).toFixed(2) + " 万"
      : value.toFixed(2);
}
export function price(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(2);
}
export function percent(value: number | null | undefined) {
  return value == null ? "—" : (value > 0 ? "+" : "") + value.toFixed(2) + "%";
}
export function tone(value: number | null | undefined) {
  return value == null || value === 0 ? "neutral" : value > 0 ? "up" : "down";
}
export function date(value: string | null | undefined) {
  return value && value.length === 8
    ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}`
    : (value ?? "尚未更新");
}
