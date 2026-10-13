<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch, useTemplateRef } from "vue";
import { init, use, type EChartsType } from "echarts/core";
import {
  BarChart,
  CandlestickChart as EChartsCandlestick,
  LineChart,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Prices } from "../../api";
import { date } from "../../utils/format";
import { indicators } from "./indicators";
import { candlePeriods, type CandlePeriod } from "./candlePeriods";

use([
  BarChart,
  EChartsCandlestick,
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);
import {
  useChartPreferences,
  type ChartRange as Range,
} from "../../composables/useChartPreferences";
const props = defineProps<{
  prices: Prices | null;
  compact?: boolean;
  range?: Range;
  period?: CandlePeriod;
}>();
const root = useTemplateRef<HTMLDivElement>("chart");
const { indicator } = useChartPreferences();
const selected = computed({
  get: () => (props.compact ? ("volume" as const) : indicator.value),
  set: (value) => {
    indicator.value = value;
  },
});
const period = computed(() => props.period ?? "day");
const allPoints = computed(() =>
  candlePeriods(
    props.prices?.points ?? [],
    props.prices?.basis_date ?? null,
    period.value,
    props.prices?.start_date ?? null,
  ),
);
const derived = computed(() => indicators(allPoints.value));
const priceLines = [
  { name: "MA5", key: "ma5", color: "#d5922d" },
  { name: "MA10", key: "ma10", color: "#4678bc" },
  { name: "MA20", key: "ma20", color: "#9a6daa" },
  { name: "MA60", key: "ma60", color: "#72818c" },
] as const;

function cutoff(basis: string, range: Range): string {
  const months = { "1m": 1, "3m": 3, "1y": 12, "3y": 36, "5y": 60, "10y": 120 }[
    range
  ];
  const year = Number(basis.slice(0, 4));
  const month = Number(basis.slice(4, 6));
  const day = Number(basis.slice(6, 8));
  const target = new Date(Date.UTC(year, month - 1 - months, 1));
  const lastDay = new Date(
    Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0),
  ).getUTCDate();
  return `${target.getUTCFullYear()}${String(target.getUTCMonth() + 1).padStart(2, "0")}${String(Math.min(day, lastDay)).padStart(2, "0")}`;
}

const indices = computed(() =>
  allPoints.value.flatMap((point, index) =>
    !props.compact ||
    !props.prices?.basis_date ||
    point.date >= cutoff(props.prices.basis_date, props.range ?? "1m")
      ? [index]
      : [],
  ),
);
const initialStart = computed(() => {
  const from = props.prices?.basis_date
    ? cutoff(
        props.prices.basis_date,
        props.range ?? (props.compact ? "1m" : "3m"),
      )
    : "";
  const index = allPoints.value.findIndex((point) => point.date >= from);
  return index < 0 ? 0 : index;
});
let zoom: { start: number; end: number } | null = null;
function resetView() {
  zoom = null;
  render();
}
const points = computed(() =>
  indices.value.map((index) => allPoints.value[index]!),
);
const latestIndex = computed(() => indices.value.at(-1));
const priceAverages = computed(() =>
  priceLines.map((line) => ({
    ...line,
    value:
      latestIndex.value === undefined
        ? null
        : derived.value[line.key][latestIndex.value],
  })),
);
const volumeAverages = computed(() =>
  (
    [
      { name: "VOL MA5", key: "volumeMa5", color: "#d5922d" },
      { name: "VOL MA10", key: "volumeMa10", color: "#4678bc" },
    ] as const
  ).map((line) => ({
    ...line,
    value:
      latestIndex.value === undefined
        ? null
        : derived.value[line.key][latestIndex.value],
  })),
);
const hasCandles = computed(() =>
  points.value.some(
    (point) =>
      point.open !== null &&
      point.high !== null &&
      point.low !== null &&
      point.close !== null,
  ),
);
const hasIndicator = computed(() =>
  indices.value.some((index) =>
    selected.value === "volume"
      ? allPoints.value[index]?.volume !== null &&
        allPoints.value[index]?.volume !== undefined
      : selected.value === "macd"
        ? derived.value.macd[index] !== null
        : derived.value.rsi[index] !== null,
  ),
);
let chartInstance: EChartsType | undefined;
let observer: ResizeObserver | undefined;

