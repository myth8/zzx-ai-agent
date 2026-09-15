# AI智能体应用平台前端

这是一个基于Vue3开发的AI智能体应用平台，包含两个核心应用：AI恋爱大师和AI超级智能体。

## 功能特点

- 💬 **AI恋爱大师**：智能情感顾问，为用户提供恋爱相关的建议和解答
- 🤖 **AI超级智能体**：全能型AI助手，解决各类专业问题

## 技术栈

- Vue3
- Vue Router
- Axios
- SSE (Server-Sent Events)

## 开发说明

### 环境要求

- Node.js >= 16.0.0
- npm >= 7.0.0

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

### 构建项目

```bash
npm run build
```

## 后端接口

项目依赖以下后端接口：

- `/api/ai/love_app/chat/sse` - AI恋爱大师聊天接口
- `/api/ai/manus/chat` - AI超级智能体聊天接口

后端服务默认运行在 `http://127.0.0.1:8123`。开发服务器会把浏览器访问的
`/api` 同源代理到后端，因此即使 Vite 因端口被占用而从 3000 自动切换到
3001、3002 等端口，也不需要同步修改后端跨域白名单。

如需让浏览器绕过 Vite 直接请求另一个域名的后端，再设置完整的
`VITE_API_BASE_URL`，并将前端的精确 Origin 加入后端 `CORS_ORIGINS`。

# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).
