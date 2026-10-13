<script setup lang="ts">
import { computed, shallowRef, watch, onUnmounted } from "vue";
import type { Concept, Filters, Industry } from "../../api";
import { featuredConcepts } from "./featuredConcepts";
const props = defineProps<{
  filters: Filters;
  level1Industries: Industry[];
  level2Industries: Industry[];
  concepts: Concept[];
}>();
const emit = defineEmits<{ change: [patch: Partial<Filters>] }>();
const keyword = shallowRef(props.filters.keyword);
const conceptQuery = shallowRef("");
const childrenByParent = computed(() => {
  const groups = new Map<string, Industry[]>();
  for (const industry of props.level2Industries) {
    if (!industry.parent_id) continue;
    const children = groups.get(industry.parent_id) ?? [];
    children.push(industry);
    groups.set(industry.parent_id, children);
  }
  return groups;
});
const unclassifiedLevel2 = computed(() =>
  props.level2Industries.find((industry) => industry.id === "unclassified-l2"),
);
const availableConcepts = computed(() =>
  props.concepts.filter((concept) => concept.fetched_at),
);
const visibleConcepts = computed(() => {
  const query = conceptQuery.value.trim();
  return query
    ? availableConcepts.value.filter((concept) => concept.name.includes(query))
    : featuredConcepts(availableConcepts.value, props.filters.concept_id);
});
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => props.filters.keyword,
  (value) => {
    clearTimeout(timer);
    keyword.value = value;
  },
);
function search(value: string) {
  keyword.value = value;
  clearTimeout(timer);
  timer = setTimeout(() => emit("change", { keyword: value }), 300);
}
function selectIndustry(id: string) {
  const level = props.level2Industries.some((industry) => industry.id === id)
    ? 2
    : 1;
  emit("change", {
    industry_id: id,
    industry_level: level,
  });
}
function selectConcept(id: string) {
  conceptQuery.value = "";
  emit("change", { concept_id: id });
}
function filterConcepts(query: string) {
  conceptQuery.value = query;
}
function conceptDropdownVisible(visible: boolean) {
  if (!visible) conceptQuery.value = "";
}
onUnmounted(() => clearTimeout(timer));
</script>
<template>
  <section class="filters" aria-label="股票筛选">
    <div
      class="mobile-classification-switch"
      role="group"
      aria-label="板块分类"
    >
      <button
        :class="{ selected: filters.view === 'industry' }"
        :aria-pressed="filters.view === 'industry'"
        @click="emit('change', { view: 'industry' })"
      >
        行业
      </button>
      <button
        :class="{ selected: filters.view === 'concept' }"
        :aria-pressed="filters.view === 'concept'"
        @click="emit('change', { view: 'concept' })"
      >
        概念
      </button>
    </div>
    <div class="filter-row filter-controls">
      <label class="filter-field search-field"
        >筛选当前列表<el-input
          :model-value="keyword"
          @update:model-value="search"
          clearable
          placeholder="代码 / 名称"
          autocomplete="off"
          :spellcheck="false"
          aria-label="股票搜索"
          ><template #prefix>⌕</template></el-input
        ></label
      >
      <div class="sort-options" role="group" aria-label="排序和龙头股筛选">
        <button
          type="button"
          :class="{ selected: filters.sort === 'default' }"
          :aria-pressed="filters.sort === 'default'"
          @click="emit('change', { sort: 'default' })"
        >
          默认
        </button>
        <button
          v-if="filters.view === 'industry'"
          type="button"
          class="representative-filter"
          :class="{ selected: filters.scope === 'representatives' }"
          :aria-pressed="filters.scope === 'representatives'"
          @click="
            emit('change', {
              scope:
                filters.scope === 'representatives' ? 'all' : 'representatives',
            })
          "
        >
          龙头股
        </button>
        <button
          v-for="option in [
            { key: 'pct_desc', label: '涨跌幅降序' },
            { key: 'pct_asc', label: '涨跌幅升序' },
            { key: 'market_cap_desc', label: '总市值' },
          ]"
          :key="option.key"
          :class="{ selected: filters.sort === option.key }"
          :aria-pressed="filters.sort === option.key"
          @click="emit('change', { sort: option.key as Filters['sort'] })"
        >
          {{ option.label }}
        </button>
      </div>
    </div>
    <div class="filter-row industry-filter-row">
      <label
        v-if="filters.view === 'industry'"
        class="filter-field industry-dropdown"
        >行业<el-select
          :model-value="filters.industry_id"
          @update:model-value="selectIndustry($event)"
          filterable
          aria-label="行业"
          placeholder="全部行业"
        >
          <el-option label="全部行业" value="" />
          <el-option-group
            v-for="parent in level1Industries"
            :key="parent.id"
            :label="parent.name"
          >
            <el-option
              :value="parent.id"
              :label="`${parent.name} · ${parent.stock_count}`"
            />
            <el-option
              v-for="child in childrenByParent.get(parent.id) ?? []"
              :key="child.id"
              :value="child.id"
              :label="`　↳ ${child.name} · ${child.stock_count}`"
            />
          </el-option-group>
          <el-option
            v-if="unclassifiedLevel2"
            :value="unclassifiedLevel2.id"
            :label="`未细分 · ${unclassifiedLevel2.stock_count}`"
          /> </el-select
      ></label>
      <label v-else class="filter-field industry-dropdown"
        >概念<el-select
          :model-value="filters.concept_id"
          @update:model-value="selectConcept($event)"
          filterable
          :filter-method="filterConcepts"
          @visible-change="conceptDropdownVisible"
          aria-label="概念"
          placeholder="全部概念"
        >
          <el-option label="全部概念" value="" />
          <el-option
            v-for="concept in visibleConcepts"
            :key="concept.id"
            :value="concept.id"
            :label="`${concept.name} · ${concept.stock_count}`"
          /> </el-select
      ></label>
    </div>
  </section>
</template>
