<script setup lang="ts">
import { useRoute } from "vue-router";
import GlobalStockSearch from "./components/market/GlobalStockSearch.vue";
import zhCn from "element-plus/es/locale/lang/zh-cn";
const route = useRoute();
</script>
<template>
  <el-config-provider :locale="zhCn">
    <div class="app-shell">
      <header class="topbar">
        <RouterLink class="brand" to="/market"
          ><span class="brand-mark">观</span>观市<span class="brand-sub"
            >A 股盘后</span
          ></RouterLink
        >
        <nav class="primary-nav" aria-label="主导航">
          <RouterLink
            to="/market"
            :class="{ active: !route.path.startsWith('/stocks') }"
            >市场浏览</RouterLink
          >
          <span v-if="route.path.startsWith('/stocks')" class="active"
            >股票详情</span
          >
        </nav>
        <GlobalStockSearch />
      </header>
      <main class="main-content"><RouterView /></main>
      <footer class="page-footer">
        <span>观市 · 个人市场看板</span
        ><span>龙头股按 SW2021 行业指数权重筛选，非投资评级</span
        ><span class="market-legend"
          >红涨绿跌 <i class="up-dot"></i><i class="down-dot"></i
        ></span>
      </footer>
    </div>
  </el-config-provider>
</template>
