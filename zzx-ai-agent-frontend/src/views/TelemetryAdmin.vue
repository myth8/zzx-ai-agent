<template>
  <main class="observatory-page">
    <div class="observatory-glow"></div>
    <header class="observatory-nav">
      <button class="back-button" type="button" @click="router.push('/')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15 18-6-6 6-6"/></svg>
        <span>工作台</span>
      </button>
      <div class="observatory-brand"><span>观</span><b>智能体观测台</b><em>TELEMETRY</em></div>
      <span class="admin-badge">管理员 / 004</span>
    </header>

    <section class="observatory-shell">
      <div class="observatory-heading">
        <div>
          <span class="eyebrow">智能体运行观测</span>
          <h1>从对话，到每一步。</h1>
          <p>按会话查看运行记录，追踪步数、Token、工具调用与完整事件时间线。数据仅管理员可见。</p>
        </div>
        <div class="heading-actions">
          <label class="auto-refresh"><input v-model="autoRefresh" type="checkbox"> 自动刷新</label>
          <button class="refresh-button" type="button" :disabled="loading" @click="refreshAll">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.4 9A7 7 0 0 0 6.2 6.5L4 11M5.6 15A7 7 0 0 0 17.8 17.5L20 13"/></svg>
            {{ loading ? '读取中' : '刷新数据' }}
          </button>
        </div>
      </div>

      <div class="stats-grid">
        <article><span>运行次数</span><strong>{{ summary.runs }}</strong><small>最近 24 小时</small></article>
        <article><span>成功率</span><strong>{{ percent(summary.success_rate) }}</strong><small>成功 {{ summary.succeeded }} · 失败 {{ summary.failed }}</small></article>
        <article><span>Token 用量</span><strong>{{ formatNumber(summary.total_tokens) }}</strong><small>输入 + 输出</small></article>
        <article><span>平均耗时</span><strong>{{ formatDuration(summary.avg_duration_ms) }}</strong><small>服务端 Agent 循环</small></article>
        <article><span>工具错误</span><strong>{{ summary.tool_errors }}</strong><small>顶层工具失败</small></article>
      </div>

      <p v-if="error" class="page-message error">{{ error }}</p>

      <div class="filter-bar">
        <label>引擎
          <select v-model="filters.engine">
            <option value="">全部引擎</option>
            <option value="react">LangChain ReAct</option>
            <option value="toolcalling">结构化工具调用</option>
            <option value="code">代码智能体</option>
          </select>
        </label>
        <label>状态
          <select v-model="filters.status">
            <option value="">全部状态</option>
            <option value="succeeded">成功</option>
            <option value="failed">失败</option>
            <option value="running">运行中</option>
          </select>
        </label>
        <span class="filter-meta">{{ selectedConversation ? `会话 ${shortId(selectedConversation.session_id)}` : '全部会话' }} · {{ runs.length }} 条运行</span>
        <span class="live-dot"><i></i>{{ autoRefresh ? '实时' : '已暂停' }}</span>
      </div>

      <div class="observatory-grid">
        <aside class="rail conversations-rail">
          <div class="rail-head"><div><span>会话</span><h2>对话列表</h2></div><b>{{ conversations.length }}</b></div>
          <button type="button" class="conversation-item all-item" :class="{ active: !selectedConversation }" @click="selectConversation(null)">
            <span class="conversation-icon">全</span>
            <span class="conversation-copy"><b>全部会话</b><small>查看所有运行</small></span>
            <span class="conversation-meta">{{ totalRuns }}</span>
          </button>
          <div v-if="conversations.length" class="conversation-list">
            <button
              v-for="conversation in conversations"
              :key="conversation.session_id"
              type="button"
              class="conversation-item"
              :class="{ active: selectedConversation && selectedConversation.session_id === conversation.session_id }"
              @click="selectConversation(conversation)"
            >
              <span class="conversation-icon" :class="conversation.engine">{{ engineInitial(conversation.engine) }}</span>
              <span class="conversation-copy">
                <b>{{ conversation.title || '未命名会话' }}</b>
                <small>{{ engineLabel(conversation.engine) }} · {{ shortId(conversation.session_id) }} · {{ conversation.runs }} 次运行</small>
                <em>{{ formatNumber(conversation.total_tokens) }} token · {{ formatTime(conversation.last_run_at) }}</em>
              </span>
              <span class="conversation-health">
                <i class="ok" :style="{ opacity: conversation.succeeded ? 1 : .15 }"></i>
                <i class="bad" :style="{ opacity: conversation.failed ? 1 : .12 }"></i>
              </span>
            </button>
          </div>
          <div v-else class="rail-empty">还没有可展示的会话。<br>发起一次 Agent 对话后再回来。</div>
        </aside>

        <aside class="rail runs-rail">
          <div class="rail-head"><div><span>运行</span><h2>运行记录</h2></div><b>{{ runs.length }}</b></div>
          <div v-if="loading && !runs.length" class="rail-state"><i></i>正在读取运行记录</div>
          <div v-else-if="runs.length" class="run-list">
            <button
              v-for="run in runs"
              :key="run.id"
              type="button"
              class="run-item"
              :class="{ active: selectedRun && selectedRun.id === run.id }"
              @click="selectRun(run)"
            >
              <span class="run-status" :class="run.status"></span>
              <span class="run-copy">
                <b>{{ engineLabel(run.engine) }}</b>
                <small>{{ formatTime(run.started_at) }} · {{ statusLabel(run.status) }}</small>
                <em>{{ run.steps }} 步 · {{ run.tool_calls }} 次工具 · {{ formatNumber(run.total_tokens) }} token</em>
              </span>
              <span class="run-duration">{{ formatDuration(run.duration_ms) }}</span>
            </button>
          </div>
          <div v-else class="rail-empty">当前筛选下没有运行记录。</div>
        </aside>

        <section class="detail-panel">
          <template v-if="selectedRun">
            <header class="detail-head">
              <div>
                <span class="detail-eyebrow">{{ engineLabel(selectedRun.engine) }} · {{ statusLabel(selectedRun.status) }}</span>
                <h2>运行 {{ shortId(selectedRun.id) }}</h2>
                <p>{{ formatTime(selectedRun.started_at) }} · 会话 {{ shortId(selectedRun.session_id) }} · 请求 {{ shortId(selectedRun.request_id) }}</p>
              </div>
              <span class="detail-status" :class="selectedRun.status">{{ statusLabel(selectedRun.status) }}</span>
            </header>

            <div class="transcript-grid">
              <article class="transcript-card">
                <header><span>原始问题</span><small>{{ (selectedRun.input_text || '').length }} 字符</small></header>
                <p>{{ selectedRun.input_text || '这条运行没有保存原始问题。' }}</p>
              </article>
              <article class="transcript-card answer-card">
                <header><span>最终回答</span><small>{{ (selectedRun.output_text || '').length }} 字符</small></header>
                <p>{{ selectedRun.output_text || '这条运行没有保存最终回答。' }}</p>
              </article>
            </div>

            <div class="metric-grid">
              <div><span>步数</span><b>{{ selectedRun.steps }}</b></div>
              <div><span>工具调用</span><b>{{ selectedRun.tool_calls }}</b></div>
              <div><span>Token</span><b>{{ formatNumber(selectedRun.total_tokens) }}</b></div>
              <div><span>输入 Token</span><b>{{ formatNumber(selectedRun.prompt_tokens) }}</b></div>
              <div><span>输出 Token</span><b>{{ formatNumber(selectedRun.completion_tokens) }}</b></div>
              <div><span>耗时</span><b>{{ formatDuration(selectedRun.duration_ms) }}</b></div>
            </div>

            <div v-if="selectedRun.error_type" class="error-strip">异常类型：{{ selectedRun.error_type }}</div>

            <div class="context-strip">
              <span>上下文预算</span>
              <b>{{ selectedRun.context?.chars ?? '-' }} 字符</b>
              <small>保留 {{ selectedRun.context?.kept_steps ?? '-' }} 步 · 省略 {{ selectedRun.context?.omitted_steps ?? 0 }} 步 · 截断 {{ selectedRun.context?.truncated_messages ?? 0 }} 条消息</small>
            </div>

            <div class="timeline-head"><span>事件时间线</span><small>{{ events.length }} 个事件</small></div>
            <div v-if="loadingDetail" class="rail-state"><i></i>正在读取 Trace</div>
            <div v-else class="timeline">
              <article v-for="event in events" :key="event.seq" class="event-row">
                <span class="event-seq">{{ String(event.seq).padStart(2, '0') }}</span>
                <div class="event-body">
                  <div class="event-line">
                    <b>{{ eventLabel(event.event_type) }}</b>
                    <small>{{ event.created_at ? formatTime(event.created_at) : '' }}</small>
                  </div>
                  <p>{{ eventSummary(event) }}</p>
                  <details>
                    <summary>查看原始数据</summary>
                    <pre>{{ formatJson(event.payload) }}</pre>
                  </details>
                </div>
              </article>
            </div>
          </template>
          <div v-else class="detail-empty">
            <span>观</span>
            <h3>选择一条运行记录</h3>
            <p>左侧先选择会话，再选择一次运行，即可查看 Token、步数和事件时间线。</p>
          </div>
        </section>
      </div>
    </section>
  </main>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useHead } from '@vueuse/head'
