<template>
  <nav class="engine-tabs" aria-label="切换 Agent 引擎">
    <router-link
      v-for="item in engines"
      :key="item.key"
      :to="item.path"
      class="engine-tab"
      :class="{ active: item.key === active }"
      :style="{ '--tab-accent': item.accent }"
    >
      <i></i>
      <span>{{ item.shortLabel }}</span>
    </router-link>
  </nav>
</template>

<script setup>
import { ENGINE_LIST as engines } from '../config/engines'

defineProps({
  active: { type: String, default: 'react' }
})
</script>

<style scoped>
.engine-tabs { display: inline-flex; align-items: center; gap: 4px; padding: 4px; background: rgba(9,15,29,.72); border: 1px solid var(--line); border-radius: 12px; }
.engine-tab { display: flex; align-items: center; gap: 8px; padding: 8px 13px; color: #6f7d96; border-radius: 9px; font-size: 11px; font-weight: 700; letter-spacing: .02em; transition: .2s; }
.engine-tab i { width: 5px; height: 5px; border-radius: 50%; background: var(--tab-accent); opacity: .55; }
.engine-tab:hover { color: var(--text); background: rgba(255,255,255,.04); }
.engine-tab.active { color: #08111b; background: var(--tab-accent); }
.engine-tab.active i { background: #08111b; opacity: .75; }
@media (max-width: 560px) {
  .engine-tabs { width: 100%; justify-content: space-between; }
  .engine-tab { flex: 1; justify-content: center; padding: 8px 6px; }
  .engine-tab span { font-size: 10px; }
}
</style>
