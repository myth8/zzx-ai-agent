import axios from 'axios'

// API base URL based on environment
const API_BASE_URL = process.env.NODE_ENV === 'production'
  ? '/api'
  : 'http://localhost:8123/api'

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000
})

// --- request interceptor: attach Bearer token -------------------
request.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }
  return config
})

// --- Auth API ----------------------------------------------------

export const register = (username, nickname, password) => {
  return request.post('/auth/register', { username, nickname, password }).then(r => r.data)
}

export const login = (username, password) => {
  return request.post('/auth/login', { username, password }).then(r => r.data)
}

export const fetchCurrentUser = () => {
  const token = localStorage.getItem('token')
  if (!token) return Promise.reject(new Error('no token'))
  return request.get('/auth/userinfo', {
    headers: { Authorization: 'Bearer ' + token }
    }).then(r => r.data)
}

// --- Session API -------------------------------------------------

export const listSessions = (chatType) => {
  return request.get('/session/list', { params: { chat_type: chatType } }).then(r => r.data)
}

export const createSession = (chatType, title) => {
  return request.post('/session/create', { chat_type: chatType, title }).then(r => r.data)
}

export const renameSession = (sessionId, title) => {
  return request.put('/session/rename', { session_id: sessionId, title }).then(r => r.data)
}

export const deleteSession = (sessionId) => {
  return request.delete('/session/' + sessionId).then(r => r.data)
}

export const getSessionMessages = (sessionId) => {
  return request.get('/session/' + sessionId + '/messages').then(r => r.data)
}

// --- SSE helper --------------------------------------------------

export const connectSSE = (url, params, onMessage, onError) => {
  const queryString = Object.keys(params)
    .map(key => encodeURIComponent(key) + '=' + encodeURIComponent(params[key]))
    .join('&')

  const fullUrl = API_BASE_URL + url + '?' + queryString

  const eventSource = new EventSource(fullUrl)

  eventSource.onmessage = event => {
    let data = event.data
    if (data === '[DONE]') {
      if (onMessage) onMessage('[DONE]')
    } else {
      if (onMessage) onMessage(data)
    }
  }

  eventSource.onerror = error => {
    if (onError) onError(error)
    eventSource.close()
  }

  return eventSource
}

// AI Love Master chat (supports session_id for multi-turn)
export const chatWithLoveApp = (message, sessionId) => {
  const params = { message }
  if (sessionId) params.session_id = sessionId
  return connectSSE('/ai/love_app/chat/sse', params)
}

// AI Super Agent chat (supports session_id for multi-turn)
export const chatWithManus = (message, sessionId) => {
  const params = { message }
  if (sessionId) params.session_id = sessionId
  return connectSSE('/ai/manus/chat', params)
}

export default {
  chatWithLoveApp,
  chatWithManus
}
