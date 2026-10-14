<script setup lang="ts">
import {
  computed,
  onMounted,
  onUnmounted,
  useTemplateRef,
  watch,
  shallowRef,
  nextTick,
} from "vue";
import * as echarts from "echarts/core";
import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { ChainNode, ChainEdge } from "../../api/industryChains";
echarts.use([GraphChart, TooltipComponent, CanvasRenderer]);
const props = defineProps<{
  nodes: ChainNode[];
  edges: ChainEdge[];
  selected: string;
  full: boolean;
  revision: string;
}>();
const emit = defineEmits<{
  select: [key: string];
  edge: [key: string];
  view: [full: boolean];
}>();
const container = useTemplateRef<HTMLDivElement>("canvas"),
  listOnly = shallowRef(window.matchMedia("(max-width:700px)").matches);
const visible = computed(() => props.nodes.filter((n) => props.full || n.main));
const visibleKeys = computed(() => new Set(visible.value.map((n) => n.key)));
const edges = computed(() =>
  props.edges.filter(
    (e) => visibleKeys.value.has(e.source) && visibleKeys.value.has(e.target),
  ),
);
let chart: echarts.ECharts | undefined, observer: ResizeObserver | undefined;
const color: Record<string, string> = {
  供给: "#758cae",
  需求反馈: "#c58b43",
  循环: "#3e9583",
  技术替代: "#9473a6",
};
function stateKey() {
  return "chain-graph:" + props.revision;
}
function saveView() {
  try {
    const series = chart?.getOption().series as {
      zoom?: number;
      center?: number[];
    }[];
    if (series?.[0])
      sessionStorage.setItem(
        stateKey(),
        JSON.stringify({ zoom: series[0].zoom, center: series[0].center }),
      );
  } catch {
    /* view retention is optional */
  }
}
function resetView() {
  try {
    sessionStorage.removeItem(stateKey());
  } catch {
    /* optional retention */
  }
  chart?.dispatchAction({ type: "restore" });
  chart?.setOption({ series: [{ zoom: 1, center: null }] });
  draw();
}
function draw() {
  if (!container.value || !chart) return;
  const byCol = new Map<number, ChainNode[]>();
  for (const n of visible.value) {
    byCol.set(n.column, [...(byCol.get(n.column) ?? []), n]);
  }
  const data = visible.value.map((n) => {
    const col = byCol.get(n.column)!;
    return {
      id: n.key,
      name: n.name,
      x: n.column * 190,
      y: col.indexOf(n) * 100 - (col.length - 1) * 50,
      symbol: "roundRect",
      symbolSize: [132, 58],
      itemStyle: {
        color: n.key === props.selected ? "#e4efff" : "#fff",
        borderColor: n.key === props.selected ? "#2c71e7" : "#c9d5e4",
        borderWidth: n.key === props.selected ? 2 : 1,
      },
      label: {
        show: true,
        color: "#26364c",
        fontSize: 12,
        formatter: () => n.name + "\n" + n.stock_count + " 家 A 股",
      },
    };
  });
  let saved: {} = {};
  try {
    saved = JSON.parse(sessionStorage.getItem(stateKey()) ?? "{}");
  } catch {
    /* optional view */
  }
  chart.setOption({
    animation: false,
    tooltip: { show: false },
    series: [
      {
        type: "graph",
        layout: "none",
        roam: true,
        ...saved,
        data,
        links: edges.value.map((e) => ({
          source: e.source,
          target: e.target,
          key: e.key,
          lineStyle: {
            color: color[e.kind],
            type: e.kind === "需求反馈" ? "dashed" : "solid",
            curveness:
              e.kind === "需求反馈" ? 0.2 : e.kind === "循环" ? 0.28 : 0,
          },
          label: {
            show: e.kind !== "供给",
            formatter: e.kind,
            fontSize: 10,
            color: color[e.kind],
          },
        })),
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: 8,
        lineStyle: { width: 1.4 },
        emphasis: { focus: "adjacency" },
        left: 70,
        right: 70,
        top: 55,
        bottom: 55,
      },
    ],
  });
}
onMounted(() => {
  chart = echarts.init(container.value!);
  chart.on("graphRoam", saveView);
  chart.on("click", (event) => {
    const d = event.data as { id?: string; key?: string };
    if (event.dataType === "edge" && d.key) emit("edge", d.key);
    else if (d.id) emit("select", d.id);
  });
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(container.value!);
  draw();
});
watch([visible, edges, () => props.selected, () => props.revision], draw);
watch(listOnly, async () => {
  await nextTick();
  chart?.resize();
});
onUnmounted(() => {
  saveView();
  observer?.disconnect();
  chart?.dispose();
});
</script>
<template>
  <section class="graph-panel">
    <header>
      <div>
        <h2>产业链图谱</h2>
        <small>箭头表示环节关系 · 拖动平移，滚轮缩放</small>
      </div>
      <div class="tools">
        <el-button size="small" @click="emit('view', !full)">{{
          full ? "查看简明图" : "展开完整图"
        }}</el-button
        ><el-button size="small" @click="listOnly = !listOnly">{{
          listOnly ? "查看图谱" : "节点列表"
        }}</el-button
        ><el-button size="small" @click="resetView">重置视图</el-button>
      </div>
    </header>
    <div
      ref="canvas"
      class="graph-canvas"
      v-show="!listOnly"
      aria-label="产业链关系图，节点与关系列表提供键盘操作"
    />
    <div
      class="node-list"
      :class="{ expanded: listOnly }"
      aria-label="产业链节点"
    >
      <button
        v-for="n in visible"
        :key="n.key"
        :class="{ active: n.key === selected }"
        :aria-pressed="n.key === selected"
        @click="emit('select', n.key)"
      >
        <small>{{ n.stage }}</small
        ><strong>{{ n.name }}</strong
        ><span>{{ n.stock_count }} 家 A 股</span>
      </button>
    </div>
    <p v-if="!full && nodes.some((n) => !n.main)" class="note">
      简明图收起辅助环节；展开完整图可查看全部节点与关系。
    </p>
    <details class="relations">
      <summary>查看关系并解释影响 · {{ edges.length }} 条</summary>
      <button v-for="e in edges" :key="e.key" @click="emit('edge', e.key)">
        {{ nodes.find((n) => n.key === e.source)?.name }} →
        {{ nodes.find((n) => n.key === e.target)?.name }}
        <span>{{ e.kind }}</span>
      </button>
    </details>
  </section>
