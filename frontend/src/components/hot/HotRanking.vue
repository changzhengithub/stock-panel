<script setup lang="ts">
import type { FundRanking, FundPeriod } from "../../api/fundFlow";
import { percent, tone } from "../../utils/format";
import { signedMoney } from "./fundFormat";
import { periodLabels } from "../../api/fundFlow";
defineProps<{ result: FundRanking; selected: string; period: FundPeriod }>();
const emit = defineEmits<{
  select: [id: string];
  page: [page: number];
  pageSize: [size: number];
}>();
</script>
<template>
  <section class="rank-panel">
    <div class="rank-heading">
      <h2>板块资金排行</h2>
      <small>{{ result.total }} 个匹配板块 · {{ periodLabels[period] }}</small>
    </div>
    <div class="table-scroll">
      <table class="fund-table">
        <thead>
          <tr>
            <th>排名</th>
            <th>板块</th>
            <th>涨跌幅</th>
            <th>主力净流入</th>
            <th>净占比</th>
            <th>最大资金股</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in result.items"
            :key="row.id"
            :class="{ selected: row.id === selected }"
          >
            <td class="rank-number">{{ row.rank }}</td>
            <td>
              <button
                class="board-link"
                :aria-pressed="row.id === selected"
                @click="emit('select', row.id)"
              >
                {{ row.name }}</button
              ><small class="board-code">{{ row.code }}</small>
            </td>
            <td :class="tone(row.pct_change)">{{ percent(row.pct_change) }}</td>
            <td :class="tone(row.net_amount)" class="net-value">
              {{ signedMoney(row.net_amount) }}
            </td>
            <td :class="tone(row.net_rate)">{{ percent(row.net_rate) }}</td>
            <td class="lead-cell" :title="row.lead_stock || '来源未提供'">
              {{ row.lead_stock || "—" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <el-empty
      v-if="!result.items.length"
      :description="
        result.meta.quality_status === 'unavailable'
          ? result.meta.pending
            ? '正在后台获取板块资金'
            : '暂无板块资金数据，稍后刷新'
          : '当前条件下没有板块'
      "
      :image-size="60"
    />
    <div class="rank-pagination">
      <el-pagination
        :current-page="result.page"
        :page-size="result.page_size"
        :total="result.total"
        :page-sizes="[20, 50, 100]"
        layout="prev, pager, next, sizes"
        size="small"
        @current-change="emit('page', $event)"
        @size-change="emit('pageSize', $event)"
      />
    </div>
  </section>
</template>
<style scoped>
.rank-panel {
  min-width: 0;
}
.rank-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 18px 0;
}
.rank-heading h2 {
  margin: 0;
  font-size: 14px;
}
.rank-heading small {
  color: var(--muted);
  font-size: 11px;
}
.table-scroll {
  overflow: auto;
}
.fund-table {
  border-collapse: collapse;
  width: 100%;
  white-space: nowrap;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.fund-table th {
  font-size: 11px;
  color: var(--muted);
  font-weight: 500;
  background: var(--subtle);
  text-align: right;
  padding: 12px 10px;
}
.fund-table td {
  padding: 12px 10px;
  text-align: right;
  border-bottom: 1px solid var(--line);
}
.fund-table th:nth-child(2),
.fund-table td:nth-child(2) {
  text-align: left;
}
.selected {
  background: var(--selection);
}
.fund-table tbody tr:hover {
  background: var(--subtle);
}
.board-link {
  border: 0;
  padding: 0;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.selected .board-link {
  color: var(--accent);
}
.board-code {
  display: block;
  color: var(--muted);
  font-size: 10px;
  margin-top: 4px;
}
.rank-number {
  color: var(--muted);
}
.net-value {
  font-weight: 600;
}
.rank-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0;
  overflow: auto;
}
.lead-cell {
  max-width: 105px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--muted);
  font-size: 11px;
}
@media (max-width: 600px) {
  .fund-table th:last-child,
  .lead-cell {
    display: none;
  }
}
</style>
