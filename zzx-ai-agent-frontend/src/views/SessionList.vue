<template>
  <main class="session-page" :class="themeClass">
    <div class="page-glow"></div>
    <header class="session-nav">
      <button class="back-btn" @click="goHome">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15 18-6-6 6-6"/></svg>
        <span>工作台</span>
      </button>
      <div class="mini-brand"><span class="mini-mark">{{ isLoveMaster ? '♥' : 'Z' }}</span><span>{{ isLoveMaster ? 'Love Advisor' : 'Super Agent' }}</span></div>
      <span class="agent-online"><i></i>ONLINE</span>
    </header>

    <section class="session-shell">
      <div class="session-hero">
        <div>
          <span class="eyebrow">{{ isLoveMaster ? 'EMOTIONAL INTELLIGENCE' : 'AUTONOMOUS REASONING' }}</span>
          <h1>{{ isLoveMaster ? '继续聊聊近况' : '继续推进任务' }}</h1>
          <p>{{ isLoveMaster ? '每段对话都值得被认真记住。' : '从历史上下文接续，让思考和执行不中断。' }}</p>
        </div>
        <button class="new-btn" @click="handleNewSession">
          <span class="plus">+</span>
          <span>新建对话</span>
        </button>
      </div>

      <div class="list-meta">
        <span>最近对话</span>
        <span>{{ loading ? '同步中…' : sessions.length + ' 个会话' }}</span>
      </div>

      <div class="session-list" v-if="sessions.length > 0">
        <article v-for="s in sessions" :key="s.session_id" class="session-card" @click="goToChat(s)">
          <div class="session-icon">
            <svg v-if="!isLoveMaster" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 7.5A2.5 2.5 0 0 1 7.5 5h9A2.5 2.5 0 0 1 19 7.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 3v-3A2.5 2.5 0 0 1 4 13.5v-6Z"/><path d="M8 10h8M8 13h5"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20S4.5 15.7 4.5 9.4A4.4 4.4 0 0 1 12 6.3a4.4 4.4 0 0 1 7.5 3.1C19.5 15.7 12 20 12 20Z"/></svg>
          </div>
          <div class="session-card-info">
            <div v-if="editingId !== s.session_id" class="session-card-title" @click.stop="startRename(s)">
              {{ s.title }}
              <span class="rename-hint">编辑</span>
            </div>
            <div v-else class="rename-input-wrap">
              <input ref="renameInput" v-model="editValue" class="rename-input" maxlength="100" @keyup.enter="saveRename(s.session_id)" @keyup.escape="cancelRename" @blur="saveRename(s.session_id)" @click.stop>
            </div>
            <div class="session-card-time">最近更新 · {{ formatTime(s.updated_at) }}</div>
          </div>
          <span class="open-arrow">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </span>
          <button class="delete-btn" @click.stop="handleDelete(s.session_id)" title="删除对话" aria-label="删除对话">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>
          </button>
        </article>
      </div>

      <div class="empty-state" v-else-if="!loading">
        <div class="empty-orbit"><span>{{ isLoveMaster ? '♥' : 'Z' }}</span></div>
        <h2>还没有对话</h2>
        <p>{{ isLoveMaster ? '说说最近让你在意的那件事。' : '给智能体一个目标，让它开始思考与行动。' }}</p>
        <button class="empty-action" @click="handleNewSession">创建第一条对话</button>
      </div>
      <div class="loading-state" v-else><i></i><span>正在同步对话记录</span></div>
    </section>
  </main>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import { listSessions, createSession, deleteSession, renameSession } from '../api'

const router = useRouter()
const route = useRoute()
const sessions = ref([])
const loading = ref(false)
const editingId = ref('')
const editValue = ref('')
const renameInput = ref(null)

const isLoveMaster = computed(() => route.path.startsWith('/love-master'))
const chatType = computed(() => isLoveMaster.value ? 'chain' : 'agent')
const pageTitle = computed(() => isLoveMaster.value ? 'AI恋爱大师 - 对话记录' : 'AI超级智能体 - 对话记录')
const themeClass = computed(() => isLoveMaster.value ? 'theme-love' : 'theme-agent')
useHead({ title: pageTitle })

