export type Exchange = "" | "SSE" | "SZSE" | "BSE";

export const MARKET_OPTIONS: { value: Exchange; label: string }[] = [
  { value: "", label: "全部 A 股" },
  { value: "SSE", label: "沪市" },
  { value: "SZSE", label: "深市" },
  { value: "BSE", label: "北交所" },
];

const BOARDS_BY_EXCHANGE: Record<Exchange, string[]> = {
  "": ["沪市主板", "科创板", "深市主板", "创业板", "北交所"],
  SSE: ["沪市主板", "科创板"],
  SZSE: ["深市主板", "创业板"],
  BSE: [],
};

export function boardsForExchange(exchange: Exchange): string[] {
  return BOARDS_BY_EXCHANGE[exchange];
}

export function isBoardInExchange(exchange: Exchange, board: string): boolean {
  return board === "" || BOARDS_BY_EXCHANGE[exchange].includes(board);
}
