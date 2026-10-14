import { shallowRef } from "vue";
export interface SavedChain {
  id: string;
  name: string;
  node: string;
  nodeName: string;
}
const key = "guanshi-chain-library-v1";
function read(): SavedChain[] {
  try {
    const x = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(x)
      ? x
          .filter(
            (v): v is SavedChain =>
              v &&
              typeof v.id === "string" &&
              /^[a-z0-9-]+$/.test(v.id) &&
              typeof v.name === "string" &&
              typeof v.node === "string" &&
              /^[a-z0-9_-]*$/.test(v.node) &&
              typeof v.nodeName === "string",
          )
          .slice(0, 200)
      : [];
  } catch {
    return [];
  }
}
const saved = shallowRef(read()),
  error = shallowRef("");
window.addEventListener("storage", (e) => {
  if (e.key === key || e.key === null) saved.value = read();
});
export function useChainLibrary() {
  const has = (id: string, node = "") =>
    saved.value.some((x) => x.id === id && x.node === node);
  function toggle(item: SavedChain) {
    if (!has(item.id, item.node) && saved.value.length >= 200) {
      error.value = "产业链与节点收藏最多 200 项。";
      return;
    }
    saved.value = has(item.id, item.node)
      ? saved.value.filter((x) => x.id !== item.id || x.node !== item.node)
      : [...saved.value, item];
    try {
      localStorage.setItem(key, JSON.stringify(saved.value));
      error.value = "";
    } catch {
      error.value = "浏览器无法保存收藏，当前修改仅本次打开有效。";
    }
  }
  return { saved, error, has, toggle };
}
