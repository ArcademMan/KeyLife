import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'

// Live polling pattern shared by Keyboard / Hourly / Apps views: every
// flush_interval (min 2s) hit the cheap /summary endpoint and trigger
// `onBump` only when all_time_total has actually advanced. We watch
// all_time_total (DB-backed, bumps on flush) instead of session_total
// (live counter, bumps on every keystroke and would refetch heavy data
// before it's flushed). Skip ticks when the tab is hidden so a
// backgrounded browser stops costing.
export function useLivePoll(onBump: () => void | Promise<void>) {
  const pollSec = ref<number>(60)
  const lastAllTime = ref<number | null>(null)
  let timer: number | undefined

  async function tick(): Promise<void> {
    if (document.hidden) return
    try {
      const s = await api.summary()
      pollSec.value = s.flush_interval_seconds
      const bumped =
        lastAllTime.value !== null && s.all_time_total > lastAllTime.value
      if (bumped) await onBump()
      lastAllTime.value = s.all_time_total
    } catch { /* swallow — retry next tick */ }
  }

  watch(pollSec, (sec) => {
    if (timer) clearInterval(timer)
    timer = window.setInterval(tick, Math.max(sec * 1000, 2000))
  }, { immediate: true })

  function onVisibility(): void { if (!document.hidden) tick() }

  onMounted(() => {
    tick()
    document.addEventListener('visibilitychange', onVisibility)
  })

  onBeforeUnmount(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibility)
  })
}