async function loadSessions() {
  loading.value = true
  try {
    const res = await listSessions(chatType.value)
    if (res.code === 0) sessions.value = res.data || []
  } catch (e) { /* keep empty state */ }
  finally { loading.value = false }
}

async function handleNewSession() {
  try {
    const res = await createSession(chatType.value, '新对话')
    if (res.code === 0) {
      const base = isLoveMaster.value ? '/love-master' : '/super-agent'
      router.push(base + '/' + res.data.session_id)
    }
  } catch (e) { /* ignore */ }
}

function goToChat(s) {
  router.push((isLoveMaster.value ? '/love-master' : '/super-agent') + '/' + s.session_id)
}

async function startRename(s) {
  editingId.value = s.session_id
  editValue.value = s.title
  await nextTick()
  const input = Array.isArray(renameInput.value) ? renameInput.value[0] : renameInput.value
  if (input) { input.focus(); input.select() }
}

async function saveRename(sessionId) {
  const title = editValue.value.trim()
  if (title && title !== sessions.value.find(x => x.session_id === sessionId)?.title) {
    try { await renameSession(sessionId, title) } catch (e) { /* ignore */ }
  }
  editingId.value = ''
  editValue.value = ''
  await loadSessions()
}

function cancelRename() { editingId.value = ''; editValue.value = '' }
async function handleDelete(sessionId) {
  try { await deleteSession(sessionId); await loadSessions() } catch (e) { /* ignore */ }
}
function goHome() { router.push('/') }
function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  const now = new Date()
  return d.toDateString() === now.toDateString()
    ? d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
onMounted(loadSessions)
</script>

