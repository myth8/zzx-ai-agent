<template>
  <main class="agent-workspace">
    <div class="workspace-glow"></div>
    <header class="workspace-header">
      <button class="back-button" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15 18-6-6 6-6"/></svg>
        <span>对话列表</span>
      </button>
      <div class="workspace-title">
        <span class="workspace-mark">Z</span>
        <span><b>AI 超级智能体</b><small>规划 · 推理 · 执行</small></span>
      </div>
      <div class="session-label" v-if="sessionId"><i></i>SESSION {{ sessionId.slice(0,6).toUpperCase() }}</div>
    </header>

    <section class="workspace-content">
      <div class="workspace-intro">
        <span>AGENT WORKSPACE</span>
        <p>把目标说清楚，剩下的交给智能体。</p>
      </div>
      <ChatRoom :messages="messages" :connection-status="connectionStatus" ai-type="super" @send-message="sendMessage" />
    </section>
  </main>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import ChatRoom from '../components/ChatRoom.vue'
import { chatWithManus, getSessionMessages } from '../api'

useHead({
  title: 'AI超级智能体 - ZZX AI Agent',
  meta: [{ name: 'description', content: '能够进行任务规划、深度推理与 MCP 工具调用的 AI 超级智能体。' }]
})

const router = useRouter()
const route = useRoute()
const messages = ref([])
const sessionId = ref(route.params.sessionId || "")
const connectionStatus = ref('disconnected')
let eventSource = null

async function loadSessionMessages(sid) {
  sessionId.value = sid
  messages.value = []
  if (sid) {
    try {
      const res = await getSessionMessages(sid)
      if (res.code === 0 && res.data) {
        for (const m of res.data) {
          messages.value.push({
            content: m.content,
            isUser: m.role === 'user',
            time: new Date(m.created_at || Date.now()).getTime(),
            type: m.role === 'user' ? '' : 'ai-final',
          })
        }
      }
    } catch (e) { /* ignore */ }
  }
}

const addMessage = (content, isUser, type) => messages.value.push({ content, isUser, type: type || '', time: Date.now() })
const sendMessage = (message) => {
  addMessage(message, true, 'user-question')
  if (eventSource) eventSource.close()
  connectionStatus.value = 'connecting'
  eventSource = chatWithManus(message, sessionId.value)
  eventSource.onmessage = (event) => {
    const data = event.data
    if (data === '[THINKING]') return
    if (data === '[DONE]') {
      connectionStatus.value = 'disconnected'
      eventSource.close()
      return
    }
    if (!data) return
    if (data.startsWith('[THINK]')) addMessage(data.slice(7).trim(), false, 'ai-think')
    else if (data.startsWith('[STEP]')) addMessage(data.slice(6).trim(), false, 'ai-step')
    else if (data.startsWith('[FINAL]')) addMessage(data.slice(7).trim(), false, 'ai-final')
  }
  eventSource.onerror = (error) => {
    console.error('SSE Error:', error)
    connectionStatus.value = 'error'
    eventSource.close()
  }
}
const goBack = () => router.push('/super-agent')
watch(() => route.params.sessionId, (newSid) => {
  if (newSid && newSid !== sessionId.value) loadSessionMessages(newSid)
})
onMounted(() => {
  if (route.params.sessionId) loadSessionMessages(route.params.sessionId)
  else addMessage('你好，我是 AI 超级智能体。告诉我你的目标，我会分析问题、规划步骤，并在需要时调用工具完成任务。', false, '')
})
onBeforeUnmount(() => { if (eventSource) eventSource.close() })
</script>

<style scoped>
.agent-workspace { position: relative; min-height: 100vh; overflow: hidden; background: linear-gradient(rgba(103,232,249,.02) 1px, transparent 1px), linear-gradient(90deg, rgba(103,232,249,.02) 1px, transparent 1px), #070b16; background-size: 52px 52px; }
.workspace-glow { position: absolute; width: 720px; height: 420px; top: -280px; left: 50%; transform: translateX(-50%); border-radius: 50%; background: #22d3ee; opacity: .09; filter: blur(120px); }
.workspace-header { position: relative; z-index: 2; height: 78px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 0 28px; background: rgba(7,11,22,.78); border-bottom: 1px solid var(--line); backdrop-filter: blur(16px); }
.back-button { justify-self: start; display: flex; align-items: center; gap: 8px; padding: 9px 11px; color: var(--muted); background: transparent; border: 0; border-radius: 10px; transition: .2s; }
.back-button svg { width: 18px; }.back-button:hover { color: var(--text); background: rgba(255,255,255,.04); }
.workspace-title { display: flex; align-items: center; gap: 11px; }
.workspace-title > span:last-child { display: flex; flex-direction: column; gap: 2px; }
.workspace-title b { font: 700 14px 'Manrope', sans-serif; }.workspace-title small { color: #617089; font-size: 10px; }
.workspace-mark { width: 34px; height: 34px; display: grid; place-items: center; color: #07101b; background: linear-gradient(135deg, var(--primary), var(--violet)); border-radius: 10px; font-weight: 800; }
.session-label { justify-self: end; display: flex; align-items: center; gap: 7px; color: #64718a; font-size: 9px; font-weight: 700; letter-spacing: .12em; }
.session-label i { width: 5px; height: 5px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px var(--success); }
.workspace-content { position: relative; z-index: 1; width: min(1100px, calc(100% - 40px)); margin: 0 auto; padding: 26px 0 34px; }
.workspace-intro { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; color: #56637a; font-size: 10px; letter-spacing: .13em; }
.workspace-intro p { color: #68758c; font-size: 12px; letter-spacing: 0; }
@media (max-width: 700px) {
  .workspace-header { height: 64px; grid-template-columns: 1fr auto; padding: 0 14px; }.workspace-title { display: none; }
  .back-button { padding-left: 0; }.workspace-content { width: calc(100% - 20px); padding: 14px 0 10px; }
  .workspace-intro { display: none; }
}
</style>
