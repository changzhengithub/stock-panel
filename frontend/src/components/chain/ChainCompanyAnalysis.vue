<script setup lang="ts">
defineProps<{ messages: string[] }>();
</script>
<template>
  <details v-if="messages.length" class="company-analysis">
    <summary>业务关联与经营解读</summary>
    <ul>
      <li v-for="(message, index) in messages" :key="index">{{ message }}</li>
    </ul>
  </details>
</template>
<style scoped>
.company-analysis {
  margin: 10px 0;
  font-size: 12px;
  color: var(--muted);
}
.company-analysis summary {
  color: var(--accent);
  cursor: pointer;
}
.company-analysis ul {
  padding-left: 18px;
  margin: 8px 0;
}
.company-analysis li {
  margin: 8px 0;
  line-height: 1.8;
}
</style>
