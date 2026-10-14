<script setup lang="ts">
import { computed, shallowRef, watch } from "vue";
import { useIndustryChain } from "../../composables/useIndustryChain";
import { useChainLibrary } from "../../composables/useChainLibrary";
import type { ChainStock } from "../../api/industryChains";
import ChainSearch from "./ChainSearch.vue";
import ChainGraph from "./ChainGraph.vue";
import ChainNodeDetail from "./ChainNodeDetail.vue";
import ChainStockTable from "./ChainStockTable.vue";
import ChainUpdateStatus from "./ChainUpdateStatus.vue";
const {
  route,
  router,
  catalog,
  coverage,
  recommendations,
  catalogTotal,
  detail,
  stocks,
  error,
  stockError,
  searchError,
  loading,
  searchLoading,
  id,
  search,
  selected,
  selectedEdge,
  full,
  scope,
  filters,
  change,
  retry,
  updateStatus,
  refreshError,
  revision,
} = useIndustryChain();
const library = useChainLibrary(),
  selection = shallowRef<number[]>([]),
  selectionError = shallowRef("");
const fullIndustry = computed(() => {
  if (detail.value?.coverage_level !== "curated") return null;
  const industry = coverage.value?.items
    .filter((i) => detail.value!.industry_ids.includes(i.id))
    .sort((a, b) => b.level - a.level)
    .find((i) => i.chains.some((c) => c.coverage_level === "baseline"));
  return industry?.chains.find((c) => c.coverage_level === "baseline") ?? null;
});
const query = computed({
  get: () => search.value,
  set: (v) => {
    void change(
      { search: v, catalog_page: "1", industry_id: undefined },
      false,
    );
  },
});
const currentSaved = computed(() => library.has(id.value)),
  nodeSaved = computed(() => library.has(id.value, selected.value?.key ?? ""));