</template>
<style scoped>
.graph-panel {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: linear-gradient(180deg, #f8fbff, #fff);
}
header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 20px;
  border-bottom: 1px solid var(--line);
}
h2 {
  font-size: 16px;
  margin: 0 0 6px;
}
small,
.note {
  font-size: 11px;
  color: var(--muted);
}
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tools :deep(.el-button + .el-button) {
  margin-left: 0;
}
.graph-canvas {
  height: 370px;
  width: 100%;
  background-image: radial-gradient(#dfe7f0 0.8px, transparent 0.8px);
  background-size: 18px 18px;
}
.node-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 14px;
  border-top: 1px solid var(--line);
}
.node-list button {
  display: flex;
  gap: 8px;
  align-items: center;
  border: 1px solid var(--line);
  background: white;
  border-radius: 4px;
  padding: 7px 10px;
  color: var(--text);
  font-size: 11px;
}
.node-list strong {
  font-size: 12px;
}
.node-list .active {
  background: var(--selection);
  border-color: var(--accent);
}
.expanded {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 22px;
}
.expanded button {
  padding: 14px;
  flex-wrap: wrap;
}
.note {
  padding: 0 14px;
}
.relations {
  padding: 14px;
  border-top: 1px solid var(--line);
  font-size: 12px;
}
.relations summary {
  cursor: pointer;
  color: var(--accent);
}
.relations button {
  display: block;
  background: none;
  border: 0;
  text-align: left;
  padding: 10px 0;
  color: var(--text);
}
.relations span {
  color: var(--muted);
  margin-left: 10px;
}
@media (max-width: 700px) {
  header {
    padding: 14px;
    flex-direction: column;
  }
  .graph-canvas {
    height: 290px;
  }
  .node-list {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .node-list button {
    flex-wrap: wrap;
    text-align: left;
  }
  .node-list span {
    width: 100%;
    color: var(--muted);
  }
  .relations button {
    line-height: 1.7;
  }
}
</style>
