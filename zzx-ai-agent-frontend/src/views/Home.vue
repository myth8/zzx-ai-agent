<template>
  <div class="home">
    <div class="aurora aurora-one"></div>
    <div class="aurora aurora-two"></div>

    <nav class="nav">
      <div class="brand-mark">
        <span class="brand-orb">Z</span>
        <span>ZZX AI Agent</span>
      </div>
      <div class="nav-right" v-if="user">
        <span class="online-pill"><i></i>智能体在线</span>
        <div class="user-chip">
          <span class="user-avatar">{{ user.nickname.charAt(0) }}</span>
          <span class="user-copy"><b>{{ user.nickname }}</b><small>@{{ user.username }}</small></span>
        </div>
        <button class="icon-button" @click="handleLogout" title="退出登录" aria-label="退出登录">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 5H5.8A1.8 1.8 0 0 0 4 6.8v10.4A1.8 1.8 0 0 0 5.8 19H9"/><path d="m15 16 4-4-4-4M19 12H9"/></svg>
        </button>
      </div>
    </nav>

    <main>
      <section class="hero">
        <div class="hero-kicker"><span>02</span> 个专属智能体已就绪</div>
        <h1>今天，想和哪个<br><span>智能体</span>一起思考？</h1>
        <p>从细腻的情感建议到复杂任务的自主规划，让合适的智能体接住你的每一个问题。</p>
        <div class="hero-meta">
          <span><i class="dot green"></i>系统正常</span>
          <span><i class="dot cyan"></i>MCP 已连接</span>
          <span><i class="dot violet"></i>长期对话</span>
        </div>
      </section>

      <section class="agent-grid" aria-label="选择智能体">
        <article class="agent-card love-card" tabindex="0" @click="navigateTo('/love-master')" @keyup.enter="navigateTo('/love-master')">
          <div class="card-topline">
            <span class="agent-state"><i></i>AVAILABLE</span>
            <span class="agent-index">AGENT / 01</span>
          </div>
          <div class="agent-visual love-visual">
            <svg viewBox="0 0 120 120" fill="none" aria-hidden="true">
              <circle cx="60" cy="60" r="42" stroke="currentColor" stroke-opacity=".18"/>
              <circle cx="60" cy="60" r="29" stroke="currentColor" stroke-opacity=".35" stroke-dasharray="3 5"/>
              <path d="M60 82S34 67 34 49.5C34 39.8 41.4 34 49 34c5.2 0 9.2 2.8 11 6.4 1.8-3.6 5.8-6.4 11-6.4 7.6 0 15 5.8 15 15.5C86 67 60 82 60 82Z" fill="currentColor"/>
            </svg>
          </div>
          <div class="agent-tag">EMOTIONAL INTELLIGENCE</div>
          <h2>AI 恋爱大师</h2>
          <p>理解关系里的言外之意，提供温柔、清醒且有边界感的情感建议。</p>
          <div class="skill-row"><span>关系分析</span><span>表达建议</span><span>情绪陪伴</span></div>
          <button class="enter-button" aria-label="进入 AI 恋爱大师">
            <span>开始对话</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
        </article>

        <article class="agent-card super-card" tabindex="0" @click="navigateTo('/super-agent')" @keyup.enter="navigateTo('/super-agent')">
          <div class="card-topline">
            <span class="agent-state"><i></i>AVAILABLE</span>
            <span class="agent-index">AGENT / 02</span>
          </div>
          <div class="agent-visual super-visual">
            <svg viewBox="0 0 120 120" fill="none" aria-hidden="true">
              <circle cx="60" cy="60" r="43" stroke="currentColor" stroke-opacity=".16"/>
              <path d="M42 43h36v34H42z" stroke="currentColor" stroke-width="3"/>
              <circle cx="52" cy="58" r="4" fill="currentColor"/><circle cx="68" cy="58" r="4" fill="currentColor"/>
              <path d="M51 69h18M60 43V32M55 32h10M35 52h7M78 52h7" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="agent-tag">AUTONOMOUS REASONING</div>
          <h2>AI 超级智能体</h2>
          <p>拆解复杂目标，调用 MCP 工具，边思考边执行，交付可用的最终结果。</p>
          <div class="skill-row"><span>深度推理</span><span>任务规划</span><span>工具调用</span></div>
          <button class="enter-button" aria-label="进入 AI 超级智能体">
            <span>开启任务</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
        </article>
      </section>

      <section class="value-strip">
        <div><strong>上下文记忆</strong><span>延续每一次有价值的对话</span></div>
        <div><strong>流式响应</strong><span>实时呈现智能体思考进度</span></div>
        <div><strong>MCP 工具生态</strong><span>从回答问题到真正执行任务</span></div>
      </section>
    </main>

    <AppFooter />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useHead } from '@vueuse/head'
