<template>
  <main class="engine-page">
    <div class="page-glow"></div>
    <header class="engine-nav">
      <button class="back-btn" @click="goHome">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15 18-6-6 6-6"/></svg>
        <span>工作台</span>
      </button>
      <div class="mini-brand"><span class="mini-mark">Z</span><span>Super Agent Engines</span></div>
      <span class="engine-online"><i></i>3 ENGINES ONLINE</span>
    </header>

    <section class="engine-shell">
      <div class="engine-hero">
        <span class="eyebrow">CHOOSE YOUR REASONING ENGINE</span>
        <h1>同一个目标，<br><span>三种思考方式。</span></h1>
        <p>LangChain 负责稳定的基线，MultiStepAgent 把多步循环握在自己手里。工具调用与代码执行各有主场，选一个最贴合任务的引擎开始。</p>
      </div>

      <div class="engine-grid">
        <article
          v-for="(item, index) in engines"
          :key="item.key"
          class="engine-card"
          :class="item.themeClass"
          :style="{ '--card-accent': item.accent }"
          tabindex="0"
          @click="enter(item)"
          @keyup.enter="enter(item)"
        >
          <div class="card-topline">
            <span class="engine-badge"><i></i>{{ item.badge }}</span>
            <span class="engine-index">0{{ index + 1 }} / ENGINE</span>
          </div>

          <div class="engine-visual">
            <div class="visual-orbit"></div>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55" aria-hidden="true">
              <path :d="item.icon" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>

          <span class="engine-eyebrow">{{ item.eyebrow }}</span>
          <h2>{{ item.label }}</h2>
          <p class="engine-desc">{{ item.description }}</p>

          <div class="engine-spec">
            <span>ACTION LANGUAGE</span>
            <b>{{ item.actionLanguage }}</b>
          </div>

          <ul class="feature-list">
            <li v-for="feature in item.features" :key="feature"><i></i>{{ feature }}</li>
          </ul>

          <div class="best-for">
            <span>适用场景</span>
            <b>{{ item.bestFor }}</b>
          </div>

          <button class="enter-btn" :aria-label="`进入 ${item.label}`">
            <span>进入引擎</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
        </article>
      </div>

      <section class="engine-compare" aria-label="引擎能力对比">
        <div class="compare-head">
          <span>QUICK COMPARE</span>
          <p>切换引擎不会影响其他引擎的历史会话，每个引擎拥有独立会话空间。</p>
        </div>
        <div class="compare-grid">
          <div class="compare-row compare-title"><span>动作协议</span><span>工具调用</span><span>更适合</span></div>
          <div v-for="item in engines" :key="item.key" class="compare-row" :style="{ '--row-accent': item.accent }">
            <span class="compare-engine"><i></i>{{ item.shortLabel }}</span>
            <span>{{ item.actionLanguage }}</span>
            <span>{{ item.key === 'code' ? '动态编排 / 计算' : item.key === 'toolcalling' ? '结构化工具链' : '稳定通用任务' }}</span>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useHead } from '@vueuse/head'
import { ENGINE_LIST as engines } from '../config/engines'

useHead({
  title: '选择 Agent 引擎 - ZZX AI Agent',
  meta: [{ name: 'description', content: '在 LangChain ReAct、ToolCallingAgent 与 CodeAgent 之间选择最适合任务的智能体引擎。' }]
})

const router = useRouter()
const goHome = () => router.push('/')
const enter = (item) => router.push(item.path)
</script>