function hands(value: number): string {
  return value >= 100000000
    ? `${(value / 100000000).toFixed(2)} 亿手`
    : value >= 10000
      ? `${(value / 10000).toFixed(2)} 万手`
      : `${value.toFixed(0)} 手`;
}

function axisHands(value: number): string {
  return value >= 100000000
    ? `${(value / 100000000).toFixed(1)}亿`
    : value >= 10000
      ? `${(value / 10000).toFixed(1)}万`
      : value.toFixed(0);
}

function tooltip(params: unknown): string {
  const item = Array.isArray(params) ? params[0] : params;
  const index = (item as { dataIndex?: number } | undefined)?.dataIndex;
  const point = index === undefined ? undefined : points.value[index];
  if (!point) return "";
  const label =
    period.value === "day"
      ? date(point.date)
      : period.value === "week"
        ? `周 K ${date(point.periodStart)} ~ ${date(point.periodEnd)}（截至 ${date(point.date)}）`
        : `月 K ${point.periodStart.slice(0, 4)}-${point.periodStart.slice(4, 6)}（截至 ${date(point.date)}）`;
  if (index === undefined) return label;
  if (
    point.open === null ||
    point.high === null ||
    point.low === null ||
    point.close === null
  )
    return `${label}\n${point.issue === "price" ? "周期内有日线缺口，未绘制 K 线" : "暂无 K 线"}`;
  const volume =
    point.volume === null
      ? point.issue === "volume"
        ? "周期内存在缺失，未汇总"
        : "暂无"
      : hands(point.volume);
  const originalIndex = indices.value[index];
  if (originalIndex === undefined) return label;
  const averages = priceLines
    .map((line) => {
      const value = derived.value[line.key][originalIndex];
      return `${line.name} ${value === null ? "不足" : value.toFixed(2)}`;
    })
    .join("  ");
  const indicator =
    selected.value === "macd"
      ? `\nMACD ${derived.value.macd[originalIndex]?.toFixed(3) ?? "不足"}  DIF ${derived.value.dif[originalIndex]?.toFixed(3) ?? "不足"}  DEA ${derived.value.dea[originalIndex]?.toFixed(3) ?? "不足"}`
      : selected.value === "rsi"
        ? `\nRSI(14) ${derived.value.rsi[originalIndex]?.toFixed(2) ?? "不足"}`
        : `\nVOL MA5 ${derived.value.volumeMa5[originalIndex] === null ? "不足" : hands(derived.value.volumeMa5[originalIndex]!)}  VOL MA10 ${derived.value.volumeMa10[originalIndex] === null ? "不足" : hands(derived.value.volumeMa10[originalIndex]!)}`;
  return `${label}\n开 ${point.open.toFixed(2)}  高 ${point.high.toFixed(2)}\n低 ${point.low.toFixed(2)}  收 ${point.close.toFixed(2)}\n${averages}\n成交量 ${volume}${indicator}`;
}

