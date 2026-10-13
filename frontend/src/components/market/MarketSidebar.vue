<script setup lang="ts">
import type { Concept, Filters, Industry } from "../../api";
import ConceptSidebar from "./ConceptSidebar.vue";
import IndustrySidebar from "./IndustrySidebar.vue";
import MarketSelect from "./MarketSelect.vue";

defineProps<{
  filters: Filters;
  level1Industries: Industry[];
  level2Industries: Industry[];
  concepts: Concept[];
}>();
const emit = defineEmits<{ change: [patch: Partial<Filters>] }>();
</script>

<template>
  <aside class="industry-sidebar" aria-label="板块导航">
    <MarketSelect
      class="sidebar-market-select"
      :exchange="filters.exchange"
      :board="filters.board"
      @change="emit('change', $event)"
    />
    <div class="classification-switch" role="group" aria-label="板块分类">
      <button
        :class="{ active: filters.view === 'industry' }"
        :aria-pressed="filters.view === 'industry'"
        @click="emit('change', { view: 'industry' })"
      >
        行业
      </button>
      <button
        :class="{ active: filters.view === 'concept' }"
        :aria-pressed="filters.view === 'concept'"
        @click="emit('change', { view: 'concept' })"
      >
        概念
      </button>
    </div>
    <IndustrySidebar
      v-if="filters.view === 'industry'"
      :level1-industries="level1Industries"
      :level2-industries="level2Industries"
      :selected="filters.industry_id"
      :selected-level="filters.industry_level"
      @change="
        emit('change', { industry_id: $event.id, industry_level: $event.level })
      "
    />
    <ConceptSidebar
      v-else
      :concepts="concepts"
      :selected="filters.concept_id"
      @change="emit('change', { concept_id: $event })"
    />
  </aside>
</template>

<style scoped>
.classification-switch {
  display: flex;
  margin: 10px 14px 0;
  padding: 3px;
  background: #eaf0f8;
  border-radius: 5px;
}
.classification-switch button {
  flex: 1;
  padding: 7px 2px;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
}
.classification-switch button.active {
  background: var(--surface);
  color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px #234b801c;
}
</style>