watch(
  [() => selected.value?.key, scope, () => detail.value?.revision_id],
  () => {
    selection.value = [];
    selectionError.value = "";
  },
);
function save(node = false) {
  if (detail.value)
    library.toggle({
      id: id.value,
      name: detail.value.name,
      node: node ? (selected.value?.key ?? "") : "",
      nodeName: node ? (selected.value?.name ?? "") : "",
    });
}
function selectStock(s: ChainStock) {
  if (selection.value.includes(s.id))
    selection.value = selection.value.filter((x) => x !== s.id);
  else if (selection.value.length < 4)
    selection.value = [...selection.value, s.id];
  else selectionError.value = "最多选择 4 家公司。";
}
function compare() {
  if (!selected.value) return;
  void router.push({
    path: "/industry-chains/" + id.value + "/compare",
    query: {
      ...route.query,
      revision: detail.value?.revision_id,
      node: selected.value.key,
      stock_ids: selection.value.join(","),
      from: route.fullPath,
    },
  });
}
function tableChange(v: Record<string, string | number>) {
  void change(v, !("page" in v));
}
</script>
<template>
  <div class="chain-workspace">
    <ChainSearch
      v-model="query"
      :items="catalog"
      :loading="searchLoading"
      :error="searchError"
      :active="id"
      :coverage="coverage"
      :recommendations="recommendations"
      :total="catalogTotal"
      :page="Number(route.query.catalog_page) || 1"
      @page="change({ catalog_page: $event }, false)"
    />
    <ChainUpdateStatus :status="updateStatus" :error="refreshError" />
    <section v-if="library.saved.value.length" class="saved-bar">
      <small>收藏</small
      ><span v-for="s in library.saved.value" :key="s.id + ':' + s.node"
        ><RouterLink
          :to="{
            path: '/industry-chains/' + s.id,
            query: s.node ? { node: s.node } : {},
          }"
          >{{ s.nodeName || s.name }}</RouterLink
        ><button
          :aria-label="'移除收藏' + (s.nodeName || s.name)"
          @click="library.toggle(s)"
        >
          ×
        </button></span
      >
    </section>
    <p v-if="library.error.value" class="message" role="alert">
      {{ library.error.value }}
    </p>
    <div v-if="error" class="message" role="alert">
      {{ error }} <el-button text @click="retry">重试</el-button>
    </div>
    <p v-if="loading" class="message">正在读取产业链资料…</p>
    <p
      v-if="search && detail && !catalog.some((c) => c.id === id)"
      class="message"
    >
      搜索结果与当前正文范围不同，请选择上方结果进入对应行业。
    </p>
    <section
      v-if="detail && (!search || catalog.some((c) => c.id === id))"
      class="analysis-body"
    >
      <header class="chain-overview">
        <div class="title-line">
          <div>
            <span class="eyebrow">产业链全景 / A 股</span>
            <h2>{{ detail.name }}</h2>
          </div>
          <el-button :aria-pressed="currentSaved" @click="save()">{{
            currentSaved ? "★ 已收藏产业链" : "☆ 收藏产业链"
          }}</el-button>
        </div>
        <p v-if="detail.coverage_level === 'baseline'" class="message">
          行业经营逻辑、供需传导、现金流和竞争维度分别分析；公司业务来自公开资料，匹配或核验状态逐项标注。
        </p>
        <p v-if="fullIndustry" class="scope">
          当前是独立资料专题。<RouterLink
            :to="'/industry-chains/' + fullIndustry.id"
            >进入 {{ fullIndustry.name }} 的全行业体系分析 ↗</RouterLink
          >
        </p>
        <p class="scope">{{ detail.scope }}</p>
        <p class="summary">{{ detail.summary }}</p>
        <div class="overview-grid">
          <div>
            <small>需求来源</small>
            <p>{{ detail.demand }}</p>
          </div>
          <div>
            <small>重点关注</small>
            <p>{{ detail.focus.join(" · ") }}</p>
          </div>
        </div>
        <div class="metadata">
          <span>资料截至 {{ detail.content_as_of }}</span
          ><span>{{ detail.nodes.length }} 个环节</span
          ><span
            >{{ detail.stock_count }} 家相关 A 股 ·
            {{ detail.verified_count }} 家有节点核验</span
          ><span>{{ detail.leader_count }} 家有节点龙头依据</span
          ><span>版本 {{ detail.revision_id.slice(0, 8) }}</span>
        </div>
        <p v-if="revision" class="message">
          {{
            detail.current_revision_id !== detail.revision_id
              ? "当前正在阅读旧版本。"
              : "当前分析版本已固定。"
          }}<el-button text @click="change({ revision: undefined }, false)"
            >跟随最新分析</el-button
          >
        </p>
        <p v-else class="message">
          自动跟随最新分析。<el-button
            text
            @click="change({ revision: detail.revision_id }, false)"
            >固定当前版本</el-button
          >
        </p>
      </header>
      <div class="explore">
        <ChainGraph
          :nodes="detail.nodes"
          :edges="detail.edges"
          :selected="selected?.key ?? ''"
          :full="full"
          :revision="detail.revision_id"
          @select="change({ node: $event, edge: undefined })"
          @edge="change({ edge: $event }, false)"
          @view="change({ view: $event ? 'full' : 'simple' }, false)"
        /><ChainNodeDetail
          :node="selected"
          :edge="selectedEdge"
          :sources="detail.sources"
          :saved="nodeSaved"
          @save="save(true)"
          @close-edge="change({ edge: undefined }, false)"
        />
      </div>
      <p v-if="selectionError" role="alert">{{ selectionError }}</p>
      <ChainStockTable
        :result="stocks"
        :error="stockError"
        :scope="scope"
        :node-name="selected?.name ?? '请选择节点'"
        :from="route.fullPath"
        :selected-ids="selection"
        :filters="filters"
        :sources="detail.sources"
        @change="tableChange"
        @select="selectStock"
        @compare="compare"
        @retry="retry"
      />
      <details class="source-list">
        <summary>
          资料版本与覆盖说明 · {{ detail.sources.length }} 项来源
        </summary>
        <p>{{ detail.change_note }}</p>
        <p>
          核验：{{ detail.reviewer }} ·
          {{ detail.reviewed_at.slice(0, 10) }}。{{ detail.review_note }}
        </p>
        <ul>
          <li v-for="g in detail.gaps" :key="g">{{ g }}</li>
        </ul>
        <div v-for="s in detail.sources" :key="s.id">
          <a :href="s.url" target="_blank" rel="noopener noreferrer"
            >{{ s.title }} ↗</a
          ><small
            >报告期 {{ s.report_period ?? "未注明" }} · 发布
            {{ s.published_on ?? "来源未注明" }} · 取得 {{ s.retrieved_on }} ·
            {{
              s.access_status === "search_verified"
                ? "官方来源检索核对，全文访问受限"
                : "已访问核对"
            }}</small
          >
        </div>
      </details>
    </section>
    <section v-else-if="!id" class="home-note">
      <h2>先理解环节，再判断影响</h2>
      <p>
        从全行业目录或搜索结果选择分析范围，查看上下游的作用、传导条件、公司实际业务和资料依据。行业基线、业务匹配与原始资料核验分别标注。
      </p>
      <div>
        <span>01 明确范围</span><span>02 探索图谱</span><span>03 查证公司</span
        ><span>04 比较与收藏</span>
      </div>
    </section>
  </div>