function render() {
  const compact = !!props.compact;
  const xs = points.value.map((point) =>
    period.value === "month"
      ? `${point.date.slice(0, 4)}-${point.date.slice(4, 6)}`
      : date(point.date),
  );
  const colors = points.value.map((point) =>
    point.close !== null && point.open !== null && point.close >= point.open
      ? "#df4249"
      : "#16835c",
  );
  const indicatorSeries =
    selected.value === "volume"
      ? [
          {
            name: "成交量",
            type: "bar" as const,
            xAxisIndex: 1,
            yAxisIndex: 1,
            barMaxWidth:
              period.value === "month"
                ? compact
                  ? 14
                  : 24
                : period.value === "week"
                  ? compact
                    ? 10
                    : 16
                  : compact
                    ? 5
                    : 9,
            data: points.value.map((point, index) =>
              point.volume === null
                ? null
                : { value: point.volume, itemStyle: { color: colors[index] } },
            ),
          },
          ...volumeAverages.value.map((line) => ({
            name: line.name,
            type: "line" as const,
            xAxisIndex: 1,
            yAxisIndex: 1,
            showSymbol: false,
            connectNulls: false,
            lineStyle: { width: 1.4, color: line.color },
            itemStyle: { color: line.color },
            data: indices.value.map((index) => derived.value[line.key][index]),
          })),
        ]
      : selected.value === "macd"
        ? [
            {
              name: "MACD",
              type: "bar" as const,
              xAxisIndex: 1,
              yAxisIndex: 1,
              barMaxWidth: 8,
              data: indices.value.map((index) =>
                derived.value.macd[index] === null
                  ? null
                  : {
                      value: derived.value.macd[index],
                      itemStyle: {
                        color:
                          derived.value.macd[index]! >= 0
                            ? "#df4249"
                            : "#16835c",
                      },
                    },
              ),
            },
            {
              name: "DIF",
              type: "line" as const,
              xAxisIndex: 1,
              yAxisIndex: 1,
              showSymbol: false,
              connectNulls: false,
              lineStyle: { width: 1.5, color: "#d69a29" },
              itemStyle: { color: "#d69a29" },
              data: indices.value.map((index) => derived.value.dif[index]),
            },
            {
              name: "DEA",
              type: "line" as const,
              xAxisIndex: 1,
              yAxisIndex: 1,
              showSymbol: false,
              connectNulls: false,
              lineStyle: { width: 1.5, color: "#5478b9" },
              itemStyle: { color: "#5478b9" },
              data: indices.value.map((index) => derived.value.dea[index]),
            },
          ]
        : [
            {
              name: "RSI(14)",
              type: "line" as const,
              xAxisIndex: 1,
              yAxisIndex: 1,
              showSymbol: false,
              connectNulls: false,
              lineStyle: { width: 1.7, color: "#b87939" },
              itemStyle: { color: "#b87939" },
              data: indices.value.map((index) => derived.value.rsi[index]),
            },
          ];
  chartInstance?.setOption(
    {
      animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      animationDuration: 250,
      grid: compact
        ? [
            { left: 4, right: 4, top: 14, height: 111 },
            { left: 4, right: 4, top: 154, height: 59 },
          ]
        : [
            { left: 62, right: 18, top: 24, height: 272 },
            { left: 62, right: 18, top: 354, height: 108 },
          ],
      dataZoom: compact
        ? []
        : [
            {
              type: "inside",
              xAxisIndex: [0, 1],
              filterMode: "filter",
              zoomOnMouseWheel: true,
              moveOnMouseMove: true,
              ...(zoom ?? {
                startValue: initialStart.value,
                endValue: Math.max(0, points.value.length - 1),
              }),
            },
            {
              type: "slider",
              xAxisIndex: [0, 1],
              bottom: 4,
              height: 18,
              showDetail: false,
              filterMode: "filter",
              ...(zoom ?? {
                startValue: initialStart.value,
                endValue: Math.max(0, points.value.length - 1),
              }),
            },
          ],
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        confine: true,
        formatter: tooltip,
        axisPointer: {
          type: compact ? "line" : "cross",
          label: { show: !compact },
        },
      },
      axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
      xAxis: [0, 1].map((gridIndex) => ({
        type: "category" as const,
        gridIndex,
        data: xs,
        boundaryGap: true,
        show: !compact && gridIndex === 1,
        axisLine: { show: true, lineStyle: { color: "#cbd4dc" } },
        axisTick: { show: true, lineStyle: { color: "#cbd4dc" } },
        axisLabel: {
          color: "#667684",
          fontSize: compact ? 9 : 10,
          hideOverlap: true,
          showMinLabel: true,
          showMaxLabel: true,
          formatter: (value: string) =>
            period.value === "month" ? value : value.slice(5),
        },
      })),
      yAxis: [0, 1].map((gridIndex) => ({
        type: "value" as const,
        gridIndex,
        show: !compact,
        scale: gridIndex === 0 || selected.value === "macd",
        min: gridIndex === 1 && selected.value !== "macd" ? 0 : undefined,
        max: gridIndex === 1 && selected.value === "rsi" ? 100 : undefined,
        splitNumber: compact ? 2 : 4,
        axisLine: { show: true, lineStyle: { color: "#cbd4dc" } },
        axisTick: { show: true, lineStyle: { color: "#cbd4dc" } },
        splitLine: { show: true, lineStyle: { color: "#edf0f4" } },
        axisLabel: {
          color: "#667684",
          fontSize: compact ? 9 : 10,
          formatter:
            gridIndex === 1 && selected.value === "volume"
              ? axisHands
              : gridIndex === 0
                ? (value: number) => value.toFixed(2)
                : (value: number) =>
                    value.toFixed(selected.value === "rsi" ? 0 : 2),
        },
      })),
      series: [
        {
          name: `${period.value === "day" ? "日" : period.value === "week" ? "周" : "月"} K`,
          type: "candlestick",
          xAxisIndex: 0,
          yAxisIndex: 0,
          barMaxWidth:
            period.value === "month"
              ? compact
                ? 16
                : 28
              : period.value === "week"
                ? compact
                  ? 12
                  : 20
                : compact
                  ? 8
                  : 12,
          data: points.value.map((point) =>
            point.open !== null &&
            point.high !== null &&
            point.low !== null &&
            point.close !== null
              ? [point.open, point.close, point.low, point.high]
              : null,
          ),
          itemStyle: {
            color: "#df4249",
            color0: "#16835c",
            borderColor: "#df4249",
            borderColor0: "#16835c",
          },
        },
        ...priceLines.map((line) => ({
          name: line.name,
          type: "line" as const,
          xAxisIndex: 0,
          yAxisIndex: 0,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: compact ? 1.1 : 1.5, color: line.color },
          itemStyle: { color: line.color },
          data: indices.value.map((index) => derived.value[line.key][index]),
        })),
        ...indicatorSeries,
      ],
    },
    true,
  );
}

