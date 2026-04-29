<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { computed, watch } from 'vue'
import DateRangePicker from './DateRangePicker.vue'
import { navigating } from '../nav-progress'

const route = useRoute()

interface NavItem {
  to: string
  label: string
  icon: string
  subtitle: string
}

const nav: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: '◉', subtitle: 'Overview & today' },
  { to: '/keyboard',  label: 'Keyboard',  icon: '⌨', subtitle: 'Per-key heatmap' },
  { to: '/calendar',  label: 'Calendar',  icon: '▦', subtitle: 'Daily totals over time' },
  { to: '/hourly',    label: 'Hourly',    icon: '◴', subtitle: 'Day × hour heatmap' },
  { to: '/apps',      label: 'Apps',      icon: '◫', subtitle: 'Per-application counts' },
]

const settingsItem: NavItem = {
  to: '/settings', label: 'Settings', icon: '⚙', subtitle: 'Preferences & mappings',
}

const showRange = computed(() =>
  route.path !== '/dashboard' && route.path !== '/settings',
)
const current = computed(() =>
  [...nav, settingsItem].find(n => n.to === route.path),
)

watch(
  current,
  (c) => {
    document.title = c ? `${c.label} • KeyLife` : 'KeyLife'
  },
  { immediate: true },
)
</script>

<template>
  <div class="h-full flex">
    <a href="#main-content" class="skip-link">Skip to content</a>

    <aside
      class="w-56 shrink-0 border-r border-slate-800 bg-slate-900/50 flex flex-col
             hidden md:flex"
      aria-label="Primary navigation"
    >
      <div class="px-5 py-5 flex items-center gap-3 border-b border-slate-800">
        <div class="w-8 h-8 rounded-lg bg-accent grid place-items-center font-bold"
             aria-hidden="true">K</div>
        <div>
          <div class="font-semibold leading-tight">KeyLife</div>
          <div class="text-xs text-slate-400">private telemetry</div>
        </div>
      </div>
      <nav class="p-3 flex flex-col gap-1">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :class="{ 'nav-link-active': route.path === item.to }"
          :aria-current="route.path === item.to ? 'page' : undefined"
        >
          <span class="w-5 text-center text-slate-400" aria-hidden="true">
            {{ item.icon }}
          </span>
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="mt-auto">
        <nav class="p-3 border-t border-slate-800">
          <RouterLink
            :to="settingsItem.to"
            class="nav-link"
            :class="{ 'nav-link-active': route.path === settingsItem.to }"
            :aria-current="route.path === settingsItem.to ? 'page' : undefined"
          >
            <span class="w-5 text-center text-slate-400" aria-hidden="true">
              {{ settingsItem.icon }}
            </span>
            {{ settingsItem.label }}
          </RouterLink>
        </nav>
        <div class="p-4 text-xs text-slate-300 border-t border-slate-800">
          Aggregate counts only.<br>No keystroke order or content stored.
        </div>
      </div>
    </aside>

    <main class="flex-1 overflow-auto">
      <!-- Top progress bar: visible during route navigation -->
      <div
        v-if="navigating"
        class="fixed top-0 left-0 right-0 h-0.5 z-50 overflow-hidden bg-slate-800"
        role="progressbar"
        aria-label="Loading page"
      >
        <div class="h-full w-1/3 bg-accent nav-progress-bar"></div>
      </div>

      <header
        class="sticky top-0 z-10 bg-slate-950/80 backdrop-blur border-b border-slate-800"
      >
        <div class="px-6 lg:px-8 py-4 flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 class="text-lg font-semibold capitalize leading-tight">
              {{ current?.label ?? route.name }}
            </h1>
            <p v-if="current" class="text-xs text-slate-400 mt-0.5">
              {{ current.subtitle }}
            </p>
          </div>
          <DateRangePicker v-if="showRange" />
        </div>
      </header>
      <div
        id="main-content"
        class="p-6 lg:p-8 transition-opacity duration-150"
        :class="navigating ? 'opacity-60' : 'opacity-100'"
        tabindex="-1"
      >
        <slot />
      </div>
    </main>
  </div>
</template>

<style scoped>
@keyframes nav-progress-slide {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}
.nav-progress-bar {
  animation: nav-progress-slide 1s ease-in-out infinite;
}
</style>
