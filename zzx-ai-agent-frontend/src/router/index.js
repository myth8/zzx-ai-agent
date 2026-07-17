import { createRouter, createWebHistory } from 'vue-router'

// Routes that do NOT require authentication
const publicRoutes = ['Login', 'Register']

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: {
      title: '登录 - ZZX-AI超级智能体'
    }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: {
      title: '注册 - ZZX-AI超级智能体'
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
  },
  {
    path: '/love-master',
    name: 'LoveMaster',
    component: () => import('../views/LoveMaster.vue'),
    meta: {
      title: 'AI恋爱大师 - ZZX-AI超级智能体',
      description: 'AI恋爱大师是ZZX-AI超级智能体的专业情感顾问，帮你解答各种恋爱问题，提供情感建议'
    }
  },
  {
    path: '/super-agent',
    name: 'SuperAgent',
    component: () => import('../views/SuperAgent.vue'),
    meta: {
      title: 'AI超级智能体 - ZZX-AI超级智能体',
      description: 'AI超级智能体是ZZX-AI超级智能体的全能助手，能解答各类专业问题，提供精准建议和解决方案'
    }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Global navigation guard
router.beforeEach((to, from, next) => {
  // Set page title
  if (to.meta.title) {
    document.title = to.meta.title
  }

  // Check login status
  const token = localStorage.getItem('token')
  if (!publicRoutes.includes(to.name)) {
    // Protected route -> require login
    if (!token) {
      return next({ name: 'Login', query: { redirect: to.fullPath } })
    }
  } else {
    // Logged-in user visiting login/register -> redirect home
    if (token) {
      return next({ name: 'Home' })
    }
  }
  next()
})

export default router