import {
  getTelemetryRun,
  getTelemetrySummary,
  listTelemetryConversations,
  listTelemetryRuns,
} from '../api'

useHead({
  title: '智能体观测台 - ZZX AI Agent',
  meta: [{ name: 'description', content: '管理员专用智能体观测台：按会话查看运行、Token、工具调用和事件时间线。' }]
})

const router = useRouter()
const conversations = ref([])
const runs = ref([])
const totalRuns = ref(0)
const summary = ref({ runs: 0, succeeded: 0, failed: 0, running: 0, success_rate: 0, total_tokens: 0, avg_duration_ms: 0, tool_errors: 0 })
const selectedConversation = ref(null)
const selectedRun = ref(null)
const events = ref([])
const loading = ref(false)
const loadingDetail = ref(false)
const error = ref('')
const autoRefresh = ref(true)
const filters = reactive({ engine: '', status: '' })
let timer = null

const engineNames = { react: 'LangChain ReAct', toolcalling: '结构化工具调用', code: '代码智能体' }
const statusNames = { succeeded: '成功', failed: '失败', running: '运行中', cancelled: '已取消' }
const eventNames = {
  run_start: '运行开始',
  llm_end: '模型返回',
  tool_start: '工具开始',
  tool_error: '工具失败',
  stream_step: '流式步骤',
  step_end: '步骤结束',
  max_steps_reached: '达到步数上限',
  run_error: '运行失败',
  run_finish: '运行结束',
}