import AppFooter from '../components/AppFooter.vue'

useHead({
  title: 'ZZX AI Agent - 智能体工作台',
  meta: [{ name: 'description', content: '选择你的专属 AI 智能体，获得专业建议、深度推理与任务执行能力。' }]
})

const router = useRouter()
const user = ref(null)

onMounted(() => {
  const raw = localStorage.getItem('user')
  if (raw) {
    try { user.value = JSON.parse(raw) } catch {}
  }
})

const navigateTo = (path) => router.push(path)

function handleLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  router.push('/login')
}
</script>

<style scoped>
.home {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background:
    linear-gradient(rgba(103,232,249,.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(103,232,249,.025) 1px, transparent 1px),
    #070b16;
  background-size: 54px 54px;
}

.aurora { position: absolute; border-radius: 50%; filter: blur(110px); opacity: .15; pointer-events: none; }
.aurora-one { width: 520px; height: 520px; top: -260px; left: 7%; background: #22d3ee; }
.aurora-two { width: 580px; height: 580px; top: 240px; right: -280px; background: #8b5cf6; }

.nav {
  position: relative;
  z-index: 3;
  max-width: 1240px;
  height: 88px;
  margin: 0 auto;
  padding: 0 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
}
.nav-right, .user-chip { display: flex; align-items: center; }
.nav-right { gap: 18px; }
.online-pill { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
.online-pill i { width: 7px; height: 7px; border-radius: 50%; background: var(--success); box-shadow: 0 0 10px var(--success); }
.user-chip { gap: 10px; padding-left: 18px; border-left: 1px solid var(--line); }
.user-avatar { width: 36px; height: 36px; display: grid; place-items: center; border: 1px solid rgba(103,232,249,.3); border-radius: 11px; color: var(--primary); background: rgba(103,232,249,.08); font-weight: 700; }
.user-copy { display: flex; flex-direction: column; gap: 2px; }
.user-copy b { font-size: 13px; }
.user-copy small { color: var(--muted); font-size: 11px; }
.icon-button { width: 36px; height: 36px; display: grid; place-items: center; color: var(--muted); background: transparent; border: 1px solid var(--line); border-radius: 10px; transition: .2s; }
.icon-button svg { width: 17px; }
.icon-button:hover { color: var(--text); border-color: var(--line-strong); background: rgba(255,255,255,.04); }

main { position: relative; z-index: 2; max-width: 1184px; margin: 0 auto; padding: 92px 28px 110px; }
.hero { max-width: 850px; margin-bottom: 64px; }
.hero-kicker { display: inline-flex; align-items: center; gap: 10px; color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.hero-kicker span { color: #07101b; padding: 4px 8px; border-radius: 5px; background: var(--primary); letter-spacing: 0; }
.hero h1 { margin-top: 24px; font: 800 clamp(48px, 7vw, 82px)/1.05 'Manrope', sans-serif; letter-spacing: -.065em; }
.hero h1 span { color: transparent; background: linear-gradient(90deg, #67e8f9, #a78bfa 72%); background-clip: text; -webkit-background-clip: text; }
.hero > p { max-width: 660px; margin-top: 24px; color: var(--muted); font-size: 17px; line-height: 1.8; }
.hero-meta { display: flex; flex-wrap: wrap; gap: 22px; margin-top: 32px; color: #69778f; font-size: 12px; }
.hero-meta span { display: flex; align-items: center; gap: 8px; }
.dot { width: 5px; height: 5px; border-radius: 50%; }
.green { background: var(--success); }.cyan { background: var(--primary); }.violet { background: var(--violet); }

.agent-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 22px; }
.agent-card { --accent: var(--primary); position: relative; min-height: 560px; padding: 28px; overflow: hidden; background: linear-gradient(145deg, rgba(18,28,49,.88), rgba(10,16,31,.94)); border: 1px solid var(--line); border-radius: 24px; box-shadow: var(--shadow); cursor: pointer; transition: transform .3s ease, border-color .3s ease, box-shadow .3s ease; }
.agent-card::before { content: ''; position: absolute; inset: 0; opacity: 0; background: radial-gradient(circle at 50% 25%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 47%); transition: opacity .3s; }
.agent-card:hover, .agent-card:focus-visible { transform: translateY(-8px); border-color: color-mix(in srgb, var(--accent) 38%, transparent); box-shadow: 0 32px 90px rgba(0,0,0,.46); outline: none; }
.agent-card:hover::before, .agent-card:focus-visible::before { opacity: 1; }
.love-card { --accent: var(--love); }.super-card { --accent: var(--primary); }
.card-topline { position: relative; z-index: 1; display: flex; justify-content: space-between; color: #65728a; font: 700 10px/1 'Manrope', sans-serif; letter-spacing: .13em; }
.agent-state { display: flex; align-items: center; gap: 7px; color: color-mix(in srgb, var(--accent) 75%, white); }
.agent-state i { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 9px var(--accent); }
.agent-visual { position: relative; z-index: 1; height: 190px; display: grid; place-items: center; margin: 18px -8px 10px; color: var(--accent); }
.agent-visual::before { content: ''; position: absolute; width: 150px; height: 150px; border-radius: 50%; background: color-mix(in srgb, var(--accent) 9%, transparent); filter: blur(4px); }
.agent-visual svg { position: relative; width: 150px; height: 150px; filter: drop-shadow(0 0 24px color-mix(in srgb, var(--accent) 35%, transparent)); }
.agent-tag { position: relative; z-index: 1; color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: .16em; }
.agent-card h2 { position: relative; z-index: 1; margin-top: 12px; font: 800 30px/1.2 'Manrope', sans-serif; letter-spacing: -.035em; }
.agent-card > p { position: relative; z-index: 1; min-height: 56px; margin-top: 12px; color: var(--muted); line-height: 1.75; }
.skill-row { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; }
.skill-row span { padding: 7px 10px; color: #aeb9cc; background: rgba(255,255,255,.035); border: 1px solid var(--line); border-radius: 8px; font-size: 11px; }
.enter-button { position: relative; z-index: 1; width: 100%; height: 50px; display: flex; align-items: center; justify-content: space-between; margin-top: 26px; padding: 0 18px; color: var(--text); background: color-mix(in srgb, var(--accent) 9%, transparent); border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent); border-radius: 12px; font-weight: 700; transition: .2s; }
.enter-button svg { width: 18px; transition: transform .2s; }
.agent-card:hover .enter-button { color: #07101b; background: var(--accent); border-color: var(--accent); }
.agent-card:hover .enter-button svg { transform: translateX(4px); }

.value-strip { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 24px; padding: 26px 30px; background: rgba(12,18,34,.65); border: 1px solid var(--line); border-radius: 18px; }
.value-strip div { display: flex; flex-direction: column; gap: 6px; padding: 0 26px; border-right: 1px solid var(--line); }
.value-strip div:first-child { padding-left: 0; }.value-strip div:last-child { border: 0; }
.value-strip strong { font-size: 13px; }.value-strip span { color: var(--muted); font-size: 12px; line-height: 1.5; }

@media (max-width: 800px) {
  .nav { height: 72px; padding: 0 20px; }
  .online-pill, .user-copy { display: none; }
  main { padding: 64px 20px 80px; }
  .hero { margin-bottom: 44px; }
  .hero h1 { font-size: clamp(42px, 12vw, 64px); }
  .agent-grid { grid-template-columns: 1fr; }
  .agent-card { min-height: 520px; }
  .value-strip { grid-template-columns: 1fr; gap: 18px; }
  .value-strip div { padding: 0 0 18px; border-right: 0; border-bottom: 1px solid var(--line); }
  .value-strip div:last-child { padding-bottom: 0; }
}

@media (max-width: 480px) {
  .brand-mark > span:last-child { display: none; }
  .user-chip { padding-left: 0; border: 0; }
  .hero-meta { gap: 14px; }
  .agent-card { min-height: auto; padding: 22px; }
  .agent-visual { height: 155px; }
}
</style>
