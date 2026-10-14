<script setup lang="ts">
import { computed, toRef } from "vue";
import type { FundPeriod } from "../../api/fundFlow";
import { periodLabels } from "../../api/fundFlow";
import { useFundDetail } from "../../composables/useHotSectors";
import { date, percent, tone } from "../../utils/format";
import { signedMoney } from "./fundFormat";
import FundStatus from "./FundStatus.vue";
import FundTrend from "./FundTrend.vue";
import FundStockTable from "./FundStockTable.vue";
const props = defineProps<{ id: string; period: FundPeriod; from: string }>();
const { detail, history, stocks, days, stockPage, stockSort } = useFundDetail(
  toRef(props, "id"),
  toRef(props, "period"),
);
const breakdown = computed(() => {
  const row = detail.data.value?.breakdown;
  return [
    ["超大单", row?.extra_large],
    ["大单", row?.large],
    ["中单", row?.medium],
    ["小单", row?.small],
  ].map(([label, value]) => ({
    label: String(label),
    value: value as number | null | undefined,
  }));
});
const largest = computed(() =>
  Math.max(1, ...breakdown.value.map((r) => Math.abs(r.value || 0))),
);
const provisional = computed(() =>
  history.data.value?.items.find((r) => r.provisional),
);
</script>
<template>
  <aside class="hot-detail">
    <el-alert
      v-if="detail.error.value"
      :title="detail.error.value"
      type="warning"
      :closable="false"
      ><el-button text @click="detail.retry">重试</el-button></el-alert
    >
    <el-skeleton v-if="detail.loading.value" :rows="5" animated />
    <template v-if="detail.data.value">
      <div class="detail-heading">
        <div>
          <span class="detail-kind"
            >{{
              detail.data.value.board.kind === "concept" ? "概念" : "行业"
            }}
            · 东方财富分类</span
          >
          <h2>{{ detail.data.value.board.name }}</h2>
          <small>{{ detail.data.value.board.code }}</small>
        </div>
        <div
          class="summary-amount"
          :class="tone(detail.data.value.summary?.net_amount)"
        >
          <strong>{{
            signedMoney(detail.data.value.summary?.net_amount)
          }}</strong
          ><small>{{ periodLabels[period] }}主力净流入</small>
        </div>
      </div>
      <FundStatus :meta="detail.data.value.meta" />
      <div v-if="detail.data.value.summary" class="summary-strip">
        <span
          >同周期涨跌
          <b :class="tone(detail.data.value.summary.pct_change)">{{
            percent(detail.data.value.summary.pct_change)
          }}</b></span
        ><span
          >净占比
          <b :class="tone(detail.data.value.summary.net_rate)">{{
            percent(detail.data.value.summary.net_rate)
          }}</b></span
        >
      </div>
      <div v-if="detail.data.value.summary?.lead_stock" class="lead-stock">
        {{ periodLabels[period] }}主力净流入最大股：<RouterLink
          v-if="detail.data.value.lead_stock_id"
          :to="{
            path: `/stocks/${detail.data.value.lead_stock_id}`,
            query: { from },
          }"
          >{{ detail.data.value.summary.lead_stock }}</RouterLink
        ><span v-else
          >{{ detail.data.value.summary.lead_stock }} ·
          {{ detail.data.value.lead_unavailable_reason || "无法进入" }}</span
        >
      </div>
      <section class="trend-section">
        <div class="section-heading">
          <h3>每日资金趋势</h3>
          <el-radio-group v-model="days" size="small" aria-label="趋势区间"
            ><el-radio-button :value="20">20交易日</el-radio-button
            ><el-radio-button :value="60"
              >60交易日</el-radio-button
            ></el-radio-group
          >
        </div>
        <el-alert
          v-if="history.error.value"
          :title="history.error.value"
          type="warning"
          :closable="false"
          ><el-button text @click="history.retry">重试</el-button></el-alert
        >
        <template v-if="history.data.value"
          ><FundStatus :meta="history.data.value.meta" />
          <FundTrend
            v-if="history.data.value.items.length"
            :items="history.data.value.items"
          />
          <el-empty
            v-else
            :description="
              history.data.value.meta.pending
                ? '正在后台获取资金历史'
                : '暂无资金历史'
            "
            :image-size="55"
          />
          <p class="chart-note">
            实际可用 {{ date(history.data.value.available_start) }} —
            {{ date(history.data.value.available_end) }} ·
            {{ history.data.value.available_days }} 条{{
              history.data.value.available_days < days ? "，不足所选区间" : ""
            }}。缺失为断点。
          </p>
          <p v-if="provisional" class="chart-note">
            *
            {{ date(provisional.trade_date) }}
            为当日数据，未确认最终值，以浅色显示。
          </p>
        </template>
        <el-skeleton v-else-if="history.loading.value" :rows="3" animated />
      </section>
      <section class="breakdown-section">
        <h3>当日资金拆分</h3>
        <FundStatus :meta="detail.data.value.breakdown_meta" />
        <div v-for="row in breakdown" :key="row.label" class="breakdown-row">
          <span>{{ row.label }}</span>
          <div class="bar-track">
            <div
              class="bar-fill"
              :class="tone(row.value)"
              :style="{
                width: `${(Math.abs(row.value || 0) / largest) * 100}%`,
              }"
            />
          </div>
          <b :class="tone(row.value)">{{ signedMoney(row.value) }}</b>
        </div>
      </section>
      <FundStockTable
        :result="stocks.data.value"
        :error="stocks.error.value"
        :loading="stocks.loading.value"
        :sort="stockSort"
        :page="stockPage"
        :period="period"
        :from="from"
        @page="stockPage = $event"
        @sort="stockSort = $event"
        @retry="stocks.retry"
      />
    </template>
    <el-empty v-else-if="!id" description="选择一个板块，查看资金趋势" />
  </aside>
