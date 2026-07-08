function defaultApiBaseUrl() {
  if (typeof window === 'undefined') return 'http://127.0.0.1:8000/api'
  const protocol = window.location.protocol || 'http:'
  const hostname = window.location.hostname || '127.0.0.1'
  const apiHost = hostname === '0.0.0.0' ? '127.0.0.1' : hostname
  return `${protocol}//${apiHost}:8000/api`
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl()
const AUTH_TOKEN_KEY = 'research-agent-auth-token'

function readAuthToken() {
  if (typeof localStorage === 'undefined') return ''
  return localStorage.getItem(AUTH_TOKEN_KEY) || ''
}

function writeAuthToken(token) {
  if (typeof localStorage === 'undefined') return
  if (token) localStorage.setItem(AUTH_TOKEN_KEY, token)
  else localStorage.removeItem(AUTH_TOKEN_KEY)
}

async function request(path, options = {}) {
  const authToken = readAuthToken()
  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { 'X-Research-Auth': authToken } : {}),
        ...(options.headers || {}),
      },
      ...options,
    })
  } catch (err) {
    throw new Error('无法连接后端服务或请求被中断，请确认 Django 后端正在 8000 端口运行后重试。')
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `请求失败：${response.status}`)
  }
  return payload
}

export default {
  baseUrl: BASE_URL,
  setAuthToken: writeAuthToken,
  clearAuthToken() {
    writeAuthToken('')
  },
  get(path) {
    return request(path)
  },
  post(path, body) {
    return request(path, {
      method: 'POST',
      body: JSON.stringify(body || {}),
    })
  },
  patch(path, body) {
    return request(path, {
      method: 'PATCH',
      body: JSON.stringify(body || {}),
    })
  },
  put(path, body) {
    return request(path, {
      method: 'PUT',
      body: JSON.stringify(body || {}),
    })
  },
  delete(path) {
    return request(path, {
      method: 'DELETE',
    })
  },
}
