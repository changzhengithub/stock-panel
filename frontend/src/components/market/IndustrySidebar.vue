<script setup lang="ts">
import { computed, shallowRef, watch } from "vue";
import type { Industry } from "../../api";

const props = defineProps<{
  level1Industries: Industry[];
  level2Industries: Industry[];
  selected: string;
  selectedLevel: 1 | 2;
}>();
const emit = defineEmits<{
  change: [selection: { id: string; level: 1 | 2 }];
}>();
const expandedId = shallowRef("");
const count = computed(() =>
  props.level1Industries.reduce(
    (total, industry) => total + industry.stock_count,
    0,
  ),
);
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
const selectedParentId = computed(() =>
  props.selectedLevel === 1
    ? ""
    : (props.level2Industries.find((industry) => industry.id === props.selected)
        ?.parent_id ?? ""),
);
const unclassifiedLevel2 = computed(() =>
  props.level2Industries.find((industry) => industry.id === "unclassified-l2"),
);
watch(
  () => [props.selected, props.selectedLevel, selectedParentId.value] as const,
  () => {
    if (!props.selected) return;
    if (props.selectedLevel === 1) {
      expandedId.value = props.selected;
      return;
    }
    if (selectedParentId.value) expandedId.value = selectedParentId.value;
  },
  { immediate: true },
);
function selectIndustry(id: string, level: 1 | 2) {
  emit("change", { id, level });
}
function selectParent(id: string) {
  if (props.selectedLevel === 1 && props.selected === id) {
    expandedId.value = expandedId.value === id ? "" : id;
    return;
  }
  expandedId.value = id;
  emit("change", { id, level: 1 });
}
</script>

<template>
  <div class="industry-section">
    <div class="rail-title">行业板块<small>SW2021 · 一级 / 二级</small></div>
    <nav class="industry-nav" aria-label="SW2021 行业分类">
      <button
        class="industry-all"
        :class="{ active: !selected }"
        :aria-pressed="!selected"
        @click="emit('change', { id: '', level: 1 })"
      >
        全部行业<span>{{ count.toLocaleString() }}</span>
      </button>
      <div
        v-for="industry in level1Industries"
        :key="industry.id"
        class="industry-tree-group"
      >
        <button
          class="industry-parent-select"
          :class="{
            active: selectedLevel === 1 && selected === industry.id,
            'has-selected-child': selectedParentId === industry.id,
          }"
          :aria-pressed="selectedLevel === 1 && selected === industry.id"
          :aria-expanded="
            childrenByParent.get(industry.id)?.length
              ? expandedId === industry.id
              : undefined
          "
          :aria-controls="
            expandedId === industry.id &&
            childrenByParent.get(industry.id)?.length
              ? `industry-children-${industry.id}`
              : undefined
          "
          @click="selectParent(industry.id)"
        >
          <span class="industry-name">{{ industry.name }}</span>
          <span class="industry-parent-meta">
            <span class="industry-count">{{ industry.stock_count }}</span>
            <span
              v-if="childrenByParent.get(industry.id)?.length"
              class="industry-chevron"
              aria-hidden="true"
            >
              <svg viewBox="0 0 16 16" focusable="false">
                <path d="m4 6 4 4 4-4" />
              </svg>
            </span>
          </span>
        </button>
        <div
          v-if="
            expandedId === industry.id &&
            childrenByParent.get(industry.id)?.length
          "
          :id="`industry-children-${industry.id}`"
          class="industry-children"
          role="group"
          :aria-label="`${industry.name}二级行业`"
        >
          <button
            v-for="child in childrenByParent.get(industry.id)"
            :key="child.id"
            class="industry-child-select"
            :class="{ active: selectedLevel === 2 && selected === child.id }"
            :aria-pressed="selectedLevel === 2 && selected === child.id"
            @click="selectIndustry(child.id, 2)"
          >
            <span class="industry-name">{{ child.name }}</span>
            <span class="industry-count">{{ child.stock_count }}</span>
          </button>
        </div>
      </div>
      <button
        v-if="unclassifiedLevel2"
        class="industry-unclassified-l2"
        :class="{
          active: selectedLevel === 2 && selected === unclassifiedLevel2.id,
        }"
        :aria-pressed="
          selectedLevel === 2 && selected === unclassifiedLevel2.id
        "
        @click="selectIndustry(unclassifiedLevel2.id, 2)"
      >
        未细分<span>{{ unclassifiedLevel2.stock_count }}</span>
      </button>
    </nav>
  </div>
</template>
