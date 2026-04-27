import { ref } from 'vue'
import type { Router } from 'vue-router'

export const navigating = ref(false)

let timer: number | undefined

export function attachNavProgress(router: Router) {
  router.beforeEach((_to, _from, next) => {
    if (timer) window.clearTimeout(timer)
    timer = window.setTimeout(() => { navigating.value = true }, 80)
    next()
  })
  const stop = () => {
    if (timer) { window.clearTimeout(timer); timer = undefined }
    navigating.value = false
  }
  router.afterEach(stop)
  router.onError(stop)
}
