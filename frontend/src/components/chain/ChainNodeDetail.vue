<script setup lang="ts">
import type {
  ChainNode,
  ChainEdge,
  ChainSource,
} from "../../api/industryChains";
import ChainEvidence from "./ChainEvidence.vue";
defineProps<{
  node: ChainNode | null;
  edge: ChainEdge | null;
  sources: ChainSource[];
  saved: boolean;
}>();
const emit = defineEmits<{ save: []; closeEdge: [] }>();
</script>
<template>
  <aside class="node-detail">
    <template v-if="edge"
      ><header>
        <small
          >关系解释 · {{ edge.kind }} ·
          {{ edge.assertion_kind ?? "事实" }}</small
        ><el-button text size="small" @click="emit('closeEdge')"
          >返回节点</el-button
        >
      </header>
      <h2>影响如何传导</h2>
      <p>{{ edge.description }}</p>
      <div class="condition">
        <strong>关系边界</strong>
        <p>{{ edge.conditions }}</p>
      </div>
      <ChainEvidence :evidence="edge.evidence" :sources="sources"
    /></template>
    <template v-else-if="node"
      ><header>
        <small
          >{{ node.stage }} · {{ node.assertion_kind ?? "事实" }} ·
          {{ node.stock_count }} 家可浏览 A 股</small
        ><el-button
          text
          size="small"
          :aria-pressed="saved"
          @click="emit('save')"
          >{{ saved ? "★ 已收藏节点" : "☆ 收藏节点" }}</el-button
        >
      </header>
      <h2>{{ node.name }}</h2>
      <p>{{ node.description }}</p>
      <div class="variable">
        <small>关键观察变量</small><strong>{{ node.variable }}</strong>
      </div>
      <p class="competition">{{ node.competition }}</p>
      <p v-if="node.gap" class="gap">{{ node.gap }}</p>
      <ChainEvidence :evidence="node.evidence" :sources="sources" />
      <article v-for="a in node.analyses" :key="a.id" class="analysis">
        <div class="analysis-label">
          <small>{{ a.kind }}</small
          ><span>{{ a.direction }}影响</span>
        </div>
        <h3>{{ a.trigger }}</h3>
        <p>{{ a.mechanism }}</p>
        <dl>
          <dt>成立条件</dt>
          <dd>{{ a.conditions }}</dd>
          <dt>时间特征</dt>
          <dd>{{ a.horizon }}</dd>
          <dt>验证指标</dt>
          <dd>{{ a.indicators.join("、") }}</dd>
        </dl>
        <ChainEvidence :evidence="a.evidence" :sources="sources" />
      </article>
    </template>
    <p v-else role="status">
      该版本中节点不存在，请重新选择图谱节点。失效收藏不会自动替换为同名节点。
    </p>
  </aside>
</template>
<style scoped>
.node-detail {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 6px;
  max-height: 670px;
  overflow-y: auto;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
header small {
  color: var(--muted);
  font-size: 11px;
}
h2 {
  font-size: 22px;
  margin: 14px 0;
}
p {
  font-size: 13px;
  line-height: 1.9;
  margin: 10px 0;
}
.variable {
  background: var(--subtle);
  padding: 14px;
  border-left: 3px solid var(--accent);
  margin: 18px 0;
}
.variable small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  margin-bottom: 6px;
}
.variable strong {
  font-size: 13px;
}
.competition,
.gap {
  color: var(--muted);
  font-size: 12px;
}
.gap {
  background: #fff9ee;
  padding: 10px;
}
.analysis {
  border-top: 1px solid var(--line);
  margin-top: 22px;
  padding-top: 18px;
}
.analysis-label {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--muted);
}
.analysis-label span {
  padding: 3px 7px;
  background: var(--subtle);
}
h3 {
  font-size: 15px;
  margin: 10px 0;
}
dl {
  font-size: 12px;
  line-height: 1.8;
}
dt {
  color: var(--muted);
  margin-top: 12px;
}
dd {
  margin: 4px 0;
}
.condition {
  background: var(--subtle);
  padding: 14px;
  font-size: 13px;
}
@media (max-width: 700px) {
  .node-detail {
    max-height: none;
    padding: 16px;
  }
}
</style>