onMounted(() => {
  if (root.value) {
    chartInstance = init(root.value);
    chartInstance.on("datazoom", (event: any) => {
      const value = event.batch?.[0] ?? event;
      if (typeof value.start === "number")
        zoom = { start: value.start, end: value.end };
    });
    observer = new ResizeObserver(() => chartInstance?.resize());
    observer.observe(root.value);
    render();
  }
});
watch([() => props.prices, () => props.range, () => props.period], resetView);
watch(selected, render);
onUnmounted(() => {
  observer?.disconnect();
  chartInstance?.dispose();
});
</script>

<template>
  <div class="candlestick-slot" :class="{ compact }">
    <div class="price-legend" aria-label="价格均线">
      <span class="axis-title">价格 · 元</span>
      <span
        v-for="line in priceAverages"
        :key="line.key"
        class="average-label"
        :style="{ color: line.color }"
        >{{ line.name }}
        {{ line.value === null ? "—" : line.value.toFixed(2) }}</span
      >
    </div>
    <div class="chart-stage">
      <div
        ref="chart"
        class="candlestick-chart"
        role="img"
        :aria-label="`${prices?.adjustment === 'none' ? '不复权' : '前复权'}历史${period === 'day' ? '日' : period === 'week' ? '周' : '月'} K 线、价格均线和副图指标${compact ? '' : '；横轴为交易日期，纵轴为价格及指标数值'}`"
      ></div>
      <div class="indicator-tabs" :aria-label="compact ? '成交量' : '副图指标'">
        <span v-if="compact" class="indicator-title">成交量 · 手</span>
        <span v-if="compact" class="compact-volume-legend">
          <span
            v-for="line in volumeAverages"
            :key="line.key"
            :style="{ color: line.color }"
            >{{ line.name.replace("VOL ", "") }}</span
          >
        </span>
        <template v-else>
          <button
            v-for="item in [
              ['volume', '成交量 · 手'],
              ['macd', 'MACD'],
              ['rsi', 'RSI'],
            ] as const"
            :key="item[0]"
            type="button"
            :class="{ active: selected === item[0] }"
            :aria-pressed="selected === item[0]"
            :disabled="
              item[0] !== 'volume' &&
              !derived[item[0]].some((value) => value !== null)
            "
            :title="
              item[0] !== 'volume' &&
              !derived[item[0]].some((value) => value !== null)
                ? '当前历史不足，扩大历史范围后再试'
                : undefined
            "
            @click="selected = item[0]"
          >
            {{ item[1] }}
          </button>
        </template>
        <span v-if="selected === 'volume' && !compact" class="volume-legend">
          <span
            v-for="line in volumeAverages"
            :key="line.key"
            :style="{ color: line.color }"
            >{{ line.name }}
            {{ line.value === null ? "—" : axisHands(line.value) }}</span
          >
        </span>
        <span v-else-if="selected === 'macd'" class="study-legend">
          <span style="color: #d69a29">DIF</span>
          <span style="color: #5478b9">DEA</span>
          <span>柱值 = 2 × (DIF − DEA)</span>
        </span>
        <span v-else-if="selected === 'rsi'" class="study-legend">
          <span style="color: #b87939">RSI(14)</span>
        </span>
      </div>
      <div v-if="prices && !hasCandles" class="candlestick-empty">
        K 线数据待补齐
      </div>
      <div
        v-else-if="prices && hasCandles && !hasIndicator"
        class="indicator-empty"
      >
        {{ selected === "volume" ? "成交量待补齐" : "可用历史数据不足" }}
      </div>
    </div>
    <div v-if="!compact" class="axis-caption">
      滚轮缩放 · 拖动平移 · 下方滑块选择区间
      <button class="text-button" @click="resetView">恢复默认视图</button>
    </div>
  </div>
