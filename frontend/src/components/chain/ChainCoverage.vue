<script setup lang="ts">
import { computed } from "vue";
import type { Coverage, IndustryCoverage } from "../../api/industryChains";
const props = defineProps<{ coverage: Coverage | null }>();
const groups = computed(() =>
  (props.coverage?.items ?? [])
    .filter((i) => i.level === 1)
    .map((i) => ({
      ...i,
      children: props.coverage!.items.filter((c) => c.parent_id === i.id),
    })),
);
function target(i: IndustryCoverage) {
  return (
    "/industry-chains/" +
    (i.chains.find((c) => c.coverage_level === "baseline") ?? i.chains[0])?.id
  );
}
</script>
<template>
  <div v-if="coverage" class="coverage">
    <div class="coverage-summary">
      <strong
        >{{ coverage.covered_count }} /
        {{ coverage.total }} 个行业已建立分析范围</strong
      >
      <span
        >专属经营分析 {{ coverage.analysed_count ?? 0 }} /
        {{ coverage.total }} 个行业</span
      >
      <span
        >主营业务 {{ coverage.business_count }} /
        {{ coverage.company_count }} 家</span
      >
      <span
        >目标报告期分部资料 {{ coverage.financial_count }} /
        {{ coverage.company_count }} 家</span
      >
    </div>
    <details class="directory">
      <summary>
        全行业目录与资料覆盖 · {{ coverage.l1_count }} 个一级 /
        {{ coverage.l2_count }} 个二级
      </summary>
      <p class="coverage-note">
        行业分析分别解释经营量价、投入、需求、现金流与竞争维度。公司关联和龙头依据按节点分项核验。资料取得：{{
          coverage.collection?.collected_at.slice(0, 10) ?? "尚未采集"
        }}，目标报告期 {{ coverage.collection?.periods.join("、") ?? "—" }}。
      </p>
      <div class="coverage-groups">
        <details v-for="g in groups" :key="g.id" class="industry-group">
          <summary>
            {{ g.name }}
            <small
              >{{ g.business_count }}/{{ g.company_count }} 家主营 ·
              {{ g.children.length }} 个细分</small
            >
          </summary>
          <RouterLink v-if="g.chains.length" :to="target(g)"
            >查看 {{ g.name }} 一级概览 ↗</RouterLink
          >
          <div v-for="i in g.children" :key="i.id" class="industry-row">
            <RouterLink v-if="i.chains.length" :to="target(i)"
              >{{ i.name }} ↗</RouterLink
            ><span v-else>{{ i.name }}</span>
            <small
              >主营 {{ i.business_count }}/{{ i.company_count }} · 分部
              {{ i.financial_count }}/{{ i.company_count }}</small
            >
            <small>{{ i.status }}</small>
          </div>
        </details>
      </div>
    </details>
  </div>
</template>
<style scoped>
.coverage {
  margin-top: 20px;
  font-size: 12px;
}
.coverage-summary {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  padding: 14px;
  background: var(--subtle);
  border-left: 3px solid var(--accent);
}
.coverage-summary span,
.coverage-note,
.industry-row small {
  color: var(--muted);
}
.directory {
  margin-top: 14px;
}
.directory summary,
.industry-group summary {
  cursor: pointer;
}
.coverage-note {
  line-height: 1.8;
}
.coverage-groups {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
  margin-top: 14px;
}
.industry-group {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
}
.industry-group summary {
  font-weight: 600;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.industry-group summary small {
  font-weight: 400;
  color: var(--muted);
}
.industry-group > a {
  display: block;
  padding: 14px 0 8px;
  color: var(--accent);
}
.industry-row {
  padding: 10px 0;
  border-top: 1px solid var(--line);
  display: grid;
  gap: 5px;
}
.industry-row a {
  color: var(--accent);
}
@media (max-width: 900px) {
  .coverage-groups {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .coverage-groups {
    grid-template-columns: 1fr;
  }
}
</style>
