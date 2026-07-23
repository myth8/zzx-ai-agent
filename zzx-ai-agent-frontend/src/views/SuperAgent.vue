<template>
  <div class="super-agent-container">
    <div class="header">
      <div class="back-button" @click="goBack">返回</div>
      <h1 class="title">AI超级智能体</h1>
      <div class="session-label" v-if="sessionId">会话 #{{ sessionId.slice(0,6) }}</div>
    </div>
    
    <div class="content-wrapper">
      <div class="chat-area">
        <ChatRoom 
          :messages="messages" 
          :connection-status="connectionStatus"
          ai-type="super"
          @send-message="sendMessage"
        />
      </div>
    </div>
    
    <div class="footer-container">
      <AppFooter />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import ChatRoom from '../components/ChatRoom.vue'
import AppFooter from '../components/AppFooter.vue'
import { chatWithManus, getSessionMessages } from '../api'

useHead({
  title: 'AI超级智能体 - ZZX-AI超级智能体',
  meta: [
    {
      name: 'description',
      content: 'AI超级智能体是ZZX-AI超级智能体的全能助手，能解答各类专业问题，提供精准建议和解决方案'
    },
    {
      name: 'keywords',
      content: 'AI超级智能体,智能助手,专业问答,AI问答,专业建议,ZZX,AI智能体'
    }
  ]
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

const addMessage = (content, isUser, type) => {
  messages.value.push({
    content,
    isUser,
    type: type || '',
    time: new Date().getTime()
  })
}

const sendMessage = (message) => {
  addMessage(message, true, 'user-question')

  if (eventSource) {
    eventSource.close()
  }

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

    if (data.startsWith('[THINK]')) {
      addMessage(data.slice(7).trim(), false, 'ai-think')
    } else if (data.startsWith('[STEP]')) {
      addMessage(data.slice(6).trim(), false, 'ai-step')
    } else if (data.startsWith('[FINAL]')) {
      addMessage(data.slice(7).trim(), false, 'ai-final')
    }
  }

  eventSource.onerror = (error) => {
    console.error('SSE Error:', error)
    connectionStatus.value = 'error'
    eventSource.close()
  }
}

const goBack = () => {
  router.push('/super-agent')
}

watch(() => route.params.sessionId, (newSid) => {
  if (newSid && newSid !== sessionId.value) {
    sessionId.value = newSid
    loadSessionMessages(newSid)
  }
})

onMounted(() => {
  if (route.params.sessionId) {
    loadSessionMessages(route.params.sessionId)
  } else {
    addMessage('你好，我是AI超级智能体。我可以解答各类问题，提供专业建议，请问有什么可以帮助你的吗？', false, '')
  }
})

onBeforeUnmount(() => {
  if (eventSource) {
    eventSource.close()
  }
})
</script>

<style scoped>
.super-agent-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: #f9fbff;
}

.header {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 16px 24px;
  background-color: #3f51b5;
  color: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  position: sticky;
  top: 0;
  z-index: 10;
}

.back-button {
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: opacity 0.2s;
  justify-self: start;
}

.back-button:hover {
  opacity: 0.8;
}

.back-button:before {
  content: '←';
  margin-right: 8px;
}

.title {
  font-size: 20px;
  font-weight: bold;
  margin: 0;
  text-align: center;
  justify-self: center;
}

.placeholder {
  width: 1px;
  justify-self: end;
}

.content-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.chat-area {
  flex: 1;
  padding: 16px;
  overflow: hidden;
  position: relative;
  min-height: calc(100vh - 56px - 180px);
  margin-bottom: 16px;
}

.footer-container {
  margin-top: auto;
}

@media (max-width: 768px) {
  .header {
    padding: 12px 16px;
  }
  
  .title {
    font-size: 18px;
  }
  
  .chat-area {
    padding: 12px;
    min-height: calc(100vh - 48px - 160px);
    margin-bottom: 12px;
  }
}

@media (max-width: 480px) {
  .header {
    padding: 10px 12px;
  }
  
  .back-button {
    font-size: 14px;
  }
  
  .chat-area {
    padding: 8px;
    min-height: calc(100vh - 42px - 150px);
    margin-bottom: 8px;
  }
}
</style>
