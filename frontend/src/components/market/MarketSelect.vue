<script setup lang="ts">
import { computed } from "vue";
import {
  MARKET_OPTIONS,
  boardsForExchange,
  type Exchange,
} from "../../marketOptions";

const props = defineProps<{ exchange: Exchange; board: string }>();
const emit = defineEmits<{
  change: [scope: { exchange: Exchange; board: string }];
}>();
const groups = MARKET_OPTIONS.filter(
  (option) => option.value === "SSE" || option.value === "SZSE",
);
const selected = computed(() => props.board || props.exchange);
function select(value: string) {
  const market = MARKET_OPTIONS.find((option) => option.value === value);
  if (market) {
    emit("change", { exchange: market.value, board: "" });
    return;
  }
  const parent = groups.find((option) =>
    boardsForExchange(option.value).includes(value),
  );
  if (parent) emit("change", { exchange: parent.value, board: value });
}
</script>

<template>
  <div class="market-select">
    <span>市场</span>
    <el-select
      :model-value="selected"
      :empty-values="[null, undefined]"
      size="large"
      popper-class="market-select-dropdown"
      aria-label="市场范围"
      @update:model-value="select"
    >
      <el-option label="全部 A 股" value="" />
      <el-option-group
        v-for="group in groups"
        :key="group.value"
        :label="group.label"
      >
        <el-option :label="group.label" :value="group.value"
          >全部{{ group.label }}</el-option
        >
        <el-option
          v-for="board in boardsForExchange(group.value)"
          :key="board"
          :label="board"
          :value="board"
        />
      </el-option-group>
      <el-option label="北交所" value="BSE" />
    </el-select>
  </div>
</template>
