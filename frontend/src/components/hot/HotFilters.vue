<script setup lang="ts">
import { onUnmounted, shallowRef, watch } from "vue";
import type { FundKind, FundPeriod, FundSort } from "../../api/fundFlow";
const props = defineProps<{
  filters: {
    kind: FundKind;
    period: FundPeriod;
    keyword: string;
    direction: string;
    sort: FundSort;
  };
}>();
const emit = defineEmits<{
  change: [patch: Partial<typeof props.filters>];
  refresh: [];
}>();
const keyword = shallowRef(props.filters.keyword);
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => props.filters.keyword,
  (v) => {
    keyword.value = v;
  },
);
watch(keyword, (v) => {
  clearTimeout(timer);
  if (v !== props.filters.keyword)
    timer = setTimeout(() => emit("change", { keyword: v }), 300);
});
onUnmounted(() => clearTimeout(timer));
</script>
<template>
  <div class="hot-filters">
    <el-radio-group
      :model-value="filters.kind"
      aria-label="板块类型"
      @change="
        (v: string | number | boolean) =>
          emit('change', { kind: v as FundKind })
      "
    >
      <el-radio-button value="concept">概念板块</el-radio-button
      ><el-radio-button value="industry">行业板块</el-radio-button>
    </el-radio-group>
    <el-radio-group
      :model-value="filters.period"
      aria-label="资金周期"
      @change="
        (v: string | number | boolean) =>
          emit('change', { period: v as FundPeriod })
      "
    >
      <el-radio-button value="today">今日</el-radio-button
      ><el-radio-button value="5d">5日</el-radio-button
      ><el-radio-button value="10d">10日</el-radio-button>
    </el-radio-group>
    <el-input
      v-model="keyword"
      clearable
      placeholder="搜索全部板块名称或代码"
      aria-label="搜索板块"
      class="board-search"
    />
    <el-select
      :model-value="filters.sort"
      aria-label="资金排序"
      class="sort-select"
      @change="
        (v: string | number | boolean) =>
          emit('change', { sort: v as FundSort })
      "
    >
      <el-option label="主力净流入 ↓" value="net_desc" /><el-option
        label="主力净流入 ↑"
        value="net_asc"
      />
      <el-option label="主力净占比 ↓" value="rate_desc" /><el-option
        label="主力净占比 ↑"
        value="rate_asc"
      />
      <el-option label="涨跌幅 ↓" value="pct_desc" /><el-option
        label="涨跌幅 ↑"
        value="pct_asc"
      />
    </el-select>
    <el-button @click="emit('refresh')">刷新</el-button>
    <div class="direction-tabs" role="group" aria-label="资金方向">
      <button
        :class="{ active: filters.direction === 'all' }"
        :aria-pressed="filters.direction === 'all'"
        @click="emit('change', { direction: 'all' })"
      >
        全部排行
      </button>
      <button
        :class="{ active: filters.direction === 'in' }"
        :aria-pressed="filters.direction === 'in'"
        @click="emit('change', { direction: 'in', sort: 'net_desc' })"
      >
        资金流入
      </button>
      <button
        :class="{ active: filters.direction === 'out' }"
        :aria-pressed="filters.direction === 'out'"
        @click="emit('change', { direction: 'out', sort: 'net_asc' })"
      >
        资金流出
      </button>
    </div>
  </div>
</template>
<style scoped>
.hot-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 18px 0;
}
.board-search {
  width: 230px;
}
.sort-select {
  width: 158px;
}
.direction-tabs {
  flex-basis: 100%;
  display: flex;
  gap: 22px;
  padding-top: 4px;
}
.direction-tabs button {
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  padding: 7px 0;
  color: var(--muted);
}
.direction-tabs .active {
  color: var(--accent);
  border-color: var(--accent);
  font-weight: 600;
}
@media (max-width: 600px) {
  .board-search {
    width: 100%;
  }
  .hot-filters {
    gap: 10px;
  }
  .sort-select {
    flex: 1;
  }
}
</style>
