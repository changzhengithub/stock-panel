import { computed, shallowRef, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { get, type Stock, type StockResult } from "../api";
import { useLibrary } from "./useLibrary";
import { useChartPreferences } from "./useChartPreferences";
import { usePriceHistory } from "./usePriceHistory";
import { useAutoRefresh } from "./useAutoRefresh";
import { updateData } from "../utils/updateData";
import { browseOrigin } from "../utils/browseOrigin";
export function useStock() {
  const route = useRoute(),
    router = useRouter();
  const stock = shallowRef<Stock | null>(null),
    error = shallowRef(""),
    loading = shallowRef(false),
    revision = shallowRef(0);
  const navigation = shallowRef<StockResult["navigation"]>(),
    navigationError = shallowRef("");
  const { favorites, remember } = useLibrary();
  const { range, period, adjustment } = useChartPreferences();
  const id = computed(() => Number(route.params.id));
  const { prices, chartError, retryHistory } = usePriceHistory(
    id,
    period,
    range,
    adjustment,
  );
  const back = computed(() => browseOrigin(route.query.from));
  const fromChain = computed(() => back.value.startsWith("/industry-chains"));
  const fromHot = computed(() => back.value.startsWith("/hot-sectors"));
  const industryLevel = computed(() =>
    new URLSearchParams(back.value.split("?")[1] ?? "").get(
      "industry_level",
    ) === "2"
      ? 2
      : 1,
  );
  watch(
    [id, industryLevel, revision],
    async (_, __, cleanup) => {
      const c = new AbortController();
      cleanup(() => c.abort());
      const firstView = stock.value?.id !== id.value;
      if (firstView) error.value = "";
      if (stock.value?.id !== id.value) stock.value = null;
      loading.value = !stock.value;
      try {
        for (let attempt = 0; attempt < 4 && !c.signal.aborted; attempt++) {
          const data = await get<Stock>(
            `/stocks/${id.value}?industry_level=${industryLevel.value}`,
            c.signal,
          );
          if (c.signal.aborted) return;
          updateData(stock, data);
          error.value = "";
          loading.value = false;
          if (attempt === 0 && firstView) remember(data);
          if (!data.profile_pending) break;
          await new Promise((resolve) => setTimeout(resolve, 3000));
        }
      } catch (e) {
        if (!c.signal.aborted) {
          if (stock.value) stock.value = { ...stock.value, quote_stale: true };
          else error.value = e instanceof Error ? e.message : "加载失败";
        }
      } finally {
        if (!c.signal.aborted) loading.value = false;
      }
    },
    { immediate: true },
  );
  watch(
    [id, back, favorites],
    async (_, __, cleanup) => {
      const c = new AbortController();
      cleanup(() => c.abort());
      navigation.value = undefined;
      navigationError.value = "";
      if (fromHot.value || fromChain.value) return;
      const params = new URLSearchParams(back.value.split("?")[1] ?? "");
      params.set("neighbor_of", String(id.value));
      params.set("group_by", "none");
      if (params.get("collection") === "recent") params.delete("collection");
      if (params.get("collection") === "favorites")
        params.set("codes", favorites.value.map((s) => s.ts_code).join(","));
      try {
        const result = await get<StockResult>("/stocks?" + params, c.signal);
        if (!c.signal.aborted) navigation.value = result.navigation;
      } catch {
        if (!c.signal.aborted) navigationError.value = "列表顺序暂不可用";
      }
    },
    { immediate: true },
  );
  useAutoRefresh(() => revision.value++);
  function navigate(nextId: number | null | undefined) {
    if (nextId)
      router.replace({
        path: `/stocks/${nextId}`,
        query: { from: back.value },
      });
  }
  return {
    stock,
    prices,
    range,
    period,
    adjustment,
    error,
    chartError,
    loading,
    back,
    fromHot,
    fromChain,
    navigation,
    navigationError,
    navigate,
    retry: () => {
      revision.value++;
      retryHistory();
    },
  };
}
