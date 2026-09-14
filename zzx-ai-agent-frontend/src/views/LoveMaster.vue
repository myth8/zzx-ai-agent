<template>
  <main class="love-workspace">
    <div class="workspace-glow"></div>
    <header class="workspace-header">
      <button class="back-button" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15 18-6-6 6-6"/></svg>
        <span>对话列表</span>
      </button>
      <div class="workspace-title">
        <span class="workspace-mark">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 20S4.5 15.7 4.5 9.4A4.4 4.4 0 0 1 12 6.3a4.4 4.4 0 0 1 7.5 3.1C19.5 15.7 12 20 12 20Z"/></svg>
        </span>
        <span><b>AI 恋爱大师</b><small>倾听 · 理解 · 陪伴</small></span>
      </div>
      <div class="session-label" v-if="sessionId"><i></i>PRIVATE {{ sessionId.slice(0,6).toUpperCase() }}</div>
    </header>

    <section class="workspace-content">
      <div class="workspace-intro">
        <span>SAFE CONVERSATION</span>
        <p>慢慢说，这里会认真听。</p>
      </div>
      <ChatRoom :messages="messages" :connection-status="connectionStatus" ai-type="love" @send-message="sendMessage" />
    </section>
  </main>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import ChatRoom from '../components/ChatRoom.vue'
import { chatWithLoveApp, getSessionMessages } from '../api'

useHead({
  title: 'AI恋爱大师 - ZZX AI Agent',
  meta: [{ name: 'description', content: '提供细腻、清醒、有边界感的关系分析与情感建议。' }]
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
            type: m.role === 'user' ? '' : 'ai-final'
          })
        }
      }
    } catch (e) { /* ignore */ }
  }
}

const addMessage = (content, isUser) => messages.value.push({ content, isUser, time: Date.now() })
const sendMessage = (message) => {
  addMessage(message, true)
  if (eventSource) eventSource.close()
  const aiMessageIndex = messages.value.length
  addMessage('', false)
  connectionStatus.value = 'connecting'
  eventSource = chatWithLoveApp(message, sessionId.value)
  eventSource.onmessage = (event) => {
    const data = event.data
    if (data === '[THINKING]' || data.startsWith('[THINK]') || data.startsWith('[STEP]')) return
    if (data && data !== '[DONE]' && aiMessageIndex < messages.value.length) messages.value[aiMessageIndex].content += data
    if (data === '[DONE]') {
      connectionStatus.value = 'disconnected'
      eventSource.close()
    }
  }
  eventSource.onerror = (error) => {
    console.error('SSE Error:', error)
    connectionStatus.value = 'error'
    eventSource.close()
  }
}
const goBack = () => router.push('/love-master')
watch(() => route.params.sessionId, (newSid) => { if (newSid) loadSessionMessages(newSid) })
onMounted(() => {
  if (route.params.sessionId) loadSessionMessages(route.params.sessionId)
  else addMessage('欢迎来到 AI 恋爱大师。你可以从最近发生的一件小事说起，我会陪你梳理感受，也会给出坦诚而有边界感的建议。', false)
})
onBeforeUnmount(() => { if (eventSource) eventSource.close() })
</script>

<style scoped>
.love-workspace { position: relative; min-height: 100vh; overflow: hidden; background: linear-gradient(rgba(251,113,133,.018) 1px, transparent 1px), linear-gradient(90deg, rgba(251,113,133,.018) 1px, transparent 1px), #090b16; background-size: 52px 52px; }
.workspace-glow { position: absolute; width: 720px; height: 420px; top: -280px; left: 50%; transform: translateX(-50%); border-radius: 50%; background: var(--love); opacity: .1; filter: blur(120px); }
.workspace-header { position: relative; z-index: 2; height: 78px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 0 28px; background: rgba(9,11,22,.78); border-bottom: 1px solid var(--line); backdrop-filter: blur(16px); }
.back-button { justify-self: start; display: flex; align-items: center; gap: 8px; padding: 9px 11px; color: var(--muted); background: transparent; border: 0; border-radius: 10px; transition: .2s; }
.back-button svg { width: 18px; }.back-button:hover { color: var(--text); background: rgba(255,255,255,.04); }
.workspace-title { display: flex; align-items: center; gap: 11px; }
.workspace-title > span:last-child { display: flex; flex-direction: column; gap: 2px; }
.workspace-title b { font: 700 14px 'Manrope', sans-serif; }.workspace-title small { color: #776672; font-size: 10px; }
.workspace-mark { width: 34px; height: 34px; display: grid; place-items: center; color: #1b0a10; background: linear-gradient(135deg, #fda4af, var(--love)); border-radius: 10px; }
.workspace-mark svg { width: 17px; }
.session-label { justify-self: end; display: flex; align-items: center; gap: 7px; color: #716373; font-size: 9px; font-weight: 700; letter-spacing: .12em; }
.session-label i { width: 5px; height: 5px; border-radius: 50%; background: var(--love); box-shadow: 0 0 8px var(--love); }
.workspace-content { position: relative; z-index: 1; width: min(1100px, calc(100% - 40px)); margin: 0 auto; padding: 26px 0 34px; }
.workspace-intro { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; color: #725d6b; font-size: 10px; letter-spacing: .13em; }
.workspace-intro p { color: #786873; font-size: 12px; letter-spacing: 0; }
@media (max-width: 700px) {
  .workspace-header { height: 64px; grid-template-columns: 1fr auto; padding: 0 14px; }.workspace-title { display: none; }
  .back-button { padding-left: 0; }.workspace-content { width: calc(100% - 20px); padding: 14px 0 10px; }
  .workspace-intro { display: none; }
}
</style>
