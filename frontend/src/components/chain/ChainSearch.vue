<script setup lang="ts">
import { computed } from "vue";
import ChainCoverage from "./ChainCoverage.vue";
import type { ChainCard, Coverage } from "../../api/industryChains";
const props = defineProps<{
  items: ChainCard[];
  loading: boolean;
  error: string;
  active: string;
  coverage: Coverage | null;
  recommendations: ChainCard[];
  total: number;
  page: number;
}>();
const visibleItems = computed(() =>
  props.active && !query.value
    ? props.items.filter((c) => c.id === props.active)
    : props.items,
);
const emit = defineEmits<{ page: [page: number] }>();
const query = defineModel<string>({ required: true });
</script>
<template>
  <section class="chain-search">
    <div class="search-heading">
      <div>
        <span class="eyebrow">行业研究</span>
        <h1>产业链分析</h1>
        <p>从产业结构，读懂经营影响与相关公司。</p>
      </div>
      <el-input
        v-model="query"
        clearable
        placeholder="搜索所有行业：名称、业务关键词或拼音"
        aria-label="搜索产业链"
        class="search-input"
      />
    </div>
    <ChainCoverage :coverage="coverage" />
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-else-if="loading">正在查找分析范围…</p>
    <p v-else-if="!items.length" class="empty">
      该行业尚未收录为独立分析范围，可查看近似名称建议或从全行业目录选择。
    </p>
    <div v-else class="chain-choices" :class="{ compact: active }">
      <RouterLink
        v-for="c in visibleItems"
        :key="c.id"
        :to="{
          path: '/industry-chains/' + c.id,
          query: query ? { search: query } : {},
        }"
        :class="{ chosen: c.id === active }"
        ><strong>{{ c.name }} <span>↗</span></strong
        ><small class="coverage-label">{{
          c.analysis_version >= 2
            ? "行业业务分析 · 分项核验"
            : c.coverage_level === "baseline"
              ? "行业基线 · 关联待核验"
              : "专题资料核验"
        }}</small
        ><small v-if="query">{{ c.match_reason }}</small
        ><template v-if="!active"
          ><p>{{ c.scope }}</p>
          <small
            >{{ c.node_count }} 个环节 · {{ c.stock_count }} 家相关 A 股 ·
            {{ c.verified_count }} 家有节点核验</small
          ></template
        ></RouterLink
      >
    </div>
    <el-pagination
      v-if="total > 24 && (!active || query)"
      class="catalog-pagination"
      :current-page="page"
      :page-size="24"
      :total="total"
      layout="prev, pager, next"
      small
      @current-change="emit('page', $event)"
    />
    <div v-if="recommendations.length" class="recommendations">
      <strong>{{
        items.length ? "相关行业，可继续研究" : "近似名称建议，请确认范围"
      }}</strong>
      <RouterLink
        v-for="r in recommendations"
        :key="r.id"
        :to="'/industry-chains/' + r.id"
        >{{ r.name }} ↗ <small>{{ r.recommendation_reason }}</small></RouterLink
      >
    </div>
    <small v-if="items.length > 1 && query" class="range-note"
      >匹配多个分析范围，请选择要研究的产业链。</small
    >
  </section>
</template>
<style scoped>
.chain-search {
  padding: 24px 22px;
  border-bottom: 1px solid var(--line);
}
.search-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
}
h1 {
  font-size: 26px;
  letter-spacing: -0.6px;
  margin: 5px 0 8px;
}
.search-heading p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.search-input {
  max-width: 400px;
}
.chain-choices {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-top: 22px;
}
.chain-choices a {
  padding: 20px;
  border: 1px solid var(--line);
  background: var(--subtle);
  border-radius: 6px;
}
.chain-choices a:hover,
.chosen {
  border-color: var(--accent) !important;
  background: var(--selection) !important;
}
.chain-choices strong {
  display: flex;
  justify-content: space-between;
  font-size: 17px;
}
.chain-choices p {
  font-size: 13px;
  line-height: 1.8;
  color: var(--muted);
}
.chain-choices small,
.range-note {
  color: var(--muted);
  font-size: 12px;
}
.compact {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16px;
}
.compact a {
  padding: 8px 14px;
}
.compact strong {
  font-size: 13px;
  gap: 12px;
}
.coverage-label {
  display: block;
  margin-top: 6px;
  font-weight: 400;
}
.catalog-pagination {
  margin-top: 16px;
}
.recommendations {
  margin-top: 18px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.recommendations a {
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 10px;
  font-size: 12px;
}
.recommendations small {
  display: block;
  color: var(--muted);
  margin-top: 5px;
}
.range-note {
  display: block;
  margin-top: 12px;
}
.empty {
  padding: 24px;
  color: var(--muted);
}
@media (max-width: 700px) {
  .chain-search {
    padding: 20px 14px;
  }
  .search-heading {
    align-items: stretch;
    flex-direction: column;
    gap: 16px;
  }
  .search-input {
    max-width: none;
  }
  .chain-choices {
    grid-template-columns: 1fr;
  }
  .chain-choices a {
    padding: 16px;
  }
  .compact a {
    padding: 8px 12px;
  }
}
</style>