</template>

<style scoped>
.candlestick-slot {
  width: 100%;
}
.price-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 13px;
  min-height: 28px;
  padding-left: 62px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.axis-title {
  color: var(--muted);
  font-weight: 600;
}
.average-label,
.volume-legend span {
  white-space: nowrap;
}
.chart-stage {
  position: relative;
  height: 500px;
}
.compact .price-legend {
  padding-left: 4px;
  gap: 4px 10px;
  font-size: 9px;
}
.compact .chart-stage {
  height: 220px;
}
.candlestick-chart {
  height: 100%;
  width: 100%;
}
.indicator-tabs {
  position: absolute;
  top: 311px;
  left: 62px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px 12px;
  align-items: center;
  height: 25px;
  z-index: 1;
}
.volume-legend {
  display: flex;
  gap: 12px;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}
.study-legend {
  display: flex;
  gap: 10px;
  color: var(--muted);
  font-size: 10px;
}
.axis-caption {
  padding-right: 18px;
  color: var(--muted);
  font-size: 10px;
  text-align: right;
}
.compact-volume-legend {
  display: flex;
  gap: 7px;
  font-size: 9px;
}
.indicator-tabs button {
  border: 0;
  border-radius: 4px;
  padding: 3px 9px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 11px;
}
.indicator-tabs button:hover,
.indicator-tabs button.active {
  color: var(--accent);
  background: #f1f5f8;
}
.indicator-tabs button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.indicator-title {
  color: var(--muted);
  font-size: 10px;
}
.compact .indicator-tabs {
  top: 127px;
  left: 4px;
}
.candlestick-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 12px;
  pointer-events: none;
}
.indicator-empty {
  position: absolute;
  top: 355px;
  bottom: 36px;
  left: 70px;
  right: 30px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 11px;
  pointer-events: none;
}
.compact .indicator-empty {
  top: 155px;
  bottom: 6px;
  left: 4px;
  right: 4px;
}
</style>
