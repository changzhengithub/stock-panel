<script setup lang="ts">
import { computed, onMounted, onUnmounted, useTemplateRef, watch } from "vue";
import { init, use, type EChartsType } from "echarts/core";
import { BarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { FundDay } from "../../api/fundFlow";
import { money } from "../../utils/format";
use([
  BarChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
]);
const props = defineProps<{ items: FundDay[] }>();
const element = useTemplateRef<HTMLDivElement>("plot");
let chart: EChartsType | undefined, observer: ResizeObserver | undefined;
const signature = computed(() => JSON.stringify(props.items));
function draw() {
  chart?.setOption({
    xAxis: {
      type: "category",
      data: props.items.map(
        (r) =>
          `${r.trade_date.slice(4, 6)}-${r.trade_date.slice(6)}${r.provisional ? "*" : ""}`,
      ),
      axisLine: { lineStyle: { color: "#dce4ef" } },
      axisLabel: { color: "#758499", fontSize: 10 },
    },
    series: [
      {
        type: "bar",
        name: "每日主力净流入",
        data: props.items.map((r) => ({
          value: r.net_amount,
          itemStyle: {
            color:
              r.net_amount != null && r.net_amount < 0 ? "#16835c" : "#df4249",
            opacity: r.provisional ? 0.55 : 1,
          },
        })),
        barMaxWidth: 18,
        markLine: {
          silent: true,
          symbol: "none",
          data: [{ yAxis: 0 }],
          label: { show: false },
          lineStyle: { color: "#b6c3d4", type: "solid" },
        },
      },
    ],
  });
}
onMounted(() => {
  if (!element.value) return;
  chart = init(element.value);
  chart.setOption({
    animation: false,
    xAxis: { type: "category", data: [] },
    series: [{ type: "bar", data: [] }],
    grid: { left: 68, right: 16, top: 14, bottom: 58 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) =>
        money(value == null ? null : Number(value)),
    },
    yAxis: {
      type: "value",
      axisLabel: {
        formatter: (v: number) => money(v),
        color: "#758499",
        fontSize: 10,
      },
      splitLine: { lineStyle: { color: "#eff3f8" } },
    },
    dataZoom: [
      { type: "inside" },
      { type: "slider", height: 16, bottom: 4, borderColor: "#e7ecf3" },
    ],
  });
  draw();
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(element.value);
});
watch(signature, draw);
onUnmounted(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>
<template>
  <div
    ref="plot"
    class="fund-plot"
    role="img"
    aria-label="每日主力净流入柱状图，红色流入、绿色流出，可缩放"
  />
</template>
<style scoped>
.fund-plot {
  width: 100%;
  height: 255px;
}
</style>
