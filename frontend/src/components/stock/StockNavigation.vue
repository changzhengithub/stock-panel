<script setup lang="ts">
import type { Stock, StockResult } from "../../api";
import { useLibrary } from "../../composables/useLibrary";
defineProps<{
  stock: Stock | null;
  navigation: StockResult["navigation"];
  error: string;
  fromHot?: boolean;
}>();
const emit = defineEmits<{ navigate: [id: number | null | undefined] }>();
const { isFavorite, toggle, storageError } = useLibrary();
</script>
<template>
  <div class="stock-navigation">
    <el-button
      v-if="!fromHot"
      :disabled="!navigation?.previous_id"
      @click="emit('navigate', navigation?.previous_id)"
      >← 上一只</el-button
    >
    <span v-if="!fromHot">{{
      error ||
      (navigation?.position
        ? `${navigation.position} / ${navigation.total}`
        : "不在当前列表中")
    }}</span>
    <el-button
      v-if="!fromHot"
      :disabled="!navigation?.next_id"
      @click="emit('navigate', navigation?.next_id)"
      >下一只 →</el-button
    >
    <el-button
      v-if="stock"
      :aria-pressed="isFavorite(stock.ts_code)"
      @click="toggle(stock)"
      >{{ isFavorite(stock.ts_code) ? "★ 移除自选" : "☆ 加入自选" }}</el-button
    >
    <small v-if="storageError" role="alert">{{ storageError }}</small>
  </div>
</template>
<style scoped>
.stock-navigation {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 14px 0;
  color: var(--muted);
  font-size: 12px;
}
.stock-navigation :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
