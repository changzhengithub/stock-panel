<script setup lang="ts">
import { ElAutocomplete } from "element-plus";
import { shallowRef, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { get } from "../../api";
import { useLibrary, type SavedStock } from "../../composables/useLibrary";
const router = useRouter(),
  route = useRoute();
const keyword = shallowRef(""),
  error = shallowRef("");
const { recent, remember } = useLibrary();
let controller: AbortController | undefined;
async function suggest(
  query: string,
  callback: (items: Record<string, unknown>[]) => void,
) {
  controller?.abort();
  const current = (controller = new AbortController());
  error.value = "";
  try {
    const stocks = query.trim()
      ? await get<SavedStock[]>(
          `/search?keyword=${encodeURIComponent(query)}`,
          current.signal,
        )
      : recent.value;
    if (!current.signal.aborted)
      callback(stocks.map((s) => ({ ...s, value: s.name })));
  } catch (e) {
    if (!current.signal.aborted) {
      error.value = "查找失败，请重新输入重试";
      callback([]);
    }
  }
}
function open(value: Record<string, unknown>) {
  const stock = value as unknown as SavedStock;
  remember(stock);
  keyword.value = "";
  router.push({
    path: `/stocks/${stock.id}`,
    query: {
      from:
        route.path === "/market"
          ? route.fullPath
          : String(route.query.from ?? "/market"),
    },
  });
}
onUnmounted(() => controller?.abort());
</script>
<template>
  <div class="global-search">
    <el-autocomplete
      v-model="keyword"
      :fetch-suggestions="suggest"
      :debounce="200"
      clearable
      placeholder="全市场 · 代码 / 名称 / 拼音"
      aria-label="全市场搜索"
      @select="open"
      popper-class="global-search-results"
    >
      <template #prefix>⌕</template>
      <template #default="{ item }"
        ><span>{{ item.name }}</span
        ><small>{{ item.code }} · {{ item.board }}</small></template
      >
    </el-autocomplete>
    <span v-if="error" role="alert" class="search-error">{{ error }}</span>
  </div>
</template>
<style scoped>
.global-search {
  margin-left: auto;
  width: 280px;
  min-width: 160px;
  position: relative;
}
.global-search :deep(.el-autocomplete) {
  width: 100%;
}
.search-error {
  position: absolute;
  top: 36px;
  right: 0;
  background: white;
  color: var(--down);
  font-size: 12px;
  z-index: 10;
}
@media (max-width: 640px) {
  .global-search {
    width: 100%;
    flex: 1 0 100%;
  }
}
</style>
<style>
.global-search-results li {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}
.global-search-results small {
  color: var(--muted);
}
</style>
