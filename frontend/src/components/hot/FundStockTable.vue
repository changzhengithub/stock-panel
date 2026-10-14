<script setup lang="ts">
import type { FundStocks, FundSort, FundPeriod } from "../../api/fundFlow";
import { periodLabels } from "../../api/fundFlow";
import { percent, tone, price } from "../../utils/format";
import { signedMoney } from "./fundFormat";
import FundStatus from "./FundStatus.vue";
defineProps<{
  result: FundStocks | null;
  sort: FundSort;
  page: number;
  period: FundPeriod;
  from: string;
  error: string;
  loading: boolean;
}>();
const emit = defineEmits<{
  page: [v: number];
  sort: [v: FundSort];
  retry: [];
}>();
</script>
<template>
  <section class="stocks-section">
    <div class="section-heading">
      <h3>成分股资金 · {{ periodLabels[period] }}</h3>
      <el-select
        :model-value="sort"
        aria-label="成分股资金排序"
        size="small"
        class="stock-sort"
        @change="emit('sort', $event)"
        ><el-option label="净流入降序" value="net_desc" /><el-option
          label="净流入升序"
          value="net_asc" /><el-option
          label="净占比降序"
          value="rate_desc" /><el-option label="涨跌幅降序" value="pct_desc"
      /></el-select>
    </div>
    <p class="scope-note">
      板块资金按来源完整口径统计，股票列表按本站规则过滤。两者金额可能不相等。
    </p>
    <el-alert v-if="error" :title="error" type="warning" :closable="false"
      ><el-button text @click="emit('retry')">重试</el-button></el-alert
    >
    <el-skeleton v-if="loading" :rows="3" animated />
    <template v-if="result">
      <FundStatus :meta="result.meta" />
      <p class="coverage">
        源 {{ result.source_count }} 只 · 可浏览 {{ result.total }} 只 · 已过滤
        {{ result.filtered_count }} · 未匹配 {{ result.unmatched_count }} ·
        资金缺失 {{ result.missing_count }}
      </p>
      <div class="table-scroll">
        <table class="stock-fund-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>价格</th>
              <th>同周期涨跌</th>
              <th>主力净流入</th>
              <th>净占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in result.items" :key="row.ts_code">
              <td>
                <RouterLink
                  :to="{ path: `/stocks/${row.stock_id}`, query: { from } }"
                  class="stock-link"
                  >{{ row.name }}</RouterLink
                ><small>{{ row.code }}</small>
              </td>
              <td>{{ price(row.price) }}</td>
              <td :class="tone(row.pct_change)">
                {{ percent(row.pct_change) }}
              </td>
              <td :class="tone(row.net_amount)">
                {{ signedMoney(row.net_amount) }}
              </td>
              <td :class="tone(row.net_rate)">{{ percent(row.net_rate) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <el-empty
        v-if="!result.items.length"
        :description="
          result.meta.pending
            ? '正在后台获取成分股资金'
            : '暂无可浏览成分股资金'
        "
        :image-size="55"
      />
      <el-pagination
        v-if="result.total > 20"
        :current-page="page"
        :page-size="20"
        :total="result.total"
        layout="prev, pager, next"
        size="small"
        @current-change="emit('page', $event)"
      />
      <small class="scope-note"
        >价格为资金源返回的未复权报价，以本区来源时间为准；涨跌幅对应所选周期。</small
      >
    </template>
  </section>
</template>
<style scoped>
.stocks-section {
  margin-top: 24px;
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.section-heading h3 {
  margin: 0;
  font-size: 13px;
}
.stock-sort {
  width: 135px;
}
.scope-note,
.coverage {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
}
.coverage {
  margin: 10px 0;
}
.table-scroll {
  overflow: auto;
  margin: 12px 0;
}
.stock-fund-table {
  width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.stock-fund-table td,
.stock-fund-table th {
  padding: 10px 8px;
  border-bottom: 1px solid var(--line);
  text-align: right;
}
.stock-fund-table th {
  color: var(--muted);
  font-weight: 500;
  background: var(--subtle);
}
.stock-fund-table td:first-child,
.stock-fund-table th:first-child {
  text-align: left;
}
.stock-link {
  color: var(--accent);
  font-size: 12px;
}
.stock-fund-table small {
  display: block;
  color: var(--muted);
  margin-top: 3px;
}
</style>
