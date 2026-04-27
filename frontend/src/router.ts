import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
  { path: '/keyboard', name: 'keyboard', component: () => import('./views/KeyboardView.vue') },
  { path: '/calendar', name: 'calendar', component: () => import('./views/CalendarView.vue') },
  { path: '/hourly', name: 'hourly', component: () => import('./views/HourlyView.vue') },
  { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
