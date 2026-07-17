<template>
  <div class="auth-container">
    <div class="auth-card">
      <div class="auth-header">
        <div class="logo-area">
          <div class="logo-icon">ZZX</div>
        </div>
        <h2 class="auth-title">登录</h2>
        <p class="auth-desc">登录 ZZX-AI 超级智能体平台</p>
      </div>

      <form class="auth-form" @submit.prevent="handleLogin">
        <div class="input-group">
          <label class="input-label">账号</label>
          <div class="input-wrapper">
            <span class="input-icon">👤</span>
            <input
              v-model="form.username"
              type="text"
              placeholder="请输入账号"
              class="auth-input"
              autocomplete="username"
            />
          </div>
        </div>

        <div class="input-group">
          <label class="input-label">密码</label>
          <div class="input-wrapper">
            <span class="input-icon">🔒</span>
            <input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              class="auth-input"
              autocomplete="current-password"
            />
          </div>
        </div>

        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

        <button type="submit" class="auth-btn" :disabled="loading">
          <span v-if="loading" class="btn-loading">登录中...</span>
          <span v-else>登 录</span>
        </button>

        <p class="auth-switch">
          还没有账号？
          <router-link to="/register" class="switch-link">立即注册</router-link>
        </p>
      </form>
    </div>

    <div class="cyber-bg">
      <div class="cyber-circle c1"></div>
      <div class="cyber-circle c2"></div>
      <div class="cyber-circle c3"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from "vue"
import { useRouter, useRoute } from "vue-router"
import { login } from "../api/index.js"

const router = useRouter()
const route = useRoute()

const form = reactive({
  username: "",
  password: "",
})
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
    localStorage.setItem("token", res.data.token)
    localStorage.setItem("user", JSON.stringify(res.data))
    const redirect = route.query.redirect || "/"
    router.push(redirect)
  } catch (e) {
    errorMsg.value = e.response?.data?.msg || "网络错误，请稍后重试"
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background-color: #0a0a12;
  background-image:
    linear-gradient(0deg, rgba(8, 17, 34, 0.9), rgba(5, 8, 20, 0.9)),
    url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect x="0" y="0" width="100" height="1" fill="%23111133" opacity="0.3"/><rect x="0" y="0" width="1" height="100" fill="%23111133" opacity="0.3"/></svg>');
  background-size: auto, 40px 40px;
  position: relative;
  overflow: hidden;
  padding: 20px;
}

.auth-card {
  width: 100%;
  max-width: 420px;
  background: rgba(17, 23, 41, 0.8);
  backdrop-filter: blur(12px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 32px rgba(0, 240, 255, 0.15);
  padding: 40px 36px;
  position: relative;
  z-index: 2;
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo-area {
  margin-bottom: 16px;
}

.logo-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: linear-gradient(135deg, #00f0ff, #0088ff);
  color: #fff;
  font-family: "Orbitron", sans-serif;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 1px;
  box-shadow: 0 0 20px rgba(0, 240, 255, 0.4);
}

.auth-title {
  color: #edf7ff;
  font-size: 1.8rem;
  font-weight: 700;
  margin-bottom: 8px;
  text-shadow: 0 0 10px rgba(0, 240, 255, 0.3);
}

.auth-desc {
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.95rem;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.9rem;
  font-weight: 500;
}

.input-wrapper {
  display: flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 0 14px;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.input-wrapper:focus-within {
  border-color: #00f0ff;
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.15);
}

.input-icon {
  font-size: 1.1rem;
  margin-right: 10px;
  opacity: 0.6;
}

.auth-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #edf7ff;
  font-size: 1rem;
  padding: 14px 0;
}

.auth-input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.error-msg {
  color: #ff4757;
  font-size: 0.9rem;
  text-align: center;
  padding: 8px;
  background: rgba(255, 71, 87, 0.1);
  border-radius: 8px;
  border: 1px solid rgba(255, 71, 87, 0.2);
}

.auth-btn {
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(90deg, #0088ff, #00b2ff);
  color: #fff;
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  letter-spacing: 4px;
  border: 1px solid rgba(0, 240, 255, 0.2);
}

.auth-btn:hover:not(:disabled) {
  box-shadow: 0 0 20px rgba(0, 178, 255, 0.5);
  transform: translateY(-2px);
}

.auth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-loading {
  letter-spacing: 2px;
}

.auth-switch {
  text-align: center;
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.9rem;
}

.switch-link {
  color: #00f0ff;
  text-decoration: none;
  font-weight: 500;
  transition: color 0.2s;
}

.switch-link:hover {
  color: #00b2ff;
  text-decoration: underline;
}

/* Cyber background circles */
.cyber-bg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 1;
}

.cyber-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.12;
}

.c1 {
  width: 400px;
  height: 400px;
  top: -150px;
  right: -100px;
  background: linear-gradient(135deg, #00f0ff, #9000ff);
  animation: float 18s infinite alternate;
}

.c2 {
  width: 350px;
  height: 350px;
  bottom: -120px;
  left: -80px;
  background: linear-gradient(135deg, #9000ff, #ff00d4);
  animation: float 22s infinite alternate-reverse;
}

.c3 {
  width: 200px;
  height: 200px;
  top: 40%;
  left: 60%;
  background: linear-gradient(135deg, #ff00d4, #00f0ff);
  animation: float 14s infinite alternate;
}

@keyframes float {
  0% { transform: translate(0, 0) rotate(0deg); }
  100% { transform: translate(40px, 40px) rotate(8deg); }
}

@media (max-width: 480px) {
  .auth-card {
    padding: 30px 24px;
  }
  .auth-title {
    font-size: 1.5rem;
  }
  .auth-input {
    padding: 12px 0;
    font-size: 0.95rem;
  }
  .auth-btn {
    padding: 12px;
    font-size: 1rem;
  }
}
</style>
