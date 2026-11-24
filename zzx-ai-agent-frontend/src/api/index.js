import axios from 'axios'

// VITE_ variables are public build-time values and must never contain secrets.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ||
  '/api'

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  withCredentials: true
})

// Refresh requests use an isolated client so a failed refresh cannot recurse
// through the normal response interceptor.
const refreshRequest = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  withCredentials: true
})

let refreshPromise = null

const readCookie = (name) => {
  const prefix = encodeURIComponent(name) + '='
  const item = document.cookie
    .split('; ')
    .find(value => value.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : ''
}

// --- request interceptor: attach Bearer token -------------------
request.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }
  return config
})

// --- Auth API ----------------------------------------------------

export const register = (username, nickname, password, inviteCode = '') => {
  return request.post('/auth/register', {
    username,
    nickname,
    password,
    invite_code: inviteCode
  }).then(r => r.data)
}

export const redeemAdminInvite = (inviteCode) => {
  return request.post('/auth/invite/redeem', {
    invite_code: inviteCode
  }).then(r => r.data)
}

export const login = (username, password) => {
  return request.post('/auth/login', { username, password }).then(r => r.data)
}

export const refreshAccessToken = async () => {
  const csrfToken = readCookie('csrf_refresh_token')
  const response = await refreshRequest.post('/auth/refresh', {}, {
    headers: csrfToken ? { 'X-CSRF-TOKEN': csrfToken } : {}
  })
  const token = response.data?.data?.access_token || response.data?.data?.token
  if (!token) throw new Error('refresh response did not include an access token')
  localStorage.setItem('token', token)
  const currentUser = response.data?.data
  if (currentUser?.user_id) {
    const { token: _token, access_token: _accessToken, ...profile } = currentUser
    localStorage.setItem('user', JSON.stringify(profile))
  }
  return token
}

// Retry one ordinary API request after rotating the refresh token. Concurrent
// 401 responses share one refresh operation to avoid invalidating each other.
request.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config
    const isAuthEndpoint = original?.url?.startsWith('/auth/')
    if (error.response?.status !== 401 || original?._retry || isAuthEndpoint) {
      return Promise.reject(error)
    }

    original._retry = true
    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null
        })
      }
      const token = await refreshPromise
      original.headers = original.headers || {}
      original.headers.Authorization = 'Bearer ' + token
      return request(original)
    } catch (refreshError) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      return Promise.reject(refreshError)
    }
  }
)

export const logout = async () => {
  try {
    return await request.delete('/auth/logout').then(r => r.data)
  } finally {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }
}

export const logoutAll = async () => {
  try {
    return await request.delete('/auth/logout-all').then(r => r.data)
  } finally {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }
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

// --- RAG administration API ------------------------------------

export const listRagDocuments = () => {
  return request.get('/admin/rag/documents').then(r => r.data)
}

export const getRagDocument = (documentId) => {
  return request.get('/admin/rag/documents/' + documentId).then(r => r.data)
}

export const getRagDocumentChunks = (documentId) => {
  return request.get('/admin/rag/documents/' + documentId + '/chunks').then(r => r.data)
}

export const getRagIndexStatus = () => {
  return request.get('/admin/rag/index-status').then(r => r.data)
}

export const uploadRagDocument = (file, onUploadProgress) => {
  const form = new FormData()
  form.append('file', file)
  return request.post('/admin/rag/documents', form, {
    timeout: 300000,
    onUploadProgress
  }).then(r => r.data)
}

export const deleteRagDocument = (documentId) => {
  return request.delete('/admin/rag/documents/' + documentId, { timeout: 300000 }).then(r => r.data)
}

export const rebuildRagIndex = () => {
  return request.post('/admin/rag/rebuild', {}, { timeout: 300000 }).then(r => r.data)
}

// --- SSE helper --------------------------------------------------

export const connectSSE = (url, params, onMessage, onError) => {
  const queryString = Object.keys(params)
    .map(key => encodeURIComponent(key) + '=' + encodeURIComponent(params[key]))
    .join('&')

  const fullUrl = API_BASE_URL + url + '?' + queryString

  const abortController = new AbortController()
  const connection = {
    onmessage: onMessage
      ? event => onMessage(event.data)
      : null,
    onerror: onError || null,
    close: () => abortController.abort()
  }

  const dispatchEventBlock = block => {
    const eventType = block
      .split('\n')
      .find(line => line.startsWith('event:'))
      ?.slice(6).trim() || 'message'
    const data = block
      .split('\n')
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).replace(/^ /, ''))
      .join('\n')
    if (!data) return
    if (eventType === 'error') {
      let payload = {}
      try { payload = JSON.parse(data) } catch { payload = {} }
      const streamError = new Error(payload.message || '生成失败，请稍后重试')
      streamError.code = payload.code
      streamError.requestId = payload.request_id
      streamError.details = payload.details
      if (connection.onerror) connection.onerror(streamError)
      return
    }
    if (connection.onmessage) connection.onmessage({ data })
  }

  const openStream = async token => {
    return fetch(fullUrl, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        Authorization: 'Bearer ' + token
      },
      credentials: 'include',
      signal: abortController.signal
    })
  }

  Promise.resolve().then(async () => {
    try {
      let token = localStorage.getItem('token')
      let response = await openStream(token || '')
      if (response.status === 401) {
        token = await refreshAccessToken()
        response = await openStream(token)
      }
      if (!response.ok || !response.body) {
        let payload = {}
        try { payload = await response.json() } catch { payload = {} }
        const requestError = new Error(payload.message || '请求失败，请稍后重试')
        requestError.code = payload.code
        requestError.requestId = payload.request_id
        throw requestError
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
        buffer = buffer.replace(/\r\n/g, '\n')

        let boundary = buffer.indexOf('\n\n')
        while (boundary !== -1) {
          const block = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          dispatchEventBlock(block)
          boundary = buffer.indexOf('\n\n')
        }
        if (done) break
      }

      if (buffer.trim()) dispatchEventBlock(buffer)
    } catch (error) {
      if (error.name !== 'AbortError' && connection.onerror) {
        if (error.code || error.requestId) {
          connection.onerror(error)
        } else {
          const safeError = new Error('网络连接失败，请稍后重试')
          safeError.code = 'NETWORK_ERROR'
          connection.onerror(safeError)
        }
      }
    }
  })

  return connection
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
  chatWithManus,
  refreshAccessToken,
  logout,
  logoutAll
}
