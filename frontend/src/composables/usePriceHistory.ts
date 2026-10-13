import { computed, shallowRef, watch, type Ref } from "vue";
import { get, type Prices } from "../api";
import type { CandlePeriod } from "../components/stock/candlePeriods";
import type { ChartRange } from "./useChartPreferences";
export function usePriceHistory(
  id: Ref<number>,
  period: Ref<CandlePeriod>,
  range: Ref<ChartRange>,
  adjustment: Ref<"qfq" | "none">,
) {
  const prices = shallowRef<Prices | null>(null),
    chartError = shallowRef(""),
    revision = shallowRef(0);
  const historyRange = computed<ChartRange>(() =>
    period.value === "month" || range.value === "10y"
      ? "10y"
      : range.value === "5y"
        ? "10y"
        : period.value === "week" || range.value === "3y"
          ? "5y"
          : "1y",
  );
  watch(
    [id, historyRange, adjustment, revision],
    async ([stockId, window, adjust], old, cleanup) => {
      const c = new AbortController();
      let timer: ReturnType<typeof setTimeout> | undefined;
      cleanup(() => {
        c.abort();
        clearTimeout(timer);
      });
      chartError.value = "";
      if (!old || old[0] !== stockId || old[2] !== adjust) prices.value = null;
      async function fetchHistory(attempt = 0) {
        try {
          const result = await get<Prices>(
            `/stocks/${stockId}/prices?range=${window}&adjustment=${adjust}`,
            c.signal,
          );
          if (c.signal.aborted) return;
          if (result.points.length || !prices.value?.points.length)
            prices.value = result;
          else
            prices.value = {
              ...prices.value,
              pending: result.pending,
              stale: true,
              message: result.message,
            };
          if (result.pending && attempt < 60)
            timer = setTimeout(() => fetchHistory(attempt + 1), 3000);
          else if (result.pending) {
            prices.value = { ...prices.value!, pending: false };
            chartError.value = "历史仍在后台处理，请稍后刷新查看。";
          }
        } catch (e) {
          if (!c.signal.aborted)
            chartError.value = e instanceof Error ? e.message : "走势读取失败";
        }
      }
      await fetchHistory();
    },
    { immediate: true },
  );
  return { prices, chartError, retryHistory: () => revision.value++ };
}