const engineLabel = (key) => engineNames[key] || key || '-'
const statusLabel = (key) => statusNames[key] || key || '-'
const eventLabel = (key) => eventNames[key] || key || '-'
const engineInitial = (key) => ({ react: 'R', toolcalling: 'T', code: 'C' }[key] || '?')
const shortId = (value) => value ? String(value).slice(0, 8) : '未关联'
const percent = (value) => `${Math.round((Number(value) || 0) * 100)}%`
const formatNumber = (value) => Number(value || 0).toLocaleString('zh-CN')
const formatDuration = (ms) => ms == null ? '-' : (Number(ms) / 1000).toFixed(1) + ' 秒'
const formatTime = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
const formatJson = (value) => {
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}
const eventSummary = (event) => {
  const p = event.payload || {}
  switch (event.event_type) {
    case 'run_start': return `最大步数 ${p.max_steps ?? '-'} · 任务 ${p.task_chars ?? '-'} 字符 · 工具 ${p.tools ?? '-'} 个`
    case 'llm_end': return `第 ${p.call ?? '-'} 次模型调用 · 输入 ${p.prompt_tokens ?? 0} · 输出 ${p.completion_tokens ?? 0} · 累计 ${(p.cumulative_prompt_tokens || 0) + (p.cumulative_completion_tokens || 0)} token`
    case 'tool_start': return `开始调用工具 ${p.tool ?? '-'}`
    case 'tool_error': return `工具 ${p.tool ?? '-'} 失败 · ${p.error_type ?? '-'}`
    case 'stream_step': return `动作 ${(p.actions || []).join('、') || '-'} · 观察 ${p.observations ?? 0} 条 · 耗时 ${p.elapsed_ms ?? 0}ms`
    case 'step_end': return `第 ${p.step ?? '-'} 步 · 耗时 ${p.duration_ms ?? 0}ms · 输入 ${p.prompt_tokens ?? 0} · 输出 ${p.completion_tokens ?? 0} · 工具 ${p.tool_calls ?? 0} 次`
    case 'max_steps_reached': return `达到最大步数 ${p.max_steps ?? '-'}`
    case 'run_error': return `运行异常 ${p.error_type ?? '-'} · 已运行 ${p.elapsed_ms ?? 0}ms`
    case 'run_finish': return `运行结束 · 状态 ${statusLabel(p.status)} · ${p.steps ?? 0} 步 · ${(p.prompt_tokens || 0) + (p.completion_tokens || 0)} token · ${p.duration_ms ?? 0}ms`
    default: return `事件序号 ${event.seq}`
  }
}

