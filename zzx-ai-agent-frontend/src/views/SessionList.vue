<template>
  <div class="list-container" :class="themeClass">
    <div class="list-header">
      <button class="back-btn" @click="goHome">&larr; 返回</button>
      <h1 class="list-title">{{ pageTitle }}</h1>
      <button class="new-btn" @click="handleNewSession">+ 新对话</button>
    </div>

    <div class="session-list" v-if="sessions.length > 0">
      <div
        v-for="s in sessions"
        :key="s.session_id"
        class="session-card"
        @click="goToChat(s)"
      >
        <div class="session-card-info">
          <div v-if="editingId !== s.session_id" class="session-card-title" @click.stop="startRename(s)">
            {{ s.title }}
            <span class="rename-hint">&#9998;</span>
          </div>
          <div v-else class="rename-input-wrap">
            <input
              ref="renameInput"
              v-model="editValue"
              class="rename-input"
              @keyup.enter="saveRename(s.session_id)"
              @keyup.escape="cancelRename"
              @blur="saveRename(s.session_id)"
              @click.stop
            />
          </div>
          <div class="session-card-time">{{ formatTime(s.updated_at) }}</div>
        </div>
        <button
          class="delete-btn"
          @click.stop="handleDelete(s.session_id)"
          title="删除对话"
        >&times;</button>
      </div>
    </div>

    <div class="empty-state" v-else>
      <div class="empty-icon">💬</div>
      <p>暂无对话记录</p>
      <p class="empty-hint">点击上方「+ 新对话」开始</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import { listSessions, createSession, deleteSession, renameSession } from '../api'

const router = useRouter()

const sessions = ref([])
const loading = ref(false)
const editingId = ref('')
const editValue = ref('')
const renameInput = ref(null)

// Determine chat type from route path
const route = useRoute()
const isLoveMaster = computed(() => route.path.startsWith('/love-master'))
const chatType = computed(() => isLoveMaster.value ? 'chain' : 'agent')
const pageTitle = computed(() => isLoveMaster.value ? 'AI恋爱大师 - 对话记录' : 'AI超级智能体 - 对话记录')
const themeClass = computed(() => isLoveMaster.value ? 'theme-love' : 'theme-agent')

useHead({
  title: pageTitle,
})

async function loadSessions() {
  loading.value = true
  try {
    const res = await listSessions(chatType.value)
    if (res.code === 0) {
      sessions.value = res.data || []
    }
  } catch (e) { /* ignore */ }
  finally { loading.value = false }
}

async function handleNewSession() {
  try {
    const res = await createSession(chatType.value, '新对话')
    if (res.code === 0) {
      const sid = res.data.session_id
      const base = isLoveMaster.value ? '/love-master' : '/super-agent'
      router.push(base + '/' + sid)
    }
  } catch (e) { /* ignore */ }
}

function goToChat(s) {
  const base = isLoveMaster.value ? '/love-master' : '/super-agent'
  router.push(base + '/' + s.session_id)
}

async function startRename(s) {
  editingId.value = s.session_id
  editValue.value = s.title
  await nextTick()
  if (renameInput.value) {
    renameInput.value.focus()
    renameInput.value.select()
  }
}

async function saveRename(sessionId) {
  const title = editValue.value.trim()
  if (title && title !== sessions.value.find(x => x.session_id === sessionId)?.title) {
    try {
      await renameSession(sessionId, title)
    } catch (e) { /* ignore */ }
  }
  editingId.value = ''
  editValue.value = ''
  await loadSessions()
}

function cancelRename() {
  editingId.value = ''
  editValue.value = ''
}

async function handleDelete(sessionId) {
  try {
    await deleteSession(sessionId)
    await loadSessions()
  } catch (e) { /* ignore */ }
}

function goHome() {
  router.push('/')
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

onMounted(() => {
  loadSessions()
})
</script>

<style scoped>
.list-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 20px;
}

.theme-love { background: #fff9f9; }
.theme-agent { background: #f9fbff; }

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  margin-bottom: 24px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}

.back-btn {
  font-size: 15px;
  cursor: pointer;
  background: none;
  border: none;
  color: #666;
  padding: 6px 12px;
  border-radius: 8px;
  transition: background 0.2s;
}
.back-btn:hover { background: rgba(0,0,0,0.05); }

.list-title {
  font-size: 1.3rem;
  font-weight: 700;
  color: #333;
  margin: 0;
}

.new-btn {
  font-size: 14px;
  cursor: pointer;
  border: none;
  background: #0088ff;
  color: #fff;
  padding: 8px 18px;
  border-radius: 20px;
  font-weight: 600;
  transition: background 0.2s;
}
.new-btn:hover { background: #006bb5; }

.session-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 700px;
  width: 100%;
  margin: 0 auto;
}

.session-card {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.theme-love .session-card:hover {
  box-shadow: 0 4px 12px rgba(255,107,139,0.15);
  border-color: #ff6b8b;
}
.theme-agent .session-card:hover {
  box-shadow: 0 4px 12px rgba(63,81,181,0.15);
  border-color: #3f51b5;
}

.session-card-info {
  flex: 1;
  min-width: 0;
}

.session-card-title {
  font-size: 1rem;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-card-time {
  font-size: 0.8rem;
  color: #999;
  margin-top: 4px;
}

.rename-hint {
  font-size: 0.75rem;
  color: #ccc;
  margin-left: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}
.session-card:hover .rename-hint { opacity: 1; }

.rename-input-wrap { padding: 2px 0; }

.rename-input {
  width: 100%;
  font-size: 1rem;
  font-weight: 600;
  color: #333;
  background: #f5f6fa;
  border: 1px solid #0088ff;
  border-radius: 6px;
  padding: 6px 10px;
  outline: none;
  font-family: inherit;
}

.delete-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #ccc;
  font-size: 1.2rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}
.session-card:hover .delete-btn { color: #bbb; }
.delete-btn:hover { background: rgba(255,71,87,0.1); color: #ff4757; }

.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: #999;
}
.empty-icon { font-size: 3rem; margin-bottom: 16px; }
.empty-hint { font-size: 0.85rem; margin-top: 8px; color: #bbb; }
</style>
