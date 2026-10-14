<script setup lang="ts">
import { computed } from "vue";
import type { FundChartBoard, FundKind, FundPeriod } from "../../api/fundFlow";
import { periodLabels } from "../../api/fundFlow";
import { money } from "../../utils/format";
import { signedMoney } from "./fundFormat";
const props = defineProps<{
  chart: { inflows: FundChartBoard[]; outflows: FundChartBoard[] };
  kind: FundKind;
  period: FundPeriod;
  selected: string;
}>();
const emit = defineEmits<{ select: [id: string] }>();
const count = defineModel<5 | 10>("count", { default: 5 });
const inflows = computed(() => props.chart.inflows.slice(0, count.value));
const outflows = computed(() => props.chart.outflows.slice(0, count.value));
const maximum = computed(() =>
  Math.max(
    1,
    ...[...inflows.value, ...outflows.value].map((row) =>
      Math.abs(row.net_amount ?? 0),
    ),
  ),
);
const ticks = computed(() =>
  [-1, -0.5, 0, 0.5, 1].map((factor) => money(factor * maximum.value)),
);
function barStyle(row: FundChartBoard) {
  const amount = row.net_amount ?? 0;
  const width = (Math.abs(amount) / maximum.value) * 50;
  return { left: `${amount < 0 ? 50 - width : 50}%`, width: `${width}%` };
}
</script>
<template>
  <section class="sector-flow-chart" aria-label="热门板块资金流入流出图表">
    <div class="flow-chart-heading">
      <div>
        <h2>板块资金流入流出</h2>
        <p>
          全部{{ kind === "concept" ? "概念" : "行业" }} ·
          {{ periodLabels[period] }}主力净额 · 两侧统一金额刻度
        </p>
      </div>
      <el-radio-group v-model="count" size="small" aria-label="图表板块数量"
        ><el-radio-button :value="5">各前5</el-radio-button
        ><el-radio-button :value="10">各前10</el-radio-button></el-radio-group
      >
    </div>
    <div class="chart-legend">
      <span class="out-dot" />净流出向左<span class="in-dot" />净流入向右<small
        >点击板块查看详情</small
      >
    </div>
    <template v-if="inflows.length || outflows.length">
      <div class="flow-axis">
        <span>板块</span>
        <div class="axis-ticks">
          <span v-for="(tick, index) in ticks" :key="index">{{
            index === 2 ? "0" : tick
          }}</span>
        </div>
        <span class="amount-caption">主力净额</span>
      </div>
      <div class="flow-group">
        <h3>
          净流入前列 <small>{{ inflows.length }} 个板块</small>
        </h3>
        <button
          v-for="row in inflows"
          :key="row.id"
          class="flow-row inflow-row"
          :class="{ selected: row.id === selected }"
          :aria-pressed="row.id === selected"
          :aria-label="`净流入 ${row.name} ${signedMoney(row.net_amount)}`"
          :title="`${row.name} · ${signedMoney(row.net_amount)}`"
          @click="emit('select', row.id)"
        >
          <span class="flow-name">{{ row.name }}</span
          ><span class="flow-track"
            ><span class="zero-line" /><span
              class="flow-bar"
              :style="barStyle(row)" /></span
          ><span class="flow-amount">{{ signedMoney(row.net_amount) }}</span>
        </button>
        <p v-if="!inflows.length" class="empty-side">当前批次暂无净流入板块</p>
      </div>
      <div class="flow-group">
        <h3>
          净流出前列 <small>{{ outflows.length }} 个板块</small>
        </h3>
        <button
          v-for="row in outflows"
          :key="row.id"
          class="flow-row outflow-row"
          :class="{ selected: row.id === selected }"
          :aria-pressed="row.id === selected"
          :aria-label="`净流出 ${row.name} ${signedMoney(row.net_amount)}`"
          :title="`${row.name} · ${signedMoney(row.net_amount)}`"
          @click="emit('select', row.id)"
        >
          <span class="flow-name">{{ row.name }}</span
          ><span class="flow-track"
            ><span class="zero-line" /><span
              class="flow-bar"
              :style="barStyle(row)" /></span
          ><span class="flow-amount">{{ signedMoney(row.net_amount) }}</span>
        </button>
        <p v-if="!outflows.length" class="empty-side">当前批次暂无净流出板块</p>
      </div>
    </template>
    <el-empty
      v-else
      description="暂无有效的板块净流入或净流出数据"
      :image-size="55"
    />
    <p class="chart-scope">
      展示完整批次的流入、流出前列，不随下方列表搜索、排序或分页改变。净额不等同总买入／总卖出，不合计重叠板块资金。
    </p>
  </section>
