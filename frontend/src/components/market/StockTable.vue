<script setup lang="ts">
import type { Stock, Filters } from "../../api";
import { money, price, percent, tone } from "../../utils/format";
import { useLibrary } from "../../composables/useLibrary";
import StockIndustryLabels from "./StockIndustryLabels.vue";
const props = defineProps<{
  stocks: Stock[];
  selectedId?: number;
  sort: Filters["sort"];
}>();
const emit = defineEmits<{
  open: [id: number];
  select: [id: number];
  sort: [value: Filters["sort"]];
}>();
const { isFavorite, toggle } = useLibrary();
function changeSort({ prop, order }: { prop: string; order: string | null }) {
  const key =
    prop === "pct_chg" ? "pct" : prop === "turnover_rate" ? "turnover" : prop;
  emit(
    "sort",
    order
      ? (`${key}_${order === "ascending" ? "asc" : "desc"}` as Filters["sort"])
      : "default",
  );
}
function rowClass({ row }: { row: Stock }) {
  return row.id === props.selectedId ? "selected-stock" : "";
}
</script>
<template>
  <el-table
    :data="stocks"
    class="stock-table"
    row-key="id"
    :row-class-name="rowClass"
    empty-text="当前范围内暂无股票"
    @sort-change="changeSort"
    :default-sort="
      sort === 'default'
        ? undefined
        : {
            prop: sort
              .replace(/_(asc|desc)$/, '')
              .replace('pct', 'pct_chg')
              .replace('turnover', 'turnover_rate'),
            order: sort.endsWith('_asc') ? 'ascending' : 'descending',
          }
    "
    @row-click="(row: Stock) => emit('select', row.id)"
  >
    <el-table-column
      width="56"
      label="自选"
      fixed
      align="center"
      class-name="favorite-column"
      ><template #default="{ row }"
        ><button
          class="favorite-button"
          :aria-label="`${isFavorite(row.ts_code) ? '移除' : '加入'}自选 ${row.name}`"
          :aria-pressed="isFavorite(row.ts_code)"
          @click.stop="toggle(row)"
        >
          {{ isFavorite(row.ts_code) ? "★" : "☆" }}
        </button></template
      ></el-table-column
    >
    <el-table-column label="股票 / 代码" min-width="140" fixed
      ><template #default="{ row }">
        <button class="stock-link" @click.stop="emit('open', row.id)">
          {{ row.name
          }}<small class="stock-code"
            >{{ row.code }} · {{ row.board }}</small
          ></button
        ><span
          v-if="row.is_st"
          class="tiny-tag"
          :title="
            row.st_source === 'current_name' ? '当前名称标记' : '交易日 ST 状态'
          "
          >ST</span
        >
        <span v-if="row.status !== 'trading'" class="quote-state">{{
          row.status === "suspended" ? "停牌" : "暂无有效行情"
        }}</span>
      </template></el-table-column
    >
    <el-table-column label="SW2021 行业" min-width="145"
      ><template #default="{ row }">
        <StockIndustryLabels :stock="row" /> </template
    ></el-table-column>
    <el-table-column
      label="最新价"
      prop="close"
      sortable="custom"
      min-width="86"
      align="right"
      ><template #default="{ row }"
        ><span :class="['number', tone(row.pct_chg)]">{{
          price(row.close)
        }}</span></template
      ></el-table-column
    >
    <el-table-column
      label="涨跌幅"
      prop="pct_chg"
      sortable="custom"
      min-width="90"
      align="right"
      ><template #default="{ row }"
        ><span :class="['number', tone(row.pct_chg)]">{{
          percent(row.pct_chg)
        }}</span></template
      ></el-table-column
    >
    <el-table-column
      label="成交额"
      prop="amount"
      sortable="custom"
      min-width="96"
      align="right"
      ><template #default="{ row }"
        ><span class="number">{{ money(row.amount) }}</span></template
      ></el-table-column
    >
    <el-table-column
      label="总市值"
      prop="market_cap"
      sortable="custom"
      min-width="105"
      align="right"
      ><template #default="{ row }"
        ><span class="number">{{ money(row.market_cap) }}</span></template
      ></el-table-column
    >
    <el-table-column
      label="换手率"
      prop="turnover_rate"
      sortable="custom"
      min-width="100"
      align="right"
      ><template #default="{ row }">{{
        row.turnover_rate === null ? "—" : row.turnover_rate.toFixed(2) + "%"
      }}</template></el-table-column
    >
    <el-table-column width="42" label=""
      ><template #default="{ row }"
        ><button
          class="preview-select"
          :aria-label="`预览${row.name}`"
          :aria-pressed="row.id === selectedId"
          @click.stop="emit('select', row.id)"
        >
          ›
        </button></template
      ></el-table-column
    >
  </el-table>
</template>
<style scoped>
.stock-table :deep(.favorite-column .cell) {
  padding: 0 6px;
  white-space: nowrap;
}
</style>
