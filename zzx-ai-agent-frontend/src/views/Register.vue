<template>
  <main class="auth-page">
    <section class="auth-showcase" aria-label="平台介绍">
      <div class="auth-brand">
        <div class="brand-mark"><span class="brand-orb">Z</span><span>ZZX AI Agent</span></div>
        <div class="brand-status">Agent network online</div>
      </div>
      <div class="auth-promise">
        <div class="auth-eyebrow">Build your second brain</div>
        <h1>一个账号，开启你的<br><span>专属智能体空间。</span></h1>
        <p>沉淀每一次对话，让智能体在连续的上下文中更懂你的目标、偏好与工作方式。</p>
        <div class="auth-capabilities">
          <span>对话记忆</span><span>上下文理解</span><span>任务执行</span><span>隐私空间</span>
        </div>
      </div>
      <div class="auth-version">ZZX AGENT SYSTEM · 2026</div>
    </section>

    <section class="auth-panel">
      <div class="auth-card">
        <div class="auth-card-head">
          <div class="brand-mark mobile-brand"><span class="brand-orb">Z</span><span>ZZX AI Agent</span></div>
          <h2>创建账号</h2>
          <p>几步完成注册，建立你的个人智能工作空间。</p>
        </div>
        <form class="auth-form" @submit.prevent="handleRegister">
          <div class="field">
            <label for="register-username">账号</label>
            <div class="field-control">
              <span class="field-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="8" r="4"/><path d="M4.8 20c.8-4 3.2-6 7.2-6s6.4 2 7.2 6"/></svg>
              </span>
              <input id="register-username" v-model="form.username" type="text" placeholder="3–50 个字符" autocomplete="username">
            </div>
          </div>
          <div class="field">
            <label for="register-nickname">昵称</label>
            <div class="field-control">
              <span class="field-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m4 16-.8 4 4-.8L18 8.4 15.6 6 4 16Z"/><path d="m13.8 7.8 2.4 2.4"/></svg>
              </span>
              <input id="register-nickname" v-model="form.nickname" type="text" placeholder="怎么称呼你？" autocomplete="name">
            </div>
          </div>
          <div class="field">
            <label for="register-password">密码</label>
            <div class="field-control">
              <span class="field-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>
              </span>
              <input id="register-password" v-model="form.password" type="password" placeholder="至少 6 位密码" autocomplete="new-password">
            </div>
          </div>
          <div class="field">
            <label for="register-confirm">确认密码</label>
            <div class="field-control">
              <span class="field-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><path d="m9.5 15 1.7 1.7 3.6-3.6"/></svg>
              </span>
              <input id="register-confirm" v-model="form.confirmPassword" type="password" placeholder="再次输入密码" autocomplete="new-password">
            </div>
          </div>
          <p v-if="errorMsg" class="auth-error">{{ errorMsg }}</p>
          <button type="submit" class="auth-submit" :disabled="loading">
            <span>{{ loading ? '正在创建...' : '创建智能空间' }}</span>
            <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
        </form>
        <p class="auth-switch">已经有账号？<router-link to="/login">返回登录</router-link></p>
      </div>
    </section>
  </main>
</template>

<script setup>
import { ref, reactive } from "vue"
import { useRouter } from "vue-router"
import { register } from "../api/index.js"

const router = useRouter()
const form = reactive({ username: "", nickname: "", password: "", confirmPassword: "" })
const errorMsg = ref("")
const loading = ref(false)

async function handleRegister() {
  errorMsg.value = ""
  if (!form.username.trim() || !form.nickname.trim() || !form.password || !form.confirmPassword) {
    errorMsg.value = "请填写所有字段"
    return
  }
  if (form.password !== form.confirmPassword) {
    errorMsg.value = "两次输入的密码不一致"
    return
  }
  if (form.password.length < 6) {
    errorMsg.value = "密码长度至少 6 位"
    return
  }
  if (form.username.trim().length < 3) {
    errorMsg.value = "账号长度至少 3 个字符"
    return
  }
  loading.value = true
  try {
    const res = await register(form.username.trim(), form.nickname.trim(), form.password)
    if (res.code !== 0) {
      errorMsg.value = res.msg || "注册失败"
      return
    }
    router.push("/login?registered=1")
  } catch (e) {
    errorMsg.value = e.response?.data?.msg || "网络错误，请稍后重试"
  } finally {
    loading.value = false
  }
}
</script>
