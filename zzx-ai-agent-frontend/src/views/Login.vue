<template>
  <main class="auth-page">
    <section class="auth-showcase" aria-label="平台介绍">
      <div class="auth-brand">
        <div class="brand-mark"><span class="brand-orb">Z</span><span>ZZX AI Agent</span></div>
        <div class="brand-status">Agent network online</div>
      </div>
      <div class="auth-promise">
        <div class="auth-eyebrow">Your intelligent workspace</div>
        <h1>让智能体理解你，<br><span>也替你完成工作。</span></h1>
        <p>汇聚专业问答、深度思考与 MCP 工具调用，把一次对话变成可以落地的结果。</p>
        <div class="auth-capabilities">
          <span>专业问答</span><span>智能规划</span><span>MCP 工具</span><span>情感陪伴</span>
        </div>
      </div>
      <div class="auth-version">ZZX AGENT SYSTEM · 2026</div>
    </section>

    <section class="auth-panel">
      <div class="auth-card">
        <div class="auth-card-head">
          <div class="brand-mark mobile-brand"><span class="brand-orb">Z</span><span>ZZX AI Agent</span></div>
          <h2>欢迎回来</h2>
          <p>登录你的智能工作空间，继续上一次对话。</p>
        </div>
        <form class="auth-form" @submit.prevent="handleLogin">
          <div class="field">
            <label for="login-username">账号</label>
            <div class="field-control">
              <span class="field-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="8" r="4"/><path d="M4.8 20c.8-4 3.2-6 7.2-6s6.4 2 7.2 6"/></svg>
              </span>
              <input id="login-username" v-model="form.username" type="text" placeholder="输入你的账号" autocomplete="username">
            </div>
          </div>
          <div class="field">
            <label for="login-password">密码</label>
            <div class="field-control">
              <span class="field-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>
              </span>
              <input id="login-password" v-model="form.password" type="password" placeholder="输入你的密码" autocomplete="current-password">
            </div>
          </div>
          <p v-if="errorMsg" class="auth-error">{{ errorMsg }}</p>
          <button type="submit" class="auth-submit" :disabled="loading">
            <span>{{ loading ? '正在连接...' : '进入工作台' }}</span>
            <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
        </form>
        <p class="auth-switch">还没有账号？<router-link to="/register">创建账号</router-link></p>
      </div>
    </section>
  </main>
</template>

<script setup>
import { ref, reactive } from "vue"
import { useRouter, useRoute } from "vue-router"
import { login } from "../api/index.js"

const router = useRouter()
const route = useRoute()
const form = reactive({ username: "", password: "" })
const errorMsg = ref("")
const loading = ref(false)

async function handleLogin() {
  errorMsg.value = ""
  if (!form.username.trim() || !form.password.trim()) {
    errorMsg.value = "请填写账号和密码"
    return
  }
  loading.value = true
  try {
    const res = await login(form.username.trim(), form.password)
    if (res.code !== 0) {
      errorMsg.value = res.msg || "登录失败"
      return
    }
    const { token, access_token: accessToken, ...profile } = res.data
    localStorage.setItem("token", accessToken || token)
    localStorage.setItem("user", JSON.stringify(profile))
    router.push(route.query.redirect || "/")
  } catch (e) {
    errorMsg.value = e.response?.data?.msg || "网络错误，请稍后重试"
  } finally {
    loading.value = false
  }
}
</script>