</template>
<style scoped>
.hot-detail {
  min-width: 0;
  padding: 22px;
  background: var(--subtle);
  border: 1px solid var(--line);
  border-radius: 6px;
  align-self: start;
}
.detail-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.detail-kind {
  font-size: 10px;
  color: var(--muted);
}
.detail-heading h2 {
  font-size: 20px;
  margin: 6px 0;
}
.detail-heading small {
  font-size: 11px;
  color: var(--muted);
}
.summary-amount {
  text-align: right;
  padding-top: 15px;
  white-space: nowrap;
}
.summary-amount strong {
  display: block;
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}
.summary-amount small {
  display: block;
  margin-top: 4px;
}
.summary-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  margin: 14px 0;
  font-size: 12px;
}
.summary-strip b {
  margin-left: 6px;
}
.lead-stock {
  font-size: 11px;
  line-height: 1.8;
  color: var(--muted);
}
.lead-stock a {
  color: var(--accent);
}
.trend-section {
  margin-top: 24px;
}
.section-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}
.section-heading h3,
.breakdown-section h3 {
  margin: 0;
  font-size: 13px;
}
.chart-note {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.8;
}
.breakdown-section {
  margin-top: 22px;
}
.breakdown-section h3 {
  margin-bottom: 10px;
}
.breakdown-row {
  display: grid;
  grid-template-columns: 45px 1fr 100px;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  font-size: 11px;
}
.breakdown-row b {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
.bar-track {
  height: 6px;
  background: #e7ecf3;
  border-radius: 2px;
}
.bar-fill {
  height: 100%;
  border-radius: 2px;
}
.bar-fill.up {
  background: var(--up);
}
.bar-fill.down {
  background: var(--down);
}
@media (max-width: 600px) {
  .hot-detail {
    padding: 16px;
  }
  .summary-amount strong {
    font-size: 20px;
  }
  .detail-heading h2 {
    font-size: 18px;
  }
}
</style>
