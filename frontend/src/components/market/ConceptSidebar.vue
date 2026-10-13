<script setup lang="ts">
import { computed, shallowRef } from "vue";
import type { Concept } from "../../api";
import { featuredConcepts } from "./featuredConcepts";

const props = defineProps<{ concepts: Concept[]; selected: string }>();
const emit = defineEmits<{ change: [id: string] }>();
const keyword = shallowRef("");
const ready = computed(() =>
  props.concepts.filter((concept) => concept.fetched_at),
);
const featured = computed(() => featuredConcepts(ready.value, props.selected));
const visible = computed(() => {
  const query = keyword.value.trim();
  if (query) {
    return props.concepts.filter((concept) => concept.name.includes(query));
  }
  return featured.value;
});
const syncedCount = computed(() => ready.value.length);
function conceptTitle(concept: Concept): string {
  const status =
    concept.error ||
    (concept.fetched_at ? `获取于 ${concept.fetched_at}` : "等待首次成分同步");
  return `${concept.source} · ${status}`;
}
</script>

<template>
  <div class="concept-section">
    <div class="rail-title">
      概念板块<small>可浏览 {{ syncedCount }} 个</small>
    </div>
    <div class="concept-search">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索全部概念"
        aria-label="查找概念"
      />
    </div>
    <div class="concept-mode">
      <span v-if="keyword.trim()">搜索结果 {{ visible.length }} 个</span>
      <span v-else>精选概念 {{ featured.length }} 个</span>
    </div>
    <nav class="industry-nav concept-nav" aria-label="概念板块">
      <button
        class="industry-all"
        :class="{ active: !selected }"
        :aria-pressed="!selected"
        @click="emit('change', '')"
      >
        全部股票
      </button>
      <button
        v-for="concept in visible"
        :key="concept.id"
        :class="{ active: selected === concept.id }"
        :aria-pressed="selected === concept.id"
        :disabled="!concept.fetched_at"
        :title="conceptTitle(concept)"
        @click="emit('change', concept.id)"
      >
        <span class="industry-name">{{ concept.name }}</span>
        <span class="industry-count">{{
          concept.fetched_at
            ? concept.stock_count
            : concept.error
              ? "同步失败"
              : "待同步"
        }}</span>
      </button>
      <p v-if="!visible.length" class="concept-empty">
        {{ concepts.length ? "没有匹配的概念" : "概念数据暂不可用，等待同步" }}
      </p>
    </nav>
  </div>
</template>

<style scoped>
.concept-search {
  padding: 0 14px 12px;
}
.concept-search :deep(.el-input__wrapper) {
  border-radius: 4px;
}
.concept-mode {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px 8px;
  color: var(--muted);
  font-size: 12px;
}
.concept-nav {
  position: static;
  max-height: calc(100vh - 265px);
}
.concept-empty {
  padding: 10px;
  color: var(--muted);
  font-size: 12px;
}
.concept-nav button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
