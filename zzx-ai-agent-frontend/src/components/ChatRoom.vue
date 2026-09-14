<template>
  <section class="chat-container" :class="aiType">
    <div class="chat-toolbar">
      <div class="model-info">
        <span class="model-indicator"><i></i></span>
        <span>
          <b>{{ aiType === 'love' ? 'Love Advisor' : 'ZZX Super Agent' }}</b>
          <small>{{ aiType === 'love' ? '情感洞察模型' : '推理与工具调用模型' }}</small>
        </span>
      </div>
      <div class="connection-badge" :class="connectionStatus">
        <i></i>{{ connectionStatus === 'connecting' ? '正在思考' : connectionStatus === 'error' ? '连接异常' : '已连接' }}
      </div>
    </div>

    <div class="chat-messages" ref="messagesContainer">
      <div v-if="messages.length === 0" class="message-skeleton">
        <span></span><span></span><span></span>
      </div>
      <div v-for="(msg, index) in messages" :key="index" class="message-wrapper">
        <div v-if="!msg.isUser" class="message ai-message" :class="[msg.type]">
          <div class="avatar ai-avatar"><AiAvatarFallback :type="aiType" /></div>
          <div class="message-stack">
            <span v-if="msg.type && aiType !== 'love'" class="message-label">
              {{ msg.type === 'ai-think' ? 'THINKING' : msg.type === 'ai-step' ? 'ACTION' : msg.type === 'ai-final' ? 'ANSWER' : 'AGENT' }}
            </span>
            <div class="message-bubble">
              <div class="message-content">
                <MarkdownRenderer :content="msg.content" />
                <span v-if="connectionStatus === 'connecting' && index === messages.length - 1" class="typing-indicator"></span>
              </div>
              <div class="message-time">{{ formatTime(msg.time) }}</div>
            </div>
          </div>
        </div>

        <div v-else class="message user-message" :class="[msg.type]">
          <div class="message-stack">
            <span class="message-label user-label">YOU</span>
            <div class="message-bubble">
              <div class="message-content">{{ msg.content }}</div>
              <div class="message-time">{{ formatTime(msg.time) }}</div>
            </div>
          </div>
          <div class="avatar user-avatar"><div class="avatar-placeholder">我</div></div>
        </div>
      </div>
    </div>

    <div class="chat-input-container">
      <div class="composer">
        <textarea
          v-model="inputMessage"
          @keydown.enter.exact.prevent="sendMessage"
          :placeholder="aiType === 'love' ? '说说你的感受或正在经历的关系问题…' : '描述目标、问题，或希望智能体完成的任务…'"
          class="input-box"
          rows="1"
          :disabled="connectionStatus === 'connecting'"
        ></textarea>
        <div class="composer-bottom">
          <span class="input-hint">Enter 发送 · Shift + Enter 换行</span>
          <button @click="sendMessage" class="send-button" :disabled="connectionStatus === 'connecting' || !inputMessage.trim()" aria-label="发送消息">
            <span>发送</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21 3-7.5 18-4.2-8.3L1 8.5 21 3Z"/><path d="m9.3 12.7 4.5-4.5"/></svg>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import AiAvatarFallback from './AiAvatarFallback.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  connectionStatus: { type: String, default: 'disconnected' },
  aiType: { type: String, default: 'default' }
})
const emit = defineEmits(['send-message'])
const inputMessage = ref('')
const messagesContainer = ref(null)

const sendMessage = () => {
  if (!inputMessage.value.trim()) return
  emit('send-message', inputMessage.value)
  inputMessage.value = ''
}
const formatTime = (timestamp) => new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
}
watch(() => props.messages.length, scrollToBottom)
watch(() => props.messages.map(m => m.content).join(''), scrollToBottom)
onMounted(scrollToBottom)
</script>

