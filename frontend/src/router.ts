import { createRouter, createWebHistory } from "vue-router";
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/market" },
    { path: "/market", component: () => import("./views/MarketView.vue") },
    { path: "/stocks/:id", component: () => import("./views/StockView.vue") },
    { path: "/:pathMatch(.*)*", redirect: "/market" },
  ],
  scrollBehavior(_to, _from, saved) {
    return saved ?? { top: 0 };
  },
});
