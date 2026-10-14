<script setup lang="ts">
import { computed, defineAsyncComponent, shallowRef } from "vue";
import { type Stock } from "../../api";
import { usePriceHistory } from "../../composables/usePriceHistory";
import { useLibrary } from "../../composables/useLibrary";
import { date, money, percent, price, tone } from "../../utils/format";
import type { CandlePeriod } from "../stock/candlePeriods";
import QuoteStamp from "../stock/QuoteStamp.vue";
const CandlestickChart = defineAsyncComponent(
  () => import("../stock/CandlestickChart.vue"),
);
const StockBasics = defineAsyncComponent(
  () => import("../stock/StockBasics.vue"),
);
const props = defineProps<{ stock: Stock }>();
const emit = defineEmits<{ open: [id: number] }>();
const period = shallowRef<CandlePeriod>("day");
const adjustment = shallowRef<"qfq" | "none">("qfq");
const chartRange = computed(() =>
  period.value === "month"
    ? ("5y" as const)
    : period.value === "week"
      ? ("1y" as const)
      : ("3m" as const),
);
const stockId = computed(() => props.stock.id);
const { prices, chartError: error } = usePriceHistory(
  stockId,
  period,
  chartRange,
  adjustment,
);
const { isFavorite, toggle } = useLibrary();
</script>
<template>
  <aside class="stock-preview" aria-label="个股速览">
    <div class="preview-eyebrow">
      {{ stock.representative ? "龙头股" : "个股速览" }}
    </div>
    <h2>{{ stock.name }}</h2>
    <button
      class="text-button"
      :aria-pressed="isFavorite(stock.ts_code)"
      @click="toggle(stock)"
    >
      {{ isFavorite(stock.ts_code) ? "★ 移除自选" : "☆ 加入自选" }}
    </button>
    <div class="preview-code">{{ stock.code }} · {{ stock.board }}</div>
    <div :class="['preview-price', tone(stock.pct_chg)]">
      {{ price(stock.close) }}
    </div>
    <div :class="['preview-change', tone(stock.pct_chg)]">
      {{ percent(stock.pct_chg) }}
    </div>
    <small class="muted"><QuoteStamp :stock="stock" /></small>
    <div class="preview-chart-heading">
      <span
        >{{
          period === "month"
            ? "近五年"
            : period === "week"
              ? "近一年"
              : "近三个月"
        }}
        · 前复权{{
          period === "day" ? "日" : period === "week" ? "周" : "月"
        }}
        K</span
      ><span>{{ date(stock.quote_date) }}</span>
    </div>
    <div class="preview-period-tabs" role="group" aria-label="速览 K 线周期">
      <button
        v-for="item in [
          ['day', '日 K'],
          ['week', '周 K'],
          ['month', '月 K'],
        ] as const"
        :key="item[0]"
        type="button"
        :aria-pressed="period === item[0]"
        :class="{ active: period === item[0] }"
        @click="period = item[0]"
      >
        {{ item[1] }}
      </button>
    </div>
    <div class="preview-chart-slot" aria-live="polite">
      <p v-if="error" class="chart-message">{{ error }}</p>
      <p v-else-if="!prices" class="muted">正在读取走势…</p>
      <template v-else
        ><CandlestickChart
          :prices="prices"
          :period="period"
          :range="chartRange"
          compact
        />
        <p v-if="prices.message" class="chart-message">
          {{ prices.message }}
        </p></template
      >
    </div>
    <dl class="preview-metrics">
      <div>
        <dt>总市值</dt>
        <dd>{{ money(stock.market_cap) }}</dd>
      </div>
      <div>
        <dt>成交额</dt>
        <dd>{{ money(stock.amount) }}</dd>
      </div>
      <div>
        <dt>SW2021 行业</dt>
        <dd>{{ stock.industry }} · {{ stock.industry_l2 ?? "二级暂缺" }}</dd>
      </div>
      <div>
        <dt>上市时间</dt>
        <dd>{{ date(stock.list_date) }}</dd>
      </div>
    </dl>
    <StockBasics :stock="stock" compact />
    <p v-if="stock.representative" class="muted">
      权重日期 {{ stock.representative.weight_date ?? "来源未提供" }} · 获取
      {{ stock.representative.reviewed_at }}
    </p>
    <h3>{{ stock.representative ? "指数权重依据" : "主营业务" }}</h3>
    <p class="preview-reason">
      {{
        stock.representative?.reason ??
        stock.main_business ??
        "暂无主营业务资料"
      }}
    </p>
    <el-button class="preview-open" @click="emit('open', stock.id)"
      >查看完整资料 ↗</el-button
    >
  </aside>
</template>
<style scoped>
.preview-period-tabs {
  display: flex;
  gap: 4px;
  margin-top: 9px;
}
.preview-period-tabs button {
  padding: 3px 8px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
  font-size: 10px;
  cursor: pointer;
}
.preview-period-tabs button.active {
  border-color: var(--accent);
  color: var(--accent);
  background: #f1f5f8;
}
.preview-period-tabs button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