async function loadSummary() {
  try {
    const res = await getTelemetrySummary(24)
    if (res.code === 0) summary.value = res.data
  } catch (err) {
    error.value = err.response?.data?.message || '观测汇总读取失败'
  }
}

async function loadConversations() {
  try {
    const res = await listTelemetryConversations({ engine: filters.engine, limit: 100 })
    if (res.code === 0) conversations.value = res.data.conversations || []
  } catch (err) {
    error.value = err.response?.data?.message || '会话列表读取失败'
  }
}

async function loadRuns() {
  loading.value = true
  error.value = ''
  try {
    const params = { engine: filters.engine, status: filters.status, limit: 100 }
    if (selectedConversation.value) params.session_id = selectedConversation.value.session_id
    const res = await listTelemetryRuns(params)
    if (res.code === 0) {
      runs.value = res.data.runs || []
      totalRuns.value = res.data.total || 0
      if (selectedRun.value && !runs.value.some((run) => run.id === selectedRun.value.id)) {
        selectedRun.value = null
        events.value = []
      }
      if (!selectedRun.value && runs.value.length) await selectRun(runs.value[0])
    }
  } catch (err) {
    error.value = err.response?.data?.message || '运行记录读取失败'
  } finally {
    loading.value = false
  }
}

async function selectConversation(conversation) {
  selectedConversation.value = conversation
  selectedRun.value = null
  events.value = []
  await loadRuns()
}

async function selectRun(run) {
  selectedRun.value = run
  loadingDetail.value = true
  try {
    const res = await getTelemetryRun(run.id)
    if (res.code === 0) {
      selectedRun.value = res.data.run
      events.value = res.data.events || []
    }
  } catch (err) {
    error.value = err.response?.data?.message || 'Trace 读取失败'
  } finally {
    loadingDetail.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadConversations()])
  if (selectedConversation.value) {
    const stillExists = conversations.value.find((item) => item.session_id === selectedConversation.value.session_id)
    if (!stillExists) selectedConversation.value = null
  }
  await loadRuns()
}

function startTimer() {
  stopTimer()
  if (autoRefresh.value) timer = setInterval(refreshAll, 10000)
}
function stopTimer() {
  if (timer) { clearInterval(timer); timer = null }
}

watch(autoRefresh, (enabled) => enabled ? startTimer() : stopTimer())
watch(() => filters.engine, async () => {
  selectedConversation.value = null
  selectedRun.value = null
  await loadConversations()
  await loadRuns()
})
watch(() => filters.status, loadRuns)
onMounted(async () => {
  await refreshAll()
  startTimer()
})
onBeforeUnmount(stopTimer)
</script>

