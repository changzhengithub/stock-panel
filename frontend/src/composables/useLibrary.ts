import { shallowRef } from "vue";
import type { Stock } from "../api";
export type SavedStock = Pick<
  Stock,
  "id" | "ts_code" | "code" | "name" | "board"
>;
function read(key: string): SavedStock[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(value)
      ? value
          .filter(
            (s) =>
              s &&
              Number.isInteger(s.id) &&
              typeof s.ts_code === "string" &&
              typeof s.name === "string",
          )
          .slice(0, 500)
      : [];
  } catch {
    return [];
  }
}
const favorites = shallowRef(read("guanshi-favorites"));
const recent = shallowRef(read("guanshi-recent"));
const storageError = shallowRef("");
function snapshot(stock: SavedStock): SavedStock {
  const { id, ts_code, code, name, board } = stock;
  return { id, ts_code, code, name, board };
}
function save(key: string, value: SavedStock[]) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    storageError.value = "";
  } catch {
    storageError.value = "浏览器无法保存，当前修改仅在本次打开期间有效。";
  }
}
window.addEventListener("storage", (event) => {
  if (event.key === "guanshi-favorites") favorites.value = read(event.key);
  if (event.key === "guanshi-recent") recent.value = read(event.key);
});
export function useLibrary() {
  const isFavorite = (code: string) =>
    favorites.value.some((s) => s.ts_code === code);
  function toggle(stock: SavedStock) {
    if (!isFavorite(stock.ts_code) && favorites.value.length >= 500) {
      storageError.value = "自选最多保存 500 只，请先移除不再关注的股票。";
      return;
    }
    favorites.value = isFavorite(stock.ts_code)
      ? favorites.value.filter((s) => s.ts_code !== stock.ts_code)
      : [...favorites.value, snapshot(stock)];
    save("guanshi-favorites", favorites.value);
  }
  function remember(stock: SavedStock) {
    recent.value = [
      snapshot(stock),
      ...recent.value.filter((s) => s.ts_code !== stock.ts_code),
    ].slice(0, 30);
    save("guanshi-recent", recent.value);
  }
  return { favorites, recent, storageError, isFavorite, toggle, remember };
}