<style scoped>
.chat-container { --accent: var(--primary); height: min(760px, calc(100vh - 168px)); min-height: 560px; display: grid; grid-template-rows: 66px minmax(0, 1fr) auto; overflow: hidden; color: var(--text); background: rgba(9,15,29,.88); border: 1px solid var(--line); border-radius: 22px; box-shadow: 0 28px 90px rgba(0,0,0,.32); }
.chat-container.love { --accent: var(--love); }
.chat-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 0 20px; background: rgba(15,23,42,.72); border-bottom: 1px solid var(--line); }
.model-info { display: flex; align-items: center; gap: 11px; }
.model-indicator { width: 32px; height: 32px; display: grid; place-items: center; border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent); border-radius: 10px; background: color-mix(in srgb, var(--accent) 8%, transparent); }
.model-indicator i { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 11px var(--accent); }
.model-info > span:last-child { display: flex; flex-direction: column; gap: 2px; }
.model-info b { font: 700 12px 'Manrope', sans-serif; }.model-info small { color: #64718a; font-size: 10px; }
.connection-badge { display: flex; align-items: center; gap: 7px; padding: 6px 9px; color: #6e7b93; background: rgba(255,255,255,.025); border: 1px solid var(--line); border-radius: 999px; font-size: 10px; }
.connection-badge i { width: 5px; height: 5px; border-radius: 50%; background: var(--success); }
.connection-badge.connecting { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 22%, transparent); }
.connection-badge.connecting i { background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: pulse .7s infinite alternate; }
.connection-badge.error { color: var(--danger); }.connection-badge.error i { background: var(--danger); }
.chat-messages { overflow-y: auto; padding: 32px clamp(18px, 4vw, 44px); scroll-behavior: smooth; }
.message-wrapper { width: 100%; margin-bottom: 26px; }
.message { max-width: min(82%, 780px); display: flex; align-items: flex-start; gap: 11px; }
.ai-message { margin-right: auto; }.user-message { margin-left: auto; justify-content: flex-end; }
.avatar { width: 38px; height: 38px; flex: 0 0 38px; overflow: hidden; border-radius: 12px; }
.avatar-placeholder { width: 100%; height: 100%; display: grid; place-items: center; color: #09111e; background: linear-gradient(135deg, #a5f3fc, #a78bfa); font-size: 12px; font-weight: 800; }
.message-stack { min-width: 0; display: flex; flex-direction: column; align-items: flex-start; }
.user-message .message-stack { align-items: flex-end; }
.message-label { margin: 0 0 7px 2px; color: var(--accent); font-size: 9px; font-weight: 800; letter-spacing: .14em; }
.user-label { color: #78859c; margin-right: 2px; }
.message-bubble { min-width: 110px; padding: 15px 17px 10px; color: #dce5f5; background: #121b2e; border: 1px solid var(--line); border-radius: 6px 17px 17px 17px; word-break: break-word; }
.user-message .message-bubble { color: #07101b; background: linear-gradient(135deg, #a5f3fc, #8be7f4); border-color: transparent; border-radius: 17px 6px 17px 17px; }
.ai-think .message-bubble { color: #a9b5ca; background: rgba(167,139,250,.055); border-color: rgba(167,139,250,.16); }
.ai-think .message-label { color: var(--violet); }
.ai-step .message-bubble { background: rgba(52,211,153,.055); border-color: rgba(52,211,153,.15); }
.ai-step .message-label { color: var(--success); }
.ai-final .message-bubble { border-color: color-mix(in srgb, var(--accent) 20%, transparent); }
.message-content { font-size: 14px; line-height: 1.75; }
.message-time { margin-top: 7px; color: #65728a; font-size: 9px; text-align: right; }
.user-message .message-time { color: rgba(7,16,27,.48); }
.typing-indicator { display: inline-block; width: 6px; height: 14px; margin-left: 4px; vertical-align: -2px; background: var(--accent); animation: blink .7s infinite; }
.chat-input-container { padding: 16px 18px 18px; background: linear-gradient(to top, #090f1d 76%, rgba(9,15,29,.78)); }
.composer { padding: 13px 14px 11px 17px; background: #111a2b; border: 1px solid var(--line); border-radius: 16px; transition: .2s; }
.composer:focus-within { border-color: color-mix(in srgb, var(--accent) 42%, transparent); box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 6%, transparent); }
.input-box { width: 100%; min-height: 36px; max-height: 120px; resize: none; color: var(--text); background: transparent; border: 0; outline: none; line-height: 1.6; }
.input-box::placeholder { color: #55627a; }
.composer-bottom { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 7px; }
.input-hint { color: #4c5970; font-size: 10px; }
.send-button { height: 36px; display: flex; align-items: center; gap: 8px; padding: 0 13px; color: #07101b; background: var(--accent); border: 0; border-radius: 10px; font-size: 12px; font-weight: 800; transition: .2s; }
.send-button svg { width: 14px; }.send-button:hover:not(:disabled) { transform: translateY(-1px); filter: brightness(1.1); }
.send-button:disabled, .input-box:disabled { opacity: .4; cursor: not-allowed; }
.message-skeleton { display: flex; flex-direction: column; gap: 9px; padding: 24px; }
.message-skeleton span { width: 42%; height: 10px; border-radius: 99px; background: linear-gradient(90deg, #121b2e, #1a263d, #121b2e); background-size: 200%; animation: shimmer 1.5s infinite; }.message-skeleton span:nth-child(2) { width: 58%; }.message-skeleton span:nth-child(3) { width: 34%; }
@keyframes blink { 50% { opacity: .2; } } @keyframes pulse { to { opacity: .35; } } @keyframes shimmer { to { background-position: -200%; } }

@media (max-width: 700px) {
  .chat-container { height: calc(100vh - 96px); min-height: 500px; border-radius: 16px; }
  .chat-toolbar { padding: 0 14px; }.chat-messages { padding: 24px 14px; }
  .message { max-width: 95%; }.avatar { width: 34px; height: 34px; flex-basis: 34px; }
  .chat-input-container { padding: 10px; }.input-hint { display: none; }
}
</style>