</template>
<style scoped>
.chain-workspace {
  width: 100%;
  min-width: 0;
}
.analysis-body {
  padding: 24px 22px;
}
.title-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.title-line h2 {
  font-size: 30px;
  letter-spacing: -0.5px;
  margin: 8px 0 0;
}
.scope {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.9;
  margin: 16px 0 6px;
}
.summary {
  font-size: 15px;
  line-height: 1.9;
  max-width: 920px;
  margin: 6px 0 20px;
}
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 28px;
  padding: 18px 0;
  border-top: 1px solid var(--line);
}
.overview-grid small {
  font-size: 11px;
  color: var(--muted);
}
.overview-grid p {
  font-size: 12px;
  line-height: 1.9;
  margin: 6px 0;
}
.metadata {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 11px;
  color: var(--muted);
  padding: 0 0 22px;
}
.explore {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(300px, 1fr);
  gap: 18px;
}
.message {
  padding: 18px 22px;
  font-size: 13px;
  color: var(--muted);
}
.saved-bar {
  padding: 12px 22px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
}
.saved-bar small {
  color: var(--muted);
  margin-right: 8px;
}
.saved-bar span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border: 1px solid var(--line);
  border-radius: 4px;
}
.saved-bar button {
  border: 0;
  background: none;
  color: var(--muted);
}
.source-list {
  margin-top: 24px;
  border-top: 1px solid var(--line);
  padding-top: 20px;
  font-size: 12px;
  line-height: 1.9;
}
.source-list summary {
  color: var(--accent);
  cursor: pointer;
}
.source-list p,
.source-list li {
  color: var(--muted);
}
.source-list div {
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}
.source-list a {
  color: var(--accent);
}
.source-list small {
  display: block;
  color: var(--muted);
  font-size: 11px;
}
.home-note {
  padding: 40px 22px;
  max-width: 820px;
}
.home-note h2 {
  font-size: 22px;
}
.home-note p {
  font-size: 13px;
  line-height: 2;
  color: var(--muted);
}
.home-note div {
  display: flex;
  gap: 24px;
  margin-top: 30px;
  font-size: 12px;
  color: var(--accent);
}
@media (max-width: 900px) {
  .explore {
    grid-template-columns: 1fr;
  }
  .overview-grid {
    gap: 14px;
  }
}
@media (max-width: 700px) {
  .analysis-body {
    padding: 20px 14px;
  }
  .title-line h2 {
    font-size: 26px;
  }
  .overview-grid {
    grid-template-columns: 1fr;
  }
  .metadata {
    gap: 8px 12px;
  }
  .summary {
    font-size: 14px;
  }
  .home-note {
    padding: 24px 14px;
  }
  .home-note div {
    gap: 12px;
    flex-wrap: wrap;
  }
  .saved-bar {
    padding-inline: 14px;
  }
}
</style>
