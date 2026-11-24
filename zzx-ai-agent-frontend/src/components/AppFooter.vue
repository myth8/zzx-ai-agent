<template>
  <footer class="app-footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <span class="footer-mark">Z</span>
        <span><b>ZZX AI Agent</b><small>让智能真正参与工作</small></span>
      </div>
      <nav class="footer-links" aria-label="页脚链接">
        <a href="#">用户协议</a>
        <a href="#">隐私政策</a>
        <a href="https://juejin.cn/user/521640941459139" target="_blank" rel="noreferrer">技术博客</a>
        <a href="https://gitee.com/crzzx" target="_blank" rel="noreferrer">开源仓库</a>
      </nav>
      <span class="copyright">© {{ currentYear }} ZZX</span>
    </div>
  </footer>
</template>

<script setup>
import { computed } from 'vue'
const currentYear = computed(() => new Date().getFullYear())
</script>

<style scoped>
.app-footer { position: relative; z-index: 2; width: 100%; border-top: 1px solid var(--line); background: rgba(7,11,22,.72); }
.footer-inner { max-width: 1240px; min-height: 108px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 28px; margin: 0 auto; padding: 22px 28px; }
.footer-brand { display: flex; align-items: center; gap: 11px; }
.footer-mark { width: 32px; height: 32px; display: grid; place-items: center; color: #07101b; background: linear-gradient(135deg, var(--primary), var(--violet)); border-radius: 9px; font-weight: 800; }
.footer-brand > span:last-child { display: flex; flex-direction: column; gap: 2px; }
.footer-brand b { font: 700 12px 'Manrope', sans-serif; }.footer-brand small { color: #59667d; font-size: 10px; }
.footer-links { display: flex; gap: 22px; color: #718098; font-size: 11px; }
.footer-links a { transition: color .2s; }.footer-links a:hover { color: var(--primary); }
.copyright { justify-self: end; color: #4e5a70; font-size: 10px; letter-spacing: .08em; }
@media (max-width: 760px) {
  .footer-inner { grid-template-columns: 1fr auto; }.footer-links { grid-column: 1 / -1; grid-row: 2; flex-wrap: wrap; gap: 14px 20px; }.copyright { grid-column: 2; grid-row: 1; }
}
</style>