<style scoped>
.session-page { --accent: var(--primary); position: relative; min-height: 100vh; overflow: hidden; background: #070b16; }
.theme-love { --accent: var(--love); }
.page-glow { position: absolute; width: 640px; height: 640px; top: -360px; left: 50%; transform: translateX(-50%); border-radius: 50%; background: var(--accent); opacity: .11; filter: blur(130px); pointer-events: none; }
.session-nav { position: relative; z-index: 2; height: 76px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; max-width: 1080px; margin: 0 auto; padding: 0 24px; border-bottom: 1px solid var(--line); }
.back-btn { justify-self: start; display: flex; align-items: center; gap: 8px; padding: 8px 10px; color: var(--muted); background: transparent; border: 0; border-radius: 9px; }
.back-btn svg { width: 18px; }.back-btn:hover { color: var(--text); background: rgba(255,255,255,.04); }
.mini-brand { display: flex; align-items: center; gap: 10px; font: 700 14px 'Manrope', sans-serif; }
.mini-mark { width: 30px; height: 30px; display: grid; place-items: center; color: #07101b; background: var(--accent); border-radius: 9px; }
.agent-online { justify-self: end; display: flex; align-items: center; gap: 7px; color: #65728a; font-size: 10px; font-weight: 700; letter-spacing: .12em; }
.agent-online i { width: 6px; height: 6px; border-radius: 50%; background: var(--success); box-shadow: 0 0 9px var(--success); }
.session-shell { position: relative; z-index: 1; width: min(920px, calc(100% - 40px)); margin: 0 auto; padding: 78px 0 100px; }
.session-hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 28px; margin-bottom: 66px; }
.eyebrow { color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: .17em; }
.session-hero h1 { margin-top: 14px; font: 800 clamp(38px, 6vw, 58px)/1.1 'Manrope', sans-serif; letter-spacing: -.05em; }
.session-hero p { margin-top: 12px; color: var(--muted); font-size: 15px; }
.new-btn, .empty-action { flex-shrink: 0; display: flex; align-items: center; gap: 10px; height: 48px; padding: 0 18px; color: #08111b; background: var(--accent); border: 0; border-radius: 12px; font-weight: 800; box-shadow: 0 12px 30px color-mix(in srgb, var(--accent) 16%, transparent); transition: .2s; }
.new-btn:hover, .empty-action:hover { transform: translateY(-2px); filter: brightness(1.08); }
.plus { font-size: 22px; font-weight: 400; }
.list-meta { display: flex; justify-content: space-between; margin-bottom: 14px; color: #66738b; font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.session-list { display: flex; flex-direction: column; gap: 10px; }
.session-card { display: flex; align-items: center; gap: 16px; min-height: 84px; padding: 14px 16px; background: rgba(15,23,42,.66); border: 1px solid var(--line); border-radius: 16px; cursor: pointer; transition: .2s; }
.session-card:hover { transform: translateX(4px); background: rgba(19,29,50,.92); border-color: color-mix(in srgb, var(--accent) 32%, transparent); }
.session-icon { width: 48px; height: 48px; flex: 0 0 48px; display: grid; place-items: center; color: var(--accent); background: color-mix(in srgb, var(--accent) 9%, transparent); border: 1px solid color-mix(in srgb, var(--accent) 20%, transparent); border-radius: 13px; }
.session-icon svg { width: 22px; }
.session-card-info { min-width: 0; flex: 1; }
.session-card-title { display: flex; align-items: center; gap: 9px; overflow: hidden; color: #e6edf9; font-weight: 600; white-space: nowrap; text-overflow: ellipsis; }
.session-card-time { margin-top: 6px; color: #66738b; font-size: 11px; }
.rename-hint { opacity: 0; color: var(--accent); font-size: 10px; font-weight: 600; transition: .2s; }
.session-card:hover .rename-hint { opacity: 1; }
.rename-input { width: 100%; padding: 8px 10px; color: var(--text); background: #0a1020; border: 1px solid var(--accent); border-radius: 8px; outline: none; }
.open-arrow { width: 34px; height: 34px; display: grid; place-items: center; color: #526078; transition: .2s; }
.open-arrow svg, .delete-btn svg { width: 17px; }
.session-card:hover .open-arrow { color: var(--accent); transform: translateX(3px); }
.delete-btn { width: 34px; height: 34px; display: grid; place-items: center; color: #526078; background: transparent; border: 0; border-radius: 9px; }
.delete-btn:hover { color: var(--danger); background: rgba(251,113,133,.08); }
.empty-state { min-height: 360px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; background: rgba(15,23,42,.48); border: 1px dashed rgba(148,163,184,.22); border-radius: 22px; }
.empty-orbit { width: 88px; height: 88px; display: grid; place-items: center; margin-bottom: 26px; color: var(--accent); border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent); border-radius: 50%; box-shadow: 0 0 50px color-mix(in srgb, var(--accent) 10%, transparent); }
.empty-orbit span { width: 48px; height: 48px; display: grid; place-items: center; color: #07101b; background: var(--accent); border-radius: 14px; font-weight: 800; }
.empty-state h2 { font: 700 22px 'Manrope', sans-serif; }.empty-state p { margin-top: 8px; color: var(--muted); }
.empty-action { margin-top: 24px; }
.loading-state { min-height: 280px; display: flex; align-items: center; justify-content: center; gap: 12px; color: var(--muted); }
.loading-state i { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 12px var(--accent); animation: pulse 1s infinite alternate; }
@keyframes pulse { to { opacity: .3; transform: scale(.75); } }

@media (max-width: 640px) {
  .session-nav { grid-template-columns: 1fr auto; }.mini-brand { display: none; }
  .session-shell { padding-top: 52px; }.session-hero { align-items: flex-start; flex-direction: column; margin-bottom: 48px; }
  .new-btn { width: 100%; justify-content: center; }
  .session-card { gap: 12px; }.session-icon { width: 42px; height: 42px; flex-basis: 42px; }
  .open-arrow { display: none; }.rename-hint { display: none; }
}
</style>
