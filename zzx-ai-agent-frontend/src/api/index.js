import axios from 'axios'

// API base URL based on environment
const API_BASE_URL = process.env.NODE_ENV === 'production'
  ? '/api'
  : 'http://localhost:8123/api'

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000
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

// AI Love Master chat
export const chatWithLoveApp = (message, chatId) => {
  return connectSSE('/ai/love_app/chat/sse', { message, chatId })
}

// AI Super Agent chat
export const chatWithManus = (message) => {
  return connectSSE('/ai/manus/chat', { message })
}

export default {
  chatWithLoveApp,
  chatWithManus
}