</template>
<style scoped>
.sector-flow-chart {
  margin-top: 24px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 20px 22px 14px;
  background: var(--surface);
}
.flow-chart-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
}
.flow-chart-heading h2 {
  margin: 0;
  font-size: 15px;
}
.flow-chart-heading p {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--muted);
}
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--muted);
  margin: 16px 0 22px;
}
.chart-legend small {
  margin-left: auto;
  font-size: 11px;
}
.out-dot,
.in-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.out-dot {
  background: var(--down);
}
.in-dot {
  background: var(--up);
  margin-left: 12px;
}
.flow-axis,
.flow-row {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr) 104px;
  align-items: center;
  gap: 12px;
}
.flow-axis {
  font-size: 10px;
  color: var(--muted);
  padding: 0 10px 12px;
  border-bottom: 1px solid var(--line);
}
.axis-ticks {
  position: relative;
  height: 14px;
  font-variant-numeric: tabular-nums;
}
.axis-ticks span {
  position: absolute;
  white-space: nowrap;
  transform: translateX(-50%);
}
.axis-ticks span:nth-child(1) {
  left: 0;
  transform: none;
}
.axis-ticks span:nth-child(2) {
  left: 25%;
}
.axis-ticks span:nth-child(3) {
  left: 50%;
  color: var(--text);
}
.axis-ticks span:nth-child(4) {
  left: 75%;
}
.axis-ticks span:nth-child(5) {
  left: 100%;
  transform: translateX(-100%);
}
.amount-caption {
  text-align: right;
}
.flow-group h3 {
  font-size: 11px;
  color: var(--muted);
  font-weight: 500;
  margin: 14px 10px 6px;
}
.flow-group h3 small {
  font-size: 10px;
  margin-left: 8px;
}
.flow-row {
  width: 100%;
  min-height: 32px;
  padding: 5px 10px;
  border: 0;
  border-radius: 3px;
  background: transparent;
  text-align: left;
  color: var(--text);
}
.flow-row:hover {
  background: var(--subtle);
}
.flow-row.selected {
  background: var(--selection);
}
.flow-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.selected .flow-name {
  color: var(--accent);
  font-weight: 600;
}
.flow-track {
  position: relative;
  height: 22px;
  background: linear-gradient(
    to right,
    transparent calc(25% - 0.5px),
    var(--line) 25%,
    transparent calc(25% + 0.5px),
    transparent calc(75% - 0.5px),
    var(--line) 75%,
    transparent calc(75% + 0.5px)
  );
}
.zero-line {
  position: absolute;
  top: -5px;
  bottom: -5px;
  width: 1px;
  left: 50%;
  background: #a7b8cf;
}
.flow-bar {
  position: absolute;
  top: 4px;
  height: 14px;
  border-radius: 2px;
  min-width: 1px;
}
.inflow-row .flow-bar {
  background: var(--up);
}
.outflow-row .flow-bar {
  background: var(--down);
}
.flow-amount {
  text-align: right;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.inflow-row .flow-amount {
  color: var(--up);
}
.outflow-row .flow-amount {
  color: var(--down);
}
.chart-scope,
.empty-side {
  font-size: 10px;
  line-height: 1.8;
  color: var(--muted);
  margin: 14px 0 0;
}
.empty-side {
  margin: 10px;
}
@media (max-width: 600px) {
  .sector-flow-chart {
    padding: 16px 10px 12px;
  }
  .flow-axis,
  .flow-row {
    grid-template-columns: 80px minmax(0, 1fr) 74px;
    gap: 6px;
  }
  .flow-axis,
  .flow-row {
    padding-inline: 4px;
  }
  .flow-name,
  .flow-amount {
    font-size: 11px;
  }
  .axis-ticks span:nth-child(2),
  .axis-ticks span:nth-child(4) {
    display: none;
  }
  .axis-ticks {
    font-size: 9px;
  }
  .chart-legend {
    margin-bottom: 18px;
  }
  .chart-legend small {
    flex-basis: 100%;
    margin-left: 0;
  }
}
</style>
