import { createRouter, createWebHistory } from 'vue-router'

const publicRoutes = ['Login', 'Register']

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录 - ZZX-AI超级智能体' }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { title: '注册 - ZZX-AI超级智能体' }
  },
  {
    path: '/love-master',
    name: 'LoveSessions',
    component: () => import('../views/SessionList.vue'),
    meta: { title: 'AI恋爱大师 - ZZX-AI超级智能体' }
  },
  {
    path: '/love-master/:sessionId',
    name: 'LoveMaster',
    component: () => import('../views/LoveMaster.vue'),
    meta: { title: 'AI恋爱大师 - ZZX-AI超级智能体' }
  },
  {
    path: '/super-agent',
    name: 'AgentSessions',
    component: () => import('../views/SessionList.vue'),
    meta: { title: 'AI超级智能体 - ZZX-AI超级智能体' }
  },
  {
    path: '/super-agent/:sessionId',
    name: 'SuperAgent',
    component: () => import('../views/SuperAgent.vue'),
    meta: { title: 'AI超级智能体 - ZZX-AI超级智能体' }
  },
  {
    path: '/rag-admin',
    name: 'RagAdmin',
    component: () => import('../views/RagAdmin.vue'),
    meta: {
      title: 'RAG 知识库管理 - ZZX-AI超级智能体',
      requiresAdmin: true
    }
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: {
      title: '首页 - ZZX-AI超级智能体',
      description: 'ZZX-AI超级智能体提供AI恋爱大师和AI超级智能体服务，满足您的各种AI对话需求'
    }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  if (to.meta.title) {
    document.title = to.meta.title
  }
  const token = localStorage.getItem('token')
  if (!publicRoutes.includes(to.name)) {
    if (!token) {
      return next({ name: 'Login', query: { redirect: to.fullPath } })
    }
    if (to.meta.requiresAdmin) {
      try {
        const user = JSON.parse(localStorage.getItem('user') || '{}')
        if (user.role !== 'admin') return next({ name: 'Home' })
      } catch {
        return next({ name: 'Home' })
      }
    }
  } else {
    if (token) {
      return next({ name: 'Home' })
    }
  }
  next()
})

export default router
