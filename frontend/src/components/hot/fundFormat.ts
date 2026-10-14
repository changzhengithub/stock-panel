import { money } from "../../utils/format";
export function signedMoney(value: number | null | undefined) {
  return (value != null && value > 0 ? "+" : "") + money(value);
}