<style scoped>
.observatory-page { position: relative; min-height: 100vh; overflow: hidden; background: radial-gradient(circle at 18% 0%, rgba(34,211,238,.07), transparent 34%), radial-gradient(circle at 92% 18%, rgba(139,92,246,.06), transparent 30%), #070b16; }
.observatory-glow { position: absolute; width: 760px; height: 460px; top: -300px; left: 50%; transform: translateX(-50%); border-radius: 50%; background: linear-gradient(90deg, #22d3ee, #8b5cf6); opacity: .1; filter: blur(130px); pointer-events: none; }
.observatory-nav { position: relative; z-index: 2; height: 78px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; max-width: 1400px; margin: 0 auto; padding: 0 28px; border-bottom: 1px solid var(--line); }
.back-button { justify-self: start; display: flex; align-items: center; gap: 8px; padding: 8px 10px; color: var(--muted); background: transparent; border: 0; border-radius: 9px; }
.back-button svg { width: 18px; }.back-button:hover { color: var(--text); background: rgba(255,255,255,.04); }
.observatory-brand { display: flex; align-items: center; gap: 10px; font: 700 14px 'Manrope', sans-serif; }
.observatory-brand > span { width: 32px; height: 32px; display: grid; place-items: center; color: #07101b; background: linear-gradient(135deg, var(--primary), var(--violet)); border-radius: 9px; font-size: 15px; }
.observatory-brand em { color: #5f6c84; font-size: 8px; font-style: normal; letter-spacing: .16em; }
.admin-badge { justify-self: end; padding: 6px 9px; color: #07101b; background: linear-gradient(90deg, #67e8f9, #a78bfa); border-radius: 7px; font-size: 9px; font-weight: 800; letter-spacing: .08em; }
.observatory-shell { position: relative; z-index: 1; width: min(1400px, calc(100% - 40px)); margin: 0 auto; padding: 52px 0 76px; }
.observatory-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
.eyebrow { color: var(--primary); font-size: 10px; font-weight: 800; letter-spacing: .18em; }
.observatory-heading h1 { margin-top: 10px; font: 800 clamp(34px, 5vw, 56px)/1.04 'Manrope', sans-serif; letter-spacing: -.06em; }
.observatory-heading p { max-width: 700px; margin-top: 11px; color: var(--muted); font-size: 14px; line-height: 1.75; }
.heading-actions { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
.auto-refresh { display: flex; align-items: center; gap: 7px; color: #6f7d96; font-size: 11px; }
.auto-refresh input { accent-color: var(--primary); }
.refresh-button { display: flex; align-items: center; gap: 8px; height: 38px; padding: 0 13px; color: var(--text); background: rgba(103,232,249,.08); border: 1px solid rgba(103,232,249,.24); border-radius: 9px; font-size: 11px; font-weight: 700; }
.refresh-button svg { width: 15px; }.refresh-button:hover:not(:disabled) { background: rgba(103,232,249,.14); }
.refresh-button:disabled { opacity: .5; }
.stats-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.stats-grid article { padding: 15px 16px; background: rgba(13,21,38,.82); border: 1px solid var(--line); border-radius: 13px; }
.stats-grid span { display: block; color: #8a98af; font-size: 10px; font-weight: 700; }
.stats-grid strong { display: block; margin-top: 7px; color: #e3ebf7; font: 800 24px/1 'Manrope', sans-serif; }
.stats-grid small { display: block; margin-top: 7px; color: #5f6c84; font-size: 10px; }
.page-message { margin: 0 0 14px; padding: 11px 13px; border-radius: 9px; font-size: 12px; }
.page-message.error { color: #fecdd3; background: rgba(251,113,133,.09); border: 1px solid rgba(251,113,133,.22); }
.filter-bar { display: flex; align-items: center; gap: 16px; padding: 10px 13px; margin-bottom: 14px; background: rgba(9,15,29,.72); border: 1px solid var(--line); border-radius: 11px; }
.filter-bar label { display: flex; align-items: center; gap: 7px; color: #8795ad; font-size: 10px; font-weight: 700; }
.filter-bar select { padding: 6px 8px; color: #d5dfef; background: #0c1424; border: 1px solid var(--line); border-radius: 7px; font-size: 11px; outline: none; }
.filter-meta { margin-left: auto; color: #607089; font-size: 10px; }
.live-dot { display: flex; align-items: center; gap: 6px; color: #64718a; font-size: 9px; font-weight: 800; letter-spacing: .06em; }
.live-dot i { width: 5px; height: 5px; border-radius: 50%; background: var(--success); box-shadow: 0 0 7px var(--success); }
.observatory-grid { display: grid; grid-template-columns: minmax(220px, .75fr) minmax(260px, .95fr) minmax(0, 1.7fr); gap: 14px; align-items: start; }
.rail, .detail-panel { background: rgba(10,17,32,.82); border: 1px solid var(--line); border-radius: 16px; }
.rail { min-height: 600px; padding: 15px; }
.rail-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.rail-head span { display: block; color: #5f6c84; font-size: 8px; font-weight: 800; letter-spacing: .12em; }
.rail-head h2 { margin-top: 4px; font: 700 16px 'Manrope', sans-serif; }
.rail-head b { color: var(--primary); font: 700 11px 'Manrope', sans-serif; }
.rail-empty, .rail-state { min-height: 160px; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 16px; color: #64718a; font-size: 11px; line-height: 1.8; text-align: center; }
.rail-state i { width: 7px; height: 7px; border-radius: 50%; background: var(--primary); animation: pulse 1s infinite alternate; }
.conversation-list, .run-list { display: flex; flex-direction: column; gap: 7px; max-height: 600px; overflow: auto; }
.conversation-item { display: flex; align-items: center; gap: 9px; width: 100%; padding: 10px 9px; text-align: left; background: transparent; border: 1px solid transparent; border-radius: 10px; transition: .2s; }
.conversation-item:hover { background: rgba(255,255,255,.035); border-color: var(--line); }
.conversation-item.active { background: rgba(103,232,249,.07); border-color: rgba(103,232,249,.24); }
.all-item { margin-bottom: 6px; }
.conversation-icon { width: 30px; height: 30px; flex: 0 0 30px; display: grid; place-items: center; color: #07101b; background: linear-gradient(135deg, #67e8f9, #a78bfa); border-radius: 9px; font: 800 11px 'Manrope', sans-serif; }
.conversation-icon.toolcalling { background: linear-gradient(135deg, #c4b5fd, #a78bfa); }.conversation-icon.code { background: linear-gradient(135deg, #6ee7b7, #34d399); }
.conversation-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
.conversation-copy b { color: #d8e1ef; font-size: 11px; }.conversation-copy small { color: #8a98af; font-size: 9px; }.conversation-copy em { color: #5f6c84; font-size: 9px; font-style: normal; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conversation-meta { color: #64718a; font-size: 9px; }
.conversation-health { display: flex; flex-direction: column; gap: 4px; }
.conversation-health i { width: 5px; height: 5px; border-radius: 50%; }.conversation-health .ok { background: var(--success); }.conversation-health .bad { background: var(--danger); }
.run-item { display: flex; align-items: center; gap: 9px; width: 100%; padding: 10px 9px; text-align: left; background: transparent; border: 1px solid transparent; border-radius: 9px; transition: .2s; }
.run-item:hover { background: rgba(255,255,255,.035); border-color: var(--line); }
.run-item.active { background: rgba(167,139,250,.07); border-color: rgba(167,139,250,.24); }
.run-status { width: 6px; height: 6px; flex: 0 0 6px; border-radius: 50%; background: #64718a; }
.run-status.succeeded { background: var(--success); box-shadow: 0 0 7px color-mix(in srgb, var(--success) 60%, transparent); }.run-status.failed { background: var(--danger); }.run-status.running { background: var(--primary); animation: pulse 1s infinite alternate; }
.run-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
.run-copy b { color: #d8e1ef; font-size: 11px; }.run-copy small { color: #8a98af; font-size: 9px; }.run-copy em { color: #5f6c84; font-size: 9px; font-style: normal; }
.run-duration { color: #64718a; font-size: 9px; white-space: nowrap; }
.detail-panel { min-height: 600px; padding: 18px; }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--line); }
.detail-eyebrow { color: var(--primary); font-size: 9px; font-weight: 800; letter-spacing: .08em; }
.detail-head h2 { margin-top: 7px; font: 800 23px/1.1 'Manrope', sans-serif; letter-spacing: -.035em; }
.detail-head p { margin-top: 6px; color: #607089; font-size: 10px; line-height: 1.7; }
.detail-status { padding: 6px 9px; border-radius: 7px; font-size: 9px; font-weight: 800; }
.detail-status.succeeded { color: var(--success); background: rgba(52,211,153,.08); border: 1px solid rgba(52,211,153,.2); }.detail-status.failed { color: var(--danger); background: rgba(251,113,133,.08); border: 1px solid rgba(251,113,133,.2); }.detail-status.running { color: var(--primary); background: rgba(103,232,249,.08); border: 1px solid rgba(103,232,249,.2); }
.transcript-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.transcript-card { padding: 12px 13px; background: rgba(255,255,255,.022); border: 1px solid var(--line); border-radius: 10px; }
.transcript-card.answer-card { border-color: rgba(103,232,249,.16); }
.transcript-card header { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 7px; }
.transcript-card header span { color: #9aa8bf; font-size: 10px; font-weight: 700; }
.transcript-card header small { color: #5f6c84; font-size: 9px; }
.transcript-card p { max-height: 150px; overflow: auto; color: #c3d0e4; font-size: 11px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.metric-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; margin-top: 16px; }
.metric-grid div { padding: 10px; background: rgba(255,255,255,.025); border: 1px solid var(--line); border-radius: 8px; }
.metric-grid span { display: block; color: #8a98af; font-size: 9px; }.metric-grid b { display: block; margin-top: 5px; color: #dbe5f3; font: 700 13px 'Manrope', sans-serif; }
.error-strip { margin-top: 12px; padding: 9px 11px; color: #fecdd3; background: rgba(251,113,133,.07); border: 1px solid rgba(251,113,133,.2); border-radius: 8px; font-size: 10px; }
.context-strip { display: flex; align-items: baseline; gap: 9px; margin-top: 12px; padding: 9px 11px; background: rgba(167,139,250,.045); border: 1px solid rgba(167,139,250,.14); border-radius: 8px; }
.context-strip span { color: #a997d4; font-size: 9px; font-weight: 700; }.context-strip b { color: #cfc3ef; font-size: 11px; }.context-strip small { color: #756793; font-size: 9px; }
.timeline-head { display: flex; align-items: baseline; justify-content: space-between; margin: 20px 0 10px; color: #8795ad; font-size: 10px; font-weight: 700; }
.timeline-head small { color: #5f6c84; font-size: 9px; font-weight: 400; }
.timeline { display: flex; flex-direction: column; gap: 0; max-height: 520px; overflow: auto; padding-right: 4px; }
.event-row { display: flex; gap: 12px; padding: 10px 0; border-top: 1px solid rgba(148,163,184,.08); }
.event-seq { width: 24px; flex: 0 0 24px; color: #526078; font: 700 10px 'Manrope', sans-serif; }
.event-body { min-width: 0; flex: 1; }
.event-line { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.event-line b { color: #bfcbe0; font-size: 10px; }.event-line small { color: #56637a; font-size: 9px; }
.event-body p { margin-top: 4px; color: #75839a; font-size: 10px; line-height: 1.6; word-break: break-word; }
.event-body details { margin-top: 5px; color: #5f6c84; font-size: 9px; }.event-body summary { cursor: pointer; }
.event-body pre { max-height: 240px; overflow: auto; margin-top: 5px; padding: 8px; color: #93a3bc; background: #070d18; border: 1px solid var(--line); border-radius: 7px; font-size: 9px; line-height: 1.5; }
.detail-empty { min-height: 560px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.detail-empty > span { width: 54px; height: 54px; display: grid; place-items: center; color: #07101b; background: linear-gradient(135deg, var(--primary), var(--violet)); border-radius: 15px; font: 800 20px 'Manrope', sans-serif; }
.detail-empty h3 { margin-top: 16px; font: 700 18px 'Manrope', sans-serif; }.detail-empty p { max-width: 320px; margin-top: 8px; color: #607089; font-size: 12px; line-height: 1.7; }
@keyframes pulse { to { opacity: .35; } }
@media (max-width: 1150px) {
  .observatory-grid { grid-template-columns: minmax(200px, .7fr) minmax(240px, .9fr) minmax(0, 1.5fr); }
  .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .observatory-grid { grid-template-columns: 1fr 1fr; }
  .detail-panel { grid-column: 1 / -1; }
  .conversations-rail, .runs-rail { min-height: 420px; }
}
@media (max-width: 700px) {
  .observatory-nav { height: 66px; grid-template-columns: 1fr auto; padding: 0 16px; }.observatory-brand { display: none; }
  .observatory-shell { width: calc(100% - 24px); padding: 34px 0 50px; }
  .observatory-heading { flex-direction: column; align-items: flex-start; }
  .heading-actions { width: 100%; justify-content: space-between; }
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .filter-bar { flex-wrap: wrap; gap: 9px; }.filter-meta { width: 100%; margin-left: 0; }
  .observatory-grid { grid-template-columns: 1fr; }
  .detail-panel { grid-column: auto; }
  .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .transcript-grid { grid-template-columns: 1fr; }
  .detail-head { flex-direction: column; }
}
</style>
