import type { Ref } from "vue";

/** Retain object identity when an API response contains no visible data change. */
export function updateData<T>(target: Ref<T>, next: T) {
  if (JSON.stringify(target.value) !== JSON.stringify(next))
    target.value = next;
}