<style scoped>
.engine-page { position: relative; min-height: 100vh; overflow: hidden; background: linear-gradient(rgba(103,232,249,.022) 1px, transparent 1px), linear-gradient(90deg, rgba(103,232,249,.022) 1px, transparent 1px), #070b16; background-size: 54px 54px; }
.page-glow { position: absolute; width: 780px; height: 540px; top: -340px; left: 50%; transform: translateX(-50%); border-radius: 50%; background: linear-gradient(90deg, #22d3ee, #8b5cf6, #34d399); opacity: .12; filter: blur(130px); pointer-events: none; }
.engine-nav { position: relative; z-index: 2; height: 78px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; max-width: 1180px; margin: 0 auto; padding: 0 26px; border-bottom: 1px solid var(--line); }
.back-btn { justify-self: start; display: flex; align-items: center; gap: 8px; padding: 8px 10px; color: var(--muted); background: transparent; border: 0; border-radius: 9px; }
.back-btn svg { width: 18px; }.back-btn:hover { color: var(--text); background: rgba(255,255,255,.04); }
.mini-brand { display: flex; align-items: center; gap: 10px; font: 700 14px 'Manrope', sans-serif; }
.mini-mark { width: 30px; height: 30px; display: grid; place-items: center; color: #07101b; background: linear-gradient(135deg, var(--primary), var(--violet)); border-radius: 9px; }
.engine-online { justify-self: end; display: flex; align-items: center; gap: 7px; color: #65728a; font-size: 10px; font-weight: 700; letter-spacing: .12em; }
.engine-online i { width: 6px; height: 6px; border-radius: 50%; background: var(--success); box-shadow: 0 0 9px var(--success); }
.engine-shell { position: relative; z-index: 1; width: min(1180px, calc(100% - 44px)); margin: 0 auto; padding: 76px 0 100px; }
.engine-hero { max-width: 820px; margin-bottom: 50px; }
.eyebrow { color: var(--primary); font-size: 10px; font-weight: 800; letter-spacing: .18em; }
.engine-hero h1 { margin-top: 16px; font: 800 clamp(40px, 6.3vw, 70px)/1.06 'Manrope', sans-serif; letter-spacing: -.06em; }
.engine-hero h1 span { color: transparent; background: linear-gradient(90deg, #67e8f9, #a78bfa 55%, #34d399); background-clip: text; -webkit-background-clip: text; }
.engine-hero p { max-width: 650px; margin-top: 22px; color: var(--muted); font-size: 15px; line-height: 1.85; }
.engine-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; }
.engine-card { --card-accent: var(--primary); position: relative; display: flex; flex-direction: column; min-height: 620px; padding: 26px; overflow: hidden; background: linear-gradient(155deg, rgba(18,28,49,.9), rgba(9,15,29,.96)); border: 1px solid var(--line); border-radius: 22px; box-shadow: var(--shadow); cursor: pointer; transition: transform .3s, border-color .3s, box-shadow .3s; }
.engine-card::before { content: ''; position: absolute; inset: 0; opacity: 0; background: radial-gradient(circle at 50% 16%, color-mix(in srgb, var(--card-accent) 15%, transparent), transparent 48%); transition: opacity .3s; }
.engine-card:hover, .engine-card:focus-visible { transform: translateY(-8px); border-color: color-mix(in srgb, var(--card-accent) 40%, transparent); box-shadow: 0 34px 90px rgba(0,0,0,.48); outline: none; }
.engine-card:hover::before, .engine-card:focus-visible::before { opacity: 1; }
.card-topline, .engine-visual, .engine-eyebrow, .engine-card h2, .engine-desc, .engine-spec, .feature-list, .best-for, .enter-btn { position: relative; z-index: 1; }
.card-topline { display: flex; justify-content: space-between; color: #65728a; font: 700 10px/1 'Manrope', sans-serif; letter-spacing: .13em; }
.engine-badge { display: flex; align-items: center; gap: 7px; color: color-mix(in srgb, var(--card-accent) 78%, white); }
.engine-badge i { width: 5px; height: 5px; border-radius: 50%; background: var(--card-accent); box-shadow: 0 0 9px var(--card-accent); }
.engine-visual { height: 148px; display: grid; place-items: center; margin: 10px -6px 4px; color: var(--card-accent); }
.visual-orbit { position: absolute; width: 116px; height: 116px; border: 1px solid color-mix(in srgb, var(--card-accent) 22%, transparent); border-radius: 50%; }
.engine-visual::after { content: ''; position: absolute; width: 150px; height: 150px; border-radius: 50%; background: color-mix(in srgb, var(--card-accent) 8%, transparent); filter: blur(16px); }
.engine-visual svg { position: relative; z-index: 1; width: 64px; height: 64px; filter: drop-shadow(0 0 20px color-mix(in srgb, var(--card-accent) 48%, transparent)); }
.engine-eyebrow { color: var(--card-accent); font-size: 9px; font-weight: 800; letter-spacing: .14em; }
.engine-card h2 { margin-top: 10px; font: 800 23px/1.25 'Manrope', sans-serif; letter-spacing: -.035em; }
.engine-desc { min-height: 92px; margin-top: 11px; color: var(--muted); font-size: 13px; line-height: 1.75; }
.engine-spec { display: flex; flex-direction: column; gap: 4px; margin-top: 16px; padding: 12px 13px; background: rgba(255,255,255,.026); border: 1px solid var(--line); border-radius: 10px; }
.engine-spec span { color: #66738b; font-size: 8px; font-weight: 800; letter-spacing: .13em; }
.engine-spec b { color: #c5d0e2; font: 600 12px 'Manrope', sans-serif; }
.feature-list { display: flex; flex-direction: column; gap: 9px; margin-top: 18px; list-style: none; }
.feature-list li { display: flex; align-items: center; gap: 9px; color: #a8b4c8; font-size: 12px; }
.feature-list i { width: 4px; height: 4px; border-radius: 50%; background: var(--card-accent); }
.best-for { display: flex; flex-direction: column; gap: 5px; margin-top: auto; padding-top: 18px; }
.best-for span { color: #66738b; font-size: 9px; font-weight: 800; letter-spacing: .1em; }
.best-for b { color: #c5d0e2; font-size: 12px; font-weight: 600; line-height: 1.5; }
.enter-btn { width: 100%; height: 46px; display: flex; align-items: center; justify-content: space-between; margin-top: 18px; padding: 0 16px; color: var(--text); background: color-mix(in srgb, var(--card-accent) 9%, transparent); border: 1px solid color-mix(in srgb, var(--card-accent) 26%, transparent); border-radius: 11px; font-weight: 700; transition: .2s; }
.enter-btn svg { width: 17px; transition: transform .2s; }
.engine-card:hover .enter-btn { color: #07101b; background: var(--card-accent); border-color: var(--card-accent); }
.engine-card:hover .enter-btn svg { transform: translateX(4px); }
.engine-compare { margin-top: 24px; padding: 24px 26px; background: rgba(11,17,32,.66); border: 1px solid var(--line); border-radius: 18px; }
.compare-head { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; margin-bottom: 16px; }
.compare-head span { color: var(--primary); font: 700 10px 'Manrope', sans-serif; letter-spacing: .14em; }
.compare-head p { color: #66738b; font-size: 11px; }
.compare-grid { display: flex; flex-direction: column; }
.compare-row { display: grid; grid-template-columns: 1.15fr 1.2fr 1.2fr; align-items: center; gap: 18px; padding: 11px 12px; color: #93a1b7; font-size: 12px; border-top: 1px solid rgba(148,163,184,.08); }
.compare-title { color: #5d6a82; font-size: 9px; font-weight: 800; letter-spacing: .1em; border-top: 0; padding-top: 0; }
.compare-engine { display: flex; align-items: center; gap: 8px; color: #d4deed; font-weight: 700; }
.compare-engine i { width: 5px; height: 5px; border-radius: 50%; background: var(--row-accent); }
@media (max-width: 1000px) {
  .engine-grid { grid-template-columns: 1fr; }
  .engine-card { min-height: auto; }
  .engine-desc { min-height: 0; }
  .engine-visual { height: 110px; }
  .best-for { margin-top: 20px; }
}
@media (max-width: 700px) {
  .engine-nav { height: 66px; grid-template-columns: 1fr auto; padding: 0 16px; }.mini-brand { display: none; }
  .engine-shell { width: calc(100% - 28px); padding: 52px 0 70px; }
  .engine-hero { margin-bottom: 34px; }
  .compare-head { flex-direction: column; gap: 6px; }
  .compare-row { grid-template-columns: 1fr 1fr; gap: 8px; }
  .compare-row span:last-child { grid-column: 1 / -1; color: #66738b; }
}
</style>
