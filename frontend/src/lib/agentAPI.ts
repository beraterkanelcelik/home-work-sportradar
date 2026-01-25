/**
 * Agent API client for agent definition management.
 */
import apiClient from './api'

export interface AgentDefinition {
  id: number
  name: string
  description?: string
  graph_config?: any
  is_active: boolean
  is_public: boolean
  metadata?: any
  created_at: string
  updated_at: string
  nodes?: AgentNode[]
  edges?: AgentEdge[]
}

export interface AgentNode {
  id: string
  type: 'agent' | 'tool' | 'supervisor' | 'router' | 'condition' | 'input' | 'output'
  config: any
  position: { x: number; y: number }
  requires_approval: boolean
  tool_configs?: AgentToolConfig[]
}

export interface AgentEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
  condition?: any
  priority?: number
}

export interface AgentToolConfig {
  tool_type: 'rag' | 'db' | 'web' | 'custom'
  tool_name: string
  config: any
  document_ids?: number[]
  input_schema?: any
  output_schema?: any
  requires_approval: boolean
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export interface ApprovalRequest {
  id: number
  chat_session_id: number
  agent_definition_id: number
  agent_definition_name: string
  node_id: string
  tool_name?: string
  request_data: any
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  responded_at?: string
}

export const agentAPI = {
  // List user's agents
  listAgents: async (): Promise<{ agents: AgentDefinition[] }> => {
    const response = await apiClient.get('/agents/')
    return response.data
  },

  // Get agent by ID
  getAgent: async (id: number): Promise<AgentDefinition> => {
    const response = await apiClient.get(`/agents/${id}/`)
    return response.data
  },

  // Create agent
  createAgent: async (data: Partial<AgentDefinition>): Promise<AgentDefinition> => {
    const response = await apiClient.post('/agents/', data)
    return response.data
  },

  // Update agent
  updateAgent: async (id: number, data: Partial<AgentDefinition>): Promise<AgentDefinition> => {
    const response = await apiClient.put(`/agents/${id}/`, data)
    return response.data
  },

  // Delete agent
  deleteAgent: async (id: number): Promise<void> => {
    await apiClient.delete(`/agents/${id}/`)
  },

  // Duplicate agent
  duplicateAgent: async (id: number, name?: string): Promise<AgentDefinition> => {
    const response = await apiClient.post(`/agents/${id}/duplicate/`, { name })
    return response.data
  },

  // Export agent
  exportAgent: async (id: number, format: 'json' | 'openapi' = 'json'): Promise<any> => {
    const response = await apiClient.get(`/agents/${id}/export/`, {
      params: { format }
    })
    return response.data
  },

  // Import agent
  importAgent: async (data: any, format: 'json' | 'openapi' = 'json'): Promise<AgentDefinition> => {
    const response = await apiClient.post('/agents/import/', {
      format,
      data
    })
    return response.data
  },

  // Validate agent
  validateAgent: async (id: number): Promise<ValidationResult> => {
    const response = await apiClient.post(`/agents/${id}/validate/`)
    return response.data
  },

  // List pending approvals
  listApprovals: async (): Promise<{ approvals: ApprovalRequest[] }> => {
    const response = await apiClient.get('/agents/approvals/')
    return response.data
  },

  // Respond to approval
  respondToApproval: async (id: number, status: 'approved' | 'rejected'): Promise<void> => {
    await apiClient.post(`/agents/approvals/${id}/respond/`, { status })
  },
}
