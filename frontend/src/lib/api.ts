/**
 * API client for backend communication.
 */
import axios, { type AxiosInstance } from 'axios'

// Error type for API responses
export interface ApiError {
  response?: {
    data?: {
      error?: string
      message?: string
    }
    status?: number
  }
  message?: string
}

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add auth token to requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle token refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // TODO: Implement token refresh logic
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient

// API endpoints
export const authAPI = {
  signup: (data: { email: string; password: string; first_name?: string; last_name?: string }) =>
    apiClient.post('/auth/signup/', data),
  login: (data: { email: string; password: string }) =>
    apiClient.post('/auth/login/', data),
  refresh: (refreshToken: string) =>
    apiClient.post('/auth/refresh/', { refresh: refreshToken }),
  logout: () => apiClient.post('/auth/logout/'),
  changePassword: (data: { old_password: string; new_password: string }) =>
    apiClient.post('/auth/change-password/', data),
}

export const userAPI = {
  getCurrentUser: () => apiClient.get('/users/me/'),
  updateCurrentUser: (data: { first_name?: string; last_name?: string; email?: string }) => apiClient.put('/users/me/update/', data),
  getUserStats: () => apiClient.get('/users/me/stats/'),
  getApiKeysStatus: () => apiClient.get('/users/me/api-keys/'),
  updateApiKeys: (data: {
    openai_api_key?: string | null
    langfuse_public_key?: string | null
    langfuse_secret_key?: string | null
  }) => apiClient.put('/users/me/api-keys/update/', data),
  clearApiKeys: () => apiClient.delete('/users/me/api-keys/clear/'),
}


export const healthAPI = {
  async getHealthStatus() {
    const response = await apiClient.get('/health/')
    return response.data
  },
}

export const chatAPI = {
  getSessions: () => apiClient.get('/chats/'),
  createSession: (data?: { title?: string }) => apiClient.post('/chats/', data),
  getSession: (sessionId: number) => apiClient.get(`/chats/${sessionId}/`),
  updateSession: (sessionId: number, data: { model_used?: string; title?: string; agent_definition?: number | null }) =>
    apiClient.patch(`/chats/${sessionId}/`, data),
  updateSessionModel: (sessionId: number, modelName: string) =>
    apiClient.patch(`/chats/${sessionId}/`, { model_used: modelName }),
  updateSessionTitle: (sessionId: number, title: string) =>
    apiClient.patch(`/chats/${sessionId}/`, { title }),
  getMessages: (sessionId: number) =>
    apiClient.get(`/chats/${sessionId}/messages/`),
  sendMessage: (sessionId: number, message: string) =>
    apiClient.post(`/chats/${sessionId}/messages/`, { content: message }),
  deleteSession: (sessionId: number) => apiClient.delete(`/chats/${sessionId}/`),
  deleteAllSessions: () => apiClient.delete('/chats/delete-all/'),
  getStats: (sessionId: number) => apiClient.get(`/chats/${sessionId}/stats/`),
  
  // UI message persistence (for status updates, plans, progress - excluded from LLM context)
  saveUiMessage: (sessionId: number, data: {
    role: 'system' | 'assistant'
    content: string
    metadata: {
      type: 'status' | 'plan_proposal' | 'plan_progress' | 'player_preview'
      plan?: Record<string, any>
      plan_progress?: Record<string, any>
      [key: string]: any
    }
  }) => apiClient.post(`/chats/${sessionId}/ui-message/`, data),
  
  updateUiMessage: (sessionId: number, messageId: number, data: {
    content?: string
    metadata?: Record<string, any>
  }) => apiClient.put(`/chats/${sessionId}/ui-message/${messageId}/`, data),
}

export const documentAPI = {
  getDocuments: () => apiClient.get('/documents/'),
  getDocument: (documentId: number) => apiClient.get(`/documents/${documentId}/`),
  getDocumentChunks: (documentId: number) => apiClient.get(`/documents/${documentId}/chunks/`),
  uploadDocument: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/documents/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  deleteDocument: (documentId: number) =>
    apiClient.delete(`/documents/${documentId}/`),
  indexDocument: (documentId: number) =>
    apiClient.post(`/documents/${documentId}/index/`),
}

export const agentAPI = {
  streamAgent: (data: { 
    chat_session_id: number
    message: string
  }) =>
    apiClient.post('/agent/stream/', data, {
      responseType: 'stream',
    }),
  // URL for opening SSE stream to listen for resumed workflow events
  getStreamResumeUrl: (chatSessionId: number) =>
    `${API_URL}/api/agent/stream-resume/?chat_session_id=${chatSessionId}`,
  approveTool: (data: {
    chat_session_id: number
    resume: {
      approvals: Record<string, {
        approved: boolean
        args?: Record<string, any>
      }>
    }
  }) =>
    apiClient.post('/agent/approve-tool/', data),
  approvePlayer: (data: {
    chat_session_id: number
    resume: {
      action: 'approve' | 'reject' | 'edit_wording' | 'edit_content'
      feedback?: string
    }
  }) =>
    apiClient.post('/agent/approve-player/', data),
  approvePlan: (data: {
    chat_session_id: number
    resume: {
      approved: boolean
      reason?: string
    }
  }) =>
    apiClient.post('/agent/approve-plan/', data),
  listScoutReports: () => apiClient.get('/scout-reports/'),
  deleteScoutReport: (reportId: string) => apiClient.delete(`/scout-reports/${reportId}/`),
  deleteAllScoutReports: () => apiClient.delete('/scout-reports/delete-all/'),
}

export const modelsAPI = {
  getAvailableModels: () => apiClient.get('/models/'),
}
