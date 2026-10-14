<script setup lang="ts">
import { shallowRef, watch } from "vue";
import { get, type Filters } from "../../api";
import { percent, tone } from "../../utils/format";
import { updateData } from "../../utils/updateData";
const props = defineProps<{ filters: Filters; revision?: string | null }>();
interface Summary {
  total: number;
  valid: number;
  missing: number;
  up: number;
  down: number;
  flat: number;
  trade_date: string | null;
  index: null | { close: number; pct_chg: number; trade_date: string };
  index_pending: boolean;
  index_message: string | null;
}
const data = shallowRef<Summary | null>(null),
  error = shallowRef("");
watch(
  () => [
    props.filters.industry_id,
    props.filters.industry_level,
    props.filters.concept_id,
    props.filters.view,
    props.filters.exchange,
    props.filters.board,
    props.revision,
  ],
  async (current, previous, cleanup) => {
    const c = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    cleanup(() => {
      c.abort();
      clearTimeout(timer);
    });
    const contextChanged =
      !previous ||
      current.slice(0, -1).some((value, i) => value !== previous[i]);
    if (contextChanged) {
      data.value = null;
      error.value = "";
    }
    const params = new URLSearchParams();
    for (const key of [
      "industry_id",
      "industry_level",
      "concept_id",
      "exchange",
      "board",
    ] as const)
      if (props.filters[key]) params.set(key, String(props.filters[key]));
    async function fetchSummary(attempt = 0) {
      try {
        const result = await get<Summary>(
          "/industry-summary?" + params,
          c.signal,
        );
        if (c.signal.aborted) return;
        updateData(
          data,
          !contextChanged && data.value && result.index_pending
            ? { ...result, index: data.value.index, index_pending: false }
            : result,
        );
        error.value = "";
        if (result.index_pending) {
          if (attempt < 60)
            timer = setTimeout(() => fetchSummary(attempt + 1), 3000);
          else
            data.value = {
              ...result,
              index_pending: false,
              index_message: "指数仍在后台读取，请稍后刷新页面",
            };
        }
      } catch {
        if (!c.signal.aborted) error.value = "市场概况暂不可用";
      }
    }
    await fetchSummary();
  },
  { immediate: true },
);
</script>
<template>
  <div class="market-overview" aria-label="市场概况">
    <template v-if="data">
      <span
        v-if="filters.view === 'industry' && filters.industry_id"
        class="index-stat"
        >行业指数（完整行业）
        <strong v-if="data.index" :class="tone(data.index.pct_chg)"
          >{{ data.index.close.toFixed(2) }} /
          {{ percent(data.index.pct_chg) }}</strong
        >
        <span v-else :title="data.index_message ?? undefined">{{
          data.index_pending ? "读取中…" : "同日指数暂无"
        }}</span>
      </span>
      <span class="up">上涨 {{ data.up }}</span
      ><span class="down">下跌 {{ data.down }}</span
      ><span>平盘 {{ data.flat }}</span>
      <span class="coverage"
        >有效 {{ data.valid }} / {{ data.total }} · 未参与
        {{ data.missing }}</span
      >
      <small
        >家数按当前{{
          filters.view === "concept" ? "概念" : "行业"
        }}及市场的全部股票统计，不受搜索、自选或权重名单限制</small
      >
    </template>
    <span v-else>{{ error || "正在读取市场概况…" }}</span>
    <RouterLink
      v-if="filters.view === 'industry' && filters.industry_id"
      class="chain-entry"
      :to="{
        path: '/industry-chains',
        query: { industry_id: filters.industry_id },
      }"
      >查看产业链 →</RouterLink
    >
  </div>
</template>
<style scoped>
.market-overview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  padding: 10px 22px 12px;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  align-items: center;
}
.chain-entry {
  color: var(--accent);
  font-size: 12px;
}
.index-stat {
  display: flex;
  gap: 8px;
}
.market-overview small {
  color: var(--muted);
  font-size: 10px;
  width: 100%;
}
.coverage {
  margin-left: auto;
  color: var(--muted);
}
@media (max-width: 600px) {
  .market-overview {
    padding-inline: 14px;
  }
}
</style>
