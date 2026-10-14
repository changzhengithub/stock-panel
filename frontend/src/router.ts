import { createRouter, createWebHistory } from "vue-router";
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/market" },
    { path: "/market", component: () => import("./views/MarketView.vue") },
    {
      path: "/hot-sectors",
      component: () => import("./views/HotSectorsView.vue"),
    },
    {
      path: "/hot-sectors/:id",
      component: () => import("./views/HotSectorsView.vue"),
    },
    {
      path: "/industry-chains",
      component: () => import("./views/IndustryChainsView.vue"),
    },
    {
      path: "/industry-chains/:id/compare",
      component: () => import("./views/ChainCompareView.vue"),
    },
    {
      path: "/industry-chains/:id",
      component: () => import("./views/IndustryChainsView.vue"),
    },
    { path: "/stocks/:id", component: () => import("./views/StockView.vue") },
    { path: "/:pathMatch(.*)*", redirect: "/market" },
  ],
  scrollBehavior(to, from, saved) {
    if (saved) return saved;
    if (to.path.startsWith("/industry-chains")) {
      if (to.path === from.path) return false;
      try {
        const value = Number(
          sessionStorage.getItem("chain-scroll:" + to.fullPath),
        );
        if (value > 0) return { top: value };
      } catch {
        /* Reading remains available without session storage. */
      }
    }
    return { top: 0 };
  },
});

router.beforeEach((_to, from) => {
  if (from.path.startsWith("/industry-chains")) {
    try {
      sessionStorage.setItem(
        "chain-scroll:" + from.fullPath,
        String(window.scrollY),
      );
    } catch {
      /* optional browsing continuity */
    }
  }
});
