<template>
  <div class="love-master-container">
    <div class="header">
      <div class="back-button" @click="goBack">返回</div>
      <h1 class="title">AI恋爱大师</h1>
      <div class="session-label" v-if="sessionId">会话 #{{ sessionId.slice(0,6) }}</div>
    </div>
    
    <div class="content-wrapper">
      <div class="chat-area">
        <ChatRoom 
          :messages="messages" 
          :connection-status="connectionStatus"
          ai-type="love"
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
import { chatWithLoveApp, getSessionMessages } from '../api'

// 设置页面标题和元数据
useHead({
  title: 'AI恋爱大师 - ZZX-AI超级智能体',
  meta: [
    {
      name: 'description',
      content: 'AI恋爱大师是ZZX-AI超级智能体的专业情感顾问，帮你解答各种恋爱问题，提供情感建议'
    },
    {
      name: 'keywords',
      content: 'AI恋爱大师,情感顾问,恋爱咨询,AI聊天,情感问题,ZZX,AI智能体'
    }
  ]
})

const router = useRouter()
const route = useRoute()
const messages = ref([])
const sessionId = ref(route.params.sessionId || "")
const sidebarVisible = ref(true)
const connectionStatus = ref('disconnected')
let eventSource = null

// 生成随机会话ID
async function loadSessionMessages(sid) {
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

// 添加消息到列表
const addMessage = (content, isUser) => {
  messages.value.push({
    content,
    isUser,
    time: new Date().getTime()
  })
}

// 发送消息
const sendMessage = (message) => {
  addMessage(message, true)
  
  // 连接SSE
  if (eventSource) {
    eventSource.close()
  }
  
  // 创建一个空的AI回复消息
  const aiMessageIndex = messages.value.length
  addMessage('', false)
  
  connectionStatus.value = 'connecting'
  eventSource = chatWithLoveApp(message, sessionId.value)
  
  // 监听SSE消息
  eventSource.onmessage = (event) => {
    const data = event.data

    if (data === '[THINKING]' || data.startsWith('[THINK]') || data.startsWith('[STEP]')) {
      return
    }

    if (data && data !== '[DONE]') {
      // 更新最新的AI消息内容，而不是创建新消息
      if (aiMessageIndex < messages.value.length) {
        messages.value[aiMessageIndex].content += data
      }
    }
    
    if (data === '[DONE]') {
      connectionStatus.value = 'disconnected'
      eventSource.close()
    }
  }
  
  // 监听SSE错误
  eventSource.onerror = (error) => {
    console.error('SSE Error:', error)
    connectionStatus.value = 'error'
    eventSource.close()
  }
}

// 返回主页
const goBack = () => {
  router.push('/love-master')
}

// 页面加载时添加欢迎消息
watch(() => route.params.sessionId, (newSid) => {
  if (newSid) {
    sessionId.value = newSid
    loadSessionMessages(newSid)
  }
})

onMounted(() => {
  if (route.params.sessionId) {
    loadSessionMessages(route.params.sessionId)
  } else {
    addMessage('欢迎来到AI恋爱大师，请告诉我你的恋爱问题，我会尽力给予帮助和建议。', false)
  }
})

// 组件销毁前关闭SSE连接
onBeforeUnmount(() => {
  if (eventSource) {
    eventSource.close()
  }
})
</script>

<style scoped>
.love-master-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: #fff9f9;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background-color: #ff6b8b;
  color: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  position: sticky;
  top: 0;
  z-index: 10;
}

.sidebar-toggle {
  font-size: 18px;
  cursor: pointer;
  background: none;
  border: none;
  color: white;
  padding: 4px 8px;
  margin-right: 4px;
  border-radius: 6px;
  transition: background 0.2s;
  line-height: 1;
}
.sidebar-toggle:hover {
  background: rgba(255,255,255,0.15);
}

.back-button {
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: opacity 0.2s;
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
}

.session-label {
  font-size: 13px;
  opacity: 0.7;
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
  /* 设置最小高度确保内容显示正常 */
  min-height: calc(100vh - 56px - 180px);
  margin-bottom: 16px;
}

.footer-container {
  margin-top: auto;
}

/* 响应式样式 */
@media (max-width: 768px) {
  .header {
    padding: 12px 16px;
  }
  
  .title {
    font-size: 18px;
  }
  
  .chat-id {
    font-size: 12px;
  }
  
  .chat-area {
    padding: 12px;
    min-height: calc(100vh - 48px - 160px); /* 调整计算值 */
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
  
  .title {
    font-size: 16px;
  }
  
  .chat-id {
    display: none;
  }
  
  .chat-area {
    padding: 8px;
    min-height: calc(100vh - 42px - 150px); /* 再次调整计算值 */
    margin-bottom: 8px;
  }
}
</style> 