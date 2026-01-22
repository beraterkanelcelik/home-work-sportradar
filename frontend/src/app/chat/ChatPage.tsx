/**
 * ChatPage Component
 * 
 * Main chat interface orchestrating all chat-related components.
 * 
 * Architecture:
 * - Uses Temporal workflows for durability (equivalent to LangGraph's checkpointing)
 * - Uses Redis for real-time streaming (equivalent to LangGraph's streaming)
 * - Custom HITL mechanism bridges Temporal signals with LangGraph's tool approval flow
 * 
 * The review pattern follows LangGraph's interrupt() -> Command() flow:
 * 1. Tool requires approval -> Workflow pauses (interrupt equivalent)
 * 2. Frontend shows review UI with tool details
 * 3. User approves -> Sends signal (Command equivalent)
 * 4. Workflow resumes with approved tool result
 * 
 * Component Organization:
 * - ChatSidebar: Session list and management (frontend/src/components/chat/ChatSidebar.tsx)
 * - ChatHeader: Model selection and menu (frontend/src/components/chat/ChatHeader.tsx)
 * - MessageList: Messages container (frontend/src/components/chat/MessageList.tsx)
 * - MessageItem: Individual message rendering (frontend/src/components/chat/MessageItem.tsx)
 * - ToolCallItem: Tool call display with approval (frontend/src/components/chat/ToolCallItem.tsx)
 * - ChatInput: Input area with file attachments (frontend/src/components/chat/ChatInput.tsx)
 * - StatsDialog: Statistics modal (frontend/src/components/chat/StatsDialog.tsx)
 * - DeleteDialogs: Delete confirmation dialogs (frontend/src/components/chat/DeleteDialogs.tsx)
 * 
 * Hooks:
 * - useToolApproval: Tool approval logic (frontend/src/hooks/useToolApproval.ts)
 * - useSessionManagement: Session CRUD operations (frontend/src/hooks/useSessionManagement.ts)
 * 
 * Location: frontend/src/app/chat/ChatPage.tsx
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useChatStore, type Message } from '@/state/useChatStore'
import { useAuthStore } from '@/state/useAuthStore'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { createAgentStream, createResumeStream, StreamEvent, SSEResumeStream } from '@/lib/streaming'
import { chatAPI, agentAPI, documentAPI, modelsAPI } from '@/lib/api'
import { getErrorMessage } from '@/lib/utils'
import { generateTempMessageId, generateTempStatusMessageId } from '@/constants/messages'

// Import extracted components
import ChatSidebar from '@/components/chat/ChatSidebar'
import ChatHeader from '@/components/chat/ChatHeader'
import MessageList from '@/components/chat/MessageList'
import ChatInput from '@/components/chat/ChatInput'
import StatsDialog from '@/components/chat/StatsDialog'
import DeleteDialogs from '@/components/chat/DeleteDialogs'
import PlanPanel from '@/components/chat/PlanPanel'
import { useToolApproval } from '@/hooks/useToolApproval'
import { usePlanApproval } from '@/hooks/usePlanApproval'
import { usePlayerApproval } from '@/hooks/usePlayerApproval'
import { useUiMessagePersistence } from '@/hooks/useUiMessagePersistence'


export default function ChatPage() {
  // ============================================================================
  // ROUTING & NAVIGATION
  // ============================================================================
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================
  // Note: Most UI state is managed here, but some is delegated to components
  // - ChatSidebar manages its own session menu state (passed as props)
  // - ChatHeader manages its own dropdown state (internal)
  // - ChatInput manages its own plus menu state (internal)
  
  // Input state
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [inputFocused, setInputFocused] = useState(false)
  const [attachedFiles, setAttachedFiles] = useState<File[]>([])
  const [selectedOptions, setSelectedOptions] = useState<Array<{type: string, label: string, icon?: React.ReactNode, data?: any}>>([])
  
  // UI state
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [chatsSectionOpen, setChatsSectionOpen] = useState(true)
  const [sessionMenuOpen, setSessionMenuOpen] = useState<number | null>(null)
  const [renameSessionId, setRenameSessionId] = useState<number | null>(null)
  const [renameSessionTitle, setRenameSessionTitle] = useState<string>('')
  
  // Dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [sessionToDelete, setSessionToDelete] = useState<number | null>(null)
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false)
  const [statsDialogOpen, setStatsDialogOpen] = useState(false)
  const [stats, setStats] = useState<any>(null)
  const [loadingStats, setLoadingStats] = useState(false)
  
  // Message & streaming state
  const [waitingForResponse, setWaitingForResponse] = useState(false)
  const [waitingMessageId, setWaitingMessageId] = useState<number | null>(null)
  const [streamComplete, setStreamComplete] = useState<Set<number>>(new Set()) // Track which messages have completed streaming
  const [expandedToolCalls, setExpandedToolCalls] = useState<Set<string>>(new Set())
  const [executingPlanMessageId, setExecutingPlanMessageId] = useState<number | null>(null)
  
  // Plan panel state
  const [planPanelCollapsed, setPlanPanelCollapsed] = useState(false)
  const [showPlanPanel, setShowPlanPanel] = useState(true)
  // Track which plans have been approved (prevents buttons from reappearing after loadMessages)
  const [approvedPlanMessageIds, setApprovedPlanMessageIds] = useState<Set<number>>(new Set())
  // Track which plans have completed execution
  const [completedPlanMessageIds, setCompletedPlanMessageIds] = useState<Set<number>>(new Set())
  
  // Stats dialog state
  const [expandedActivities, setExpandedActivities] = useState<string[]>([])
  const [expandedChains, setExpandedChains] = useState<string[]>([])
  
  // Model selection state
  const [selectedModel, setSelectedModel] = useState<string>('gpt-4o-mini')
  const [availableModels, setAvailableModels] = useState<Array<{id: string, name: string, description: string}>>([])
  
  // Refs for streaming
  const processedInterruptsRef = useRef<Set<string>>(new Set())
  const streamRef = useRef<ReturnType<typeof createAgentStream> | null>(null)
  const resumeStreamRef = useRef<SSEResumeStream | null>(null)
  const initialMessageSentRef = useRef(false)
  const initialMessageRef = useRef<string | null>(null)

  const { user } = useAuthStore()
  const {
    sessions,
    currentSession,
    messages,
    loading,
    error,
    loadSessions,
    createSession,
    loadSession,
    loadMessages,
    deleteSession,
    deleteAllSessions,
    clearCurrentSession,
    set,
  } = useChatStore()

  useEffect(() => {
    // Load sessions list on mount, but don't reload if already loaded
    if (sessions.length === 0) {
      loadSessions()
    }
    
    // Load available models from backend
    const loadModels = async () => {
      try {
        const response = await modelsAPI.getAvailableModels()
        setAvailableModels(response.data.models || [])
        // Set default model if none selected
        if (response.data.models && response.data.models.length > 0 && !selectedModel) {
          setSelectedModel(response.data.models[0].id)
        }
      } catch (error: unknown) {
        toast.error(getErrorMessage(error, 'Failed to load models'))
      }
    }
    loadModels()
  }, [loadSessions, selectedModel]) // Only run once on mount

  // Store initial message from location state when component mounts or sessionId changes
  useEffect(() => {
    // Reset refs when sessionId changes
    initialMessageSentRef.current = false
    initialMessageRef.current = null
    
    const state = location.state as { initialMessage?: string } | null
    if (state?.initialMessage) {
      initialMessageRef.current = state.initialMessage
      // Clear the location state immediately to prevent re-triggering
      window.history.replaceState({ ...window.history.state, state: null }, '')
    }
  }, [sessionId])

  useEffect(() => {
    if (sessionId) {
      const sessionIdNum = Number(sessionId)
      // Only load session if it's not already loaded or if it's a different session
      if (!currentSession || currentSession.id !== sessionIdNum) {
        loadSession(sessionIdNum)
      } else {
        // Session is already loaded, but ensure messages are loaded
        loadMessages(sessionIdNum)
      }
      initialMessageSentRef.current = false
    } else {
      clearCurrentSession()
      // Clear stream complete flags when clearing session
      setStreamComplete(new Set())
    }
  }, [sessionId, loadSession, loadMessages, clearCurrentSession, currentSession])
  
  // Mark all loaded messages from database as stream complete (they're already finished)
  // Only run when session changes to avoid unnecessary updates
  useEffect(() => {
    if (currentSession && messages.length > 0) {
      setStreamComplete(prev => {
        const newSet = new Set(prev)
        messages.forEach(msg => {
          // Mark assistant messages from DB (positive IDs) as stream complete
          // Temporary messages (negative IDs) are still streaming
          if (msg.role === 'assistant' && msg.id > 0 && msg.id < 1000000000000) {
            newSet.add(msg.id)
          }
        })
        return newSet
      })
    }
  }, [currentSession?.id]) // Only run when session changes

  // Sync selected model with session model
  useEffect(() => {
    if (currentSession?.model_used) {
      setSelectedModel(currentSession.model_used)
    } else {
      setSelectedModel('gpt-4o-mini') // Default
    }
  }, [currentSession?.model_used])

  const handleModelChange = async (modelId: string) => {
    if (!currentSession || modelId === selectedModel) return
    
    try {
      await chatAPI.updateSessionModel(currentSession.id, modelId)
      setSelectedModel(modelId)
      // Update currentSession in store
      if (currentSession) {
        const updatedSession = { ...currentSession, model_used: modelId }
        set({ currentSession: updatedSession })
      }
      // Note: ChatHeader manages its own dropdown state, so no need to close it here
      toast.success(`Model changed to ${availableModels.find(m => m.id === modelId)?.name || modelId}`)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to update model'))
    }
  }

  // ============================================================================
  // STREAMING LOGIC
  // ============================================================================
  // Location: Complex streaming logic for SSE (Server-Sent Events)
  // This function handles:
  // - Creating streaming connections
  // - Processing stream events (token, update, done, error, interrupt, final, heartbeat)
  // - Managing message state during streaming
  // - Handling tool approval interrupts (HITL)
  // - Status message creation/updates
  // 
  // Note: This is the most complex part of ChatPage (~750 lines)
  // Future improvement: Could be extracted to useChatStreaming hook
  const handleSendWithMessage = useCallback(async (messageContent: string) => {
    if (!messageContent.trim() || sending || !currentSession) return

    const content = messageContent.trim()
    setSending(true)

    // Add user message immediately
    const tempUserMessageId = generateTempMessageId()
    const userMessage = {
      id: tempUserMessageId,
      role: 'user' as const,
      content,
      tokens_used: 0,
      created_at: new Date().toISOString(),
    }
    set((state: { messages: Message[] }) => ({
      messages: [...state.messages, userMessage],
    }))

    try {
      const token = localStorage.getItem('access_token')
      if (!token) {
        throw new Error('No authentication token')
      }

      {
        // Clear processed interrupts for new message stream
        processedInterruptsRef.current.clear()
        // Also clear any stale approving states from previous message
        setApprovingToolCalls(new Set())
        
        // Clear any old temporary status messages before starting a new stream
        // They are ephemeral and should not persist across different streams
        set((state: { messages: Message[] }) => ({
          messages: state.messages.filter(
            (msg: Message) => !(msg.id < 0 && msg.role === 'system' && msg.metadata?.status_type === 'task_status')
          )
        }))
        
        // Create streaming message placeholder
        const assistantMessageId = Date.now() + 1
        setWaitingForResponse(true)
        setWaitingMessageId(assistantMessageId)
        // Reset stream complete flag for this new message
        setStreamComplete(prev => {
          const newSet = new Set(prev)
          newSet.delete(assistantMessageId) // Remove if it exists (shouldn't, but just in case)
          return newSet
        })
        
        
        set((state: { messages: Message[] }) => ({
          messages: [
            ...state.messages,
            {
              id: assistantMessageId,
              role: 'assistant' as const,
              content: '',
              tokens_used: 0,
              created_at: new Date().toISOString(),
              metadata: { agent_name: 'greeter' },
            },
          ],
        }))

        // Use streaming
        let tokenBatchCount = 0
        let lastTokenLogTime = Date.now()
        const streamStartTime = Date.now()
        const eventTypeCounts: Record<string, number> = {}
        
        console.log(`[FRONTEND] [STREAM_START] Starting agent stream session=${currentSession.id} message_preview=${content.substring(0, 50)}...`)
        
        const stream = createAgentStream(
          currentSession.id,
          content,
          token,
          async (event: StreamEvent) => {
            const eventType = event.type
            eventTypeCounts[eventType] = (eventTypeCounts[eventType] || 0) + 1
            
            // Log critical human-in-the-loop events (aligned with LangGraph interrupt pattern)
            // Reference: https://docs.langchain.com/oss/python/langgraph/use-functional-api#review-tool-calls
            // This is the equivalent of LangGraph's interrupt() in our Temporal + Redis architecture
            if (eventType === 'update' && event.data?.type === 'tool_approval_required') {
              console.log(`[HITL] [REVIEW] Stream event: tool_approval_required (interrupt equivalent) session=${currentSession.id}`, event.data)
            }
            
            // Handle message_saved event to update temporary IDs with real DB IDs
            if (eventType === 'message_saved') {
              const savedData = event.data || {}
              const role = savedData.role
              const dbId = savedData.db_id
              const sessionId = savedData.session_id
              
              if (sessionId === currentSession.id && dbId) {
                set((state: { messages: Message[] }) => {
                  // Find temporary message by role and update its ID
                  // For user messages, find the most recent user message with a temporary ID
                  // For assistant messages, find the message with the temporary assistantMessageId
                  const updatedMessages = state.messages.map((msg: Message) => {
                    if (role === 'user' && msg.role === 'user' && msg.id === tempUserMessageId) {
                      return { ...msg, id: dbId }
                    } else if (role === 'assistant' && msg.role === 'assistant' && msg.id === assistantMessageId) {
                      return { ...msg, id: dbId }
                    }
                    return msg
                  })
                  
                  return { messages: updatedMessages }
                })
              }
              return // Don't process message_saved as a regular event
            }
            
            if (eventType === 'token') {
              tokenBatchCount++
              
              // Log first token and periodic token batches
              if (tokenBatchCount === 1) {
                const timeToFirstToken = Date.now() - streamStartTime
                console.log(`[FRONTEND] [STREAM] First token received session=${currentSession.id} time_to_first_token=${timeToFirstToken}ms`)
              } else if (tokenBatchCount % 50 === 0) {
                const elapsed = Date.now() - streamStartTime
                console.log(`[FRONTEND] [STREAM] Token batch: ${tokenBatchCount} tokens received session=${currentSession.id} elapsed=${elapsed}ms`)
              }
              
              // First token received, hide loading indicator
              setWaitingForResponse(false)
              setWaitingMessageId(null)
              
              // Update the assistant message in store by appending the new token
              // Keep status until we have substantial content
              set((state: { messages: Message[] }) => {
                const currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)
                if (!currentMessage) {
                  return state // Message was removed, skip update
                }
                
                const currentContent = currentMessage.content || ''
                const tokenData = event.data || ''
                const newContent = currentContent + tokenData
                
                return {
                  messages: state.messages.map((msg: Message) =>
                    msg.id === assistantMessageId
                      ? { 
                          ...msg, 
                          content: newContent,
                          // Clear status only when we have substantial content (more than 50 chars)
                          status: newContent.length > 50 ? undefined : msg.status
                        }
                      : msg
                  ),
                }
              })
            } else if (eventType === 'update') {
              // Handle workflow state updates (agent_name, tool_calls, plan_proposal, status, etc.)
              const updateData = event.data || {}
              
              // Log update events with key information
              if (updateData.agent_name) {
                console.log(`[FRONTEND] [UPDATE] Agent name updated: agent=${updateData.agent_name} session=${currentSession.id}`)
              }
              if (updateData.tool_calls && Array.isArray(updateData.tool_calls)) {
                const toolCallCount = updateData.tool_calls.length
                const pendingCount = updateData.tool_calls.filter((tc: any) => tc.status === 'pending').length
                console.log(`[FRONTEND] [UPDATE] Tool calls updated: total=${toolCallCount} pending=${pendingCount} session=${currentSession.id}`)
              }
              
              // Human-in-the-Loop Tool Review (aligned with LangGraph best practices)
              // Reference: https://docs.langchain.com/oss/python/langgraph/use-functional-api#review-tool-calls
              // This handles the "interrupt" equivalent in our Temporal + Redis architecture
              // When a tool requires approval, the workflow pauses and waits for human review
              if (updateData.type === 'tool_approval_required' && updateData.tool_info) {
                const toolInfo = updateData.tool_info
                console.log(`[HITL] [REVIEW] Received tool_approval_required event (interrupt equivalent): tool=${toolInfo.tool} tool_call_id=${toolInfo.tool_call_id} session=${currentSession?.id} args=`, toolInfo.args)
                
                // Update the assistant message to mark the tool as pending
                set((state: { messages: Message[] }) => {
                  const currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)
                  if (!currentMessage) {
                    console.warn(`[HITL] Could not find assistant message with id=${assistantMessageId} for tool_approval_required event`)
                    return state
                  }
                  
                  const existingToolCalls = currentMessage.metadata?.tool_calls || []
                  const toolCallExists = existingToolCalls.some((tc: any) => 
                    (tc.id === toolInfo.tool_call_id) || 
                    (tc.name === toolInfo.tool || tc.tool === toolInfo.tool)
                  )
                  
                  if (!toolCallExists) {
                    // Add new tool call with pending status
                    console.log(`[HITL] Adding new pending tool call to message: tool=${toolInfo.tool} tool_call_id=${toolInfo.tool_call_id}`)
                    const newToolCall = {
                      id: toolInfo.tool_call_id,
                      name: toolInfo.tool,
                      tool: toolInfo.tool,
                      args: toolInfo.args || {},
                      status: 'pending',
                      requires_approval: true
                    }
                    
                    return {
                      messages: state.messages.map((msg: Message) =>
                        msg.id === assistantMessageId
                          ? {
                              ...msg,
                              metadata: {
                                ...msg.metadata,
                                tool_calls: [...existingToolCalls, newToolCall]
                              }
                            }
                          : msg
                      ),
                    }
                  } else {
                    // Update existing tool call to pending (for review - aligned with LangGraph pattern)
                    console.log(`[HITL] [REVIEW] Updating existing tool call to pending for review: tool=${toolInfo.tool} tool_call_id=${toolInfo.tool_call_id}`)
                    return {
                      messages: state.messages.map((msg: Message) =>
                        msg.id === assistantMessageId
                          ? {
                              ...msg,
                              metadata: {
                                ...msg.metadata,
                                tool_calls: existingToolCalls.map((tc: any) => {
                                  if ((tc.id === toolInfo.tool_call_id) || 
                                      (tc.name === toolInfo.tool || tc.tool === toolInfo.tool)) {
                                    return {
                                      ...tc,
                                      id: toolInfo.tool_call_id,
                                      status: 'pending',
                                      requires_approval: true
                                    }
                                  }
                                  return tc
                                })
                              }
                            }
                          : msg
                      ),
                    }
                  }
                })
              }

              // Handle task status updates - create/update system status messages in real-time
              // BUT: Stop updating status messages once answer tokens start arriving
              if (updateData.task && updateData.status) {
                set((state: { messages: Message[] }) => {
                  // Check if assistant message already has content (tokens have started arriving)
                  const assistantMsg = state.messages.find((msg: Message) => msg.id === assistantMessageId)
                  const hasAnswerTokens = assistantMsg?.content && assistantMsg.content.trim().length > 0
                  
                  // If answer tokens have started, don't update status messages anymore
                  // They should remain frozen at their last state
                  if (hasAnswerTokens) {
                    return state
                  }
                  
                  // Check if status message already exists for this task (check both temp and DB messages)
                  const existingStatusMsg = state.messages.find(
                    (msg: Message) => 
                      msg.role === 'system' && 
                      msg.metadata?.status_type === 'task_status' &&
                      msg.metadata?.task === updateData.task
                  )
                  
                  if (existingStatusMsg) {
                    // Update existing status message (present -> past tense)
                    return {
                      messages: state.messages.map((msg: Message) =>
                        msg.id === existingStatusMsg.id
                          ? {
                              ...msg,
                              content: updateData.status,
                              metadata: {
                                ...msg.metadata,
                                is_completed: updateData.is_completed === true
                              }
                            }
                          : msg
                      ),
                    }
                  } else {
                    // Create new status message with unique temporary ID
                    // Use negative ID to avoid conflicts with database IDs
                    const tempId = generateTempStatusMessageId()
                    const newStatusMessage: Message = {
                      id: tempId,
                      role: 'system',
                      content: updateData.status,
                      tokens_used: 0,
                      created_at: new Date().toISOString(),
                      metadata: {
                        task: updateData.task,
                        status_type: 'task_status',
                        is_completed: updateData.is_completed === true || false
                      }
                    }
                    
                    // Insert before the assistant message
                    const assistantIndex = state.messages.findIndex((msg: Message) => msg.id === assistantMessageId)
                    if (assistantIndex >= 0) {
                      const newMessages = [...state.messages]
                      newMessages.splice(assistantIndex, 0, newStatusMessage)
                      return { messages: newMessages }
                    } else {
                      return { messages: [...state.messages, newStatusMessage] }
                    }
                  }
                })
              }
              
              set((state: { messages: Message[] }) => {
                const currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)
                if (!currentMessage) {
                  return state
                }
                
                const updatedMetadata = {
                  ...currentMessage.metadata,
                  ...(updateData.agent_name && { agent_name: updateData.agent_name }),
                }
                
                // Handle tool calls during streaming - they appear immediately as they're added
                // Tool calls are shown in chronological order as events come in
                let updatedToolCalls = currentMessage.metadata?.tool_calls || []
                
                if (updateData.tool_calls) {
                  // Direct tool_calls array update - tool calls appear immediately
                  const pendingTools = (updateData.tool_calls || []).filter((tc: any) => tc.status === 'pending' && tc.requires_approval)
                  if (pendingTools.length > 0) {
                    console.log(`[HITL] Received tool_calls with ${pendingTools.length} pending tools requiring approval:`, pendingTools.map((tc: any) => ({ tool: tc.name || tc.tool, tool_call_id: tc.id, status: tc.status })))
                  }
                  updatedMetadata.tool_calls = updateData.tool_calls
                } else if (updateData.tool && updateData.status) {
                  // During streaming, track tool status updates (Executing -> Executed)
                  // But don't create tool_calls array yet - tool items will only appear after stream completes
                  // Status updates are fine, but tool items (collapsible boxes) should wait
                }
                
                // Check if this is a plan_proposal response
                const updates: Partial<Message> = {
                  metadata: updatedMetadata,
                }
                
                // Update general status if provided (for task execution status, not tool-specific)
                // Only set general status if it's not a tool-specific update
                if (updateData.status && !updateData.tool) {
                  updates.status = updateData.status
                }
                
                if (updateData.type === 'plan_proposal' && updateData.plan) {
                  updates.response_type = 'plan_proposal'
                  updates.plan = updateData.plan
                }

                if (updateData.type === 'coverage_report' && updateData.coverage) {
                  updates.response_type = 'coverage_report'
                  updates.coverage_report = updateData.coverage
                }

                // Handle plan step progress updates (for scouting workflow real-time progress)
                // NOTE: Only store progress when total_steps > 0 (after plan is generated)
                // Pre-plan steps (analyzing, identifying, drafting) have total_steps=0 and should NOT be stored
                // because they would cause isApproved to be incorrectly true
                if (updateData.type === 'plan_step_progress') {
                  console.log(`[FRONTEND] [PLAN_PROGRESS] Step ${updateData.step_index + 1}/${updateData.total_steps}: ${updateData.status} - ${updateData.step_name}`)
                  
                  // Skip pre-plan progress (total_steps=0 means plan hasn't been generated yet)
                  if (updateData.total_steps > 0) {
                    // Update the plan with step progress
                    if (!updates.plan_progress) {
                      updates.plan_progress = {}
                    }
                    updates.plan_progress = {
                      ...updates.plan_progress,
                      current_step_index: updateData.step_index,
                      total_steps: updateData.total_steps,
                      steps_status: {
                        ...(updates.plan_progress?.steps_status || {}),
                        [updateData.step_index]: {
                          status: updateData.status,
                          step_name: updateData.step_name,
                          result: updateData.result,
                        }
                      }
                    }
                  }
                }

                if (updateData.type === 'player_preview' && updateData.player_preview) {
                  updates.response_type = 'player_preview'
                  updates.player_preview = updateData.player_preview
                }

                if (updateData.clarification) {
                  updates.clarification = updateData.clarification
                }
                
                return {
                  messages: state.messages.map((msg: Message) =>
                    msg.id === assistantMessageId
                      ? { ...msg, ...updates }
                      : msg
                  ),
                }
              })
            } else if (eventType === 'done') {
              // Handle completion event with final data
              // tool_calls are sent via update event (before done event), we just mark stream as complete
              const doneData = event.data || {}
              const duration = Date.now() - streamStartTime
              // Mark stream as complete for this message
              // Tool calls are already visible (shown immediately as they come in)
              if (assistantMessageId) {
                setStreamComplete(prev => new Set(prev).add(assistantMessageId))
              }
              
              set((state: { messages: Message[] }) => {
                return {
                  messages: state.messages.map((msg: Message) =>
                    msg.id === assistantMessageId
                      ? {
                          ...msg,
                          ...(doneData.tokens_used && { tokens_used: doneData.tokens_used }),
                          ...(doneData.raw_tool_outputs && { raw_tool_outputs: doneData.raw_tool_outputs }),
                          ...(doneData.context_usage && { context_usage: doneData.context_usage }),
                          // Extract agent_name from done event (backend sends "agent" key)
                          ...(doneData.agent && {
                            metadata: {
                              ...msg.metadata,
                              agent_name: doneData.agent,
                            },
                          }),
                        }
                      : msg
                  ),
                }
              })
              
              // Mark all active temporary status messages as completed
              // This ensures they show as past tense even if on_chain_end events haven't fired yet
              set((state: { messages: Message[] }) => {
                return {
                  messages: state.messages.map((msg: Message) => {
                    // Update any active temporary status messages to completed
                    if (msg.id < 0 && 
                        msg.role === 'system' && 
                        msg.metadata?.status_type === 'task_status' &&
                        msg.metadata?.is_completed === false) {
                      // Convert to past tense
                      const pastTenseMap: Record<string, string> = {
                        "Processing with agent...": "Processed with agent",
                        "Routing to agent...": "Routed to agent",
                        "Loading conversation history...": "Loaded conversation history",
                        "Processing with greeter agent...": "Processed with greeter agent",
                        "Searching documents...": "Searched documents",
                        "Executing tools...": "Executed tools",
                        "Processing tool results...": "Processed tool results",
                        "Checking if summarization needed...": "Checked if summarization needed",
                        "Saving message...": "Saved message",
                      }
                      const pastContent = pastTenseMap[msg.content] || msg.content.replace(/ing\.\.\.$/, "ed").replace(/ing$/, "ed")
                      return {
                        ...msg,
                        content: pastContent,
                        metadata: {
                          ...msg.metadata,
                          is_completed: true
                        }
                      }
                    }
                    return msg
                  })
                }
              })
            } else if (eventType === 'plan_step_progress') {
              // Handle plan step progress events from scouting workflow
              // NOTE: Only store progress when total_steps > 0 (after plan is generated)
              // Pre-plan steps (analyzing, identifying, drafting) have total_steps=0 and should NOT be stored
              const progressData = event.data || {}
              console.log(`[FRONTEND] [PLAN_PROGRESS] Step ${progressData.step_index + 1}/${progressData.total_steps}: ${progressData.status} - ${progressData.step_name}`)
              
              // Skip pre-plan progress (total_steps=0 means plan hasn't been generated yet)
              if (progressData.total_steps > 0) {
                set((state: { messages: Message[] }) => {
                  const currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)
                  if (!currentMessage) {
                    return state
                  }
                  
                  const currentProgress = currentMessage.plan_progress || {
                    current_step_index: -1,
                    total_steps: progressData.total_steps || 0,
                    steps_status: {}
                  }
                  
                  const updatedProgress = {
                    ...currentProgress,
                    current_step_index: progressData.status === 'in_progress' ? progressData.step_index : currentProgress.current_step_index,
                    total_steps: progressData.total_steps || currentProgress.total_steps,
                    steps_status: {
                      ...currentProgress.steps_status,
                      [progressData.step_index]: {
                        status: progressData.status,
                        step_name: progressData.step_name,
                        result: progressData.result,
                      }
                    }
                  }
                  
                  return {
                    messages: state.messages.map((msg: Message) =>
                      msg.id === assistantMessageId
                        ? {
                            ...msg,
                            plan_progress: updatedProgress
                          }
                        : msg
                    ),
                }
              })
              
              // Persist plan progress to backend (debounced - only update on step completion)
              if (progressData.status === 'completed' || progressData.status === 'error') {
                // Build progress object from current state
                const updatedProgress = {
                  current_step_index: progressData.step_index,
                  total_steps: progressData.total_steps,
                  steps_status: {
                    [progressData.step_index]: {
                      status: progressData.status,
                      step_name: progressData.step_name,
                      result: progressData.result,
                    }
                  }
                }
                updatePlanProgress(assistantMessageId, updatedProgress).catch(err => {
                  console.error('[UI_PERSIST] Failed to update plan progress:', err)
                })
              }
              } // End of if (progressData.total_steps > 0)
            } else if (eventType === 'error') {
              const errorData = event.data || {}
              const duration = Date.now() - streamStartTime
              console.error(`[FRONTEND] Error event received session=${currentSession.id} duration=${duration}ms error=${errorData.error || 'unknown'}`)
              
              toast.error(errorData.error || 'Streaming error occurred')
              setSending(false)
              setWaitingForResponse(false)
              setWaitingMessageId(null)
            } else if (eventType === 'interrupt') {
              // LangGraph native interrupt pattern - workflow paused for approval
              // Connection remains open but with shorter timeout (5 min) for scalability
              // This balances resource usage with UX (no reconnection needed)
              console.log(`[HITL] [INTERRUPT] Workflow interrupted - connection will timeout after 5 minutes if no resume session=${currentSession.id}`)
              
              // Extract interrupt payload - handle multiple formats from backend
              const interruptData = event.data || event.interrupt
              let interruptValue: any = null

              console.log(`[HITL] [DEBUG] Raw interrupt data:`, interruptData, `isArray=${Array.isArray(interruptData)} type=${typeof interruptData}`)

              // Handle different interrupt data formats:
              // 1. Array format: [{value: {...}, resumable: true, ns: [...]}]
              // 2. Tuple format: (Interrupt(value={...}, id='...'),) - Python tuple serialized
              // 3. Direct Interrupt object: {value: {...}, id: '...'}
              if (interruptData) {
                if (Array.isArray(interruptData) && interruptData.length > 0) {
                  // Array format - extract value from first element
                  const firstItem = interruptData[0]
                  console.log(`[HITL] [DEBUG] Array format, firstItem:`, firstItem)
                  if (firstItem?.value) {
                    interruptValue = firstItem.value
                    console.log(`[HITL] [DEBUG] Extracted from firstItem.value:`, interruptValue)
                  } else if (firstItem?.type === 'tool_approval' || firstItem?.type === 'plan_approval') {
                    // Direct value in array
                    interruptValue = firstItem
                    console.log(`[HITL] [DEBUG] Using firstItem directly (type=${firstItem?.type}):`, interruptValue)
                  }
                } else if (typeof interruptData === 'object') {
                  // Direct object - could be Interrupt object with .value or direct payload
                  console.log(`[HITL] [DEBUG] Object format, has value=${!!interruptData.value} type=${interruptData.type}`)
                  if (interruptData.value) {
                    interruptValue = interruptData.value
                    console.log(`[HITL] [DEBUG] Extracted from interruptData.value:`, interruptValue)
                  } else if (interruptData.type === 'tool_approval' || interruptData.type === 'plan_approval' || interruptData.type === 'player_approval') {
                    interruptValue = interruptData
                    console.log(`[HITL] [DEBUG] Using interruptData directly (type=${interruptData.type}):`, interruptValue)
                  }
                }
              }

              console.log(`[HITL] [DEBUG] Final interruptValue:`, interruptValue)
              
              if (interruptValue && interruptValue.type === 'plan_approval') {
                // Plan approval interrupt - handle formats:
                // 1. General planner: { type: "plan_approval", plan: { type: "plan_proposal", plan: [...], plan_index: 0, plan_total: X } }
                // 2. Dynamic scouting: { type: "plan_approval", plan: { intent, steps: [...] } } - ExecutionPlan object
                // 3. Dynamic scouting (root): { type: "plan_approval", intent: "...", steps: [{ action, description }] }
                let planData = interruptValue.plan

                // Handle case where plan is an ExecutionPlan object (has steps, not plan array)
                // This happens when backend sends: { plan: { intent, steps: [...] } }
                if (planData && planData.steps && Array.isArray(planData.steps) && !planData.plan) {
                  console.log(`[HITL] [PLAN_APPROVAL] Detected ExecutionPlan format, converting...`)
                  planData = {
                    type: 'plan_proposal',
                    plan: planData.steps.map((step: { action: string; description: string; params?: Record<string, any> }, index: number) => ({
                      action: step.action,
                      tool: step.description,
                      agent: 'scouting',
                      query: step.description,
                      params: step.params || {},
                    })),
                    plan_index: 0,
                    plan_total: planData.steps.length,
                    intent: planData.intent,
                    player_name: planData.player_name,
                    sport_guess: planData.sport_guess,
                    reasoning: planData.reasoning,
                    session_id: interruptValue.session_id
                  }
                  console.log(`[HITL] [PLAN_APPROVAL] Converted ExecutionPlan format:`, planData)
                }
                // Handle NEW dynamic plan format at root level - convert to common format
                else if (!planData && interruptValue.steps && Array.isArray(interruptValue.steps)) {
                  planData = {
                    type: 'plan_proposal',
                    plan: interruptValue.steps.map((step: { action: string; description: string; params?: Record<string, any> }, index: number) => ({
                      action: step.action,
                      tool: step.description,  // Use description as the display text
                      agent: 'scouting',
                      query: step.description,
                      params: step.params || {},
                    })),
                    plan_index: 0,
                    plan_total: interruptValue.steps.length,
                    // Include metadata
                    intent: interruptValue.intent,
                    player_name: interruptValue.player_name,
                    sport_guess: interruptValue.sport_guess,
                    reasoning: interruptValue.reasoning,
                    session_id: interruptValue.session_id
                  }
                  console.log(`[HITL] [PLAN_APPROVAL] Converted NEW dynamic plan format:`, planData)
                }
                console.log(`[HITL] [PLAN_APPROVAL] Received plan approval interrupt:`, planData)

                // Validate plan data structure
                if (!planData || !planData.plan || !Array.isArray(planData.plan)) {
                  console.error(`[HITL] [PLAN_APPROVAL] Invalid plan data structure:`, planData)
                  return
                }

                // Mark message as ready to show plan (even though stream isn't complete)
                setStreamComplete(prev => new Set(prev).add(assistantMessageId))

                // Update/create assistant message with plan data
                set((state: { messages: Message[] }) => {
                  let currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)

                  // Create assistant message if it doesn't exist
                  if (!currentMessage) {
                    console.log(`[HITL] [PLAN_APPROVAL] Creating assistant message for plan: session=${currentSession.id}`)
                    const newMessage: Message = {
                      id: assistantMessageId,
                      role: 'assistant',
                      content: '',
                      tokens_used: 0,
                      created_at: new Date().toISOString(),
                      metadata: {
                        agent_name: 'planner'
                      },
                      response_type: 'plan_proposal',
                      plan: planData
                    }
                    return {
                      messages: [...state.messages, newMessage]
                    }
                  }

                  // Update existing message with plan data
                  console.log(`[HITL] [PLAN_APPROVAL] Updating message ${assistantMessageId} with plan data:`, {
                    response_type: 'plan_proposal',
                    plan: planData,
                    planStepsCount: planData?.plan?.length || 0
                  })

                  return {
                    messages: state.messages.map((msg: Message) =>
                      msg.id === assistantMessageId
                        ? {
                            ...msg,
                            response_type: 'plan_proposal',
                            plan: planData
                          }
                        : msg
                    ),
                  }
                })
                
                // Persist plan proposal to backend (UI-only message)
                // This ensures the plan survives page refresh
                savePlanProposal(assistantMessageId, planData).catch(err => {
                  console.error('[UI_PERSIST] Failed to save plan proposal:', err)
                })

              } else if (interruptValue && interruptValue.type === 'tool_approval') {
                const tools = interruptValue.tools || []

                // Generate unique interrupt ID from tools to prevent duplicate processing
                const interruptId = JSON.stringify(tools.map((t: any) => t.tool_call_id || t.id).sort())

                // Deduplicate - prevent processing same interrupt twice
                if (processedInterruptsRef.current.has(interruptId)) {
                  console.log(`[HITL] [INTERRUPT] Ignoring duplicate interrupt: interruptId=${interruptId} session=${currentSession.id}`)
                  return
                }
                processedInterruptsRef.current.add(interruptId)

                console.log(`[HITL] [INTERRUPT] Received interrupt with ${tools.length} tools requiring approval:`, tools.map((t: any) => ({ tool: t.tool, tool_call_id: t.tool_call_id })))
                
                // Mark message as ready to show tool calls (even though stream isn't complete)
                // This ensures the approval UI is visible immediately
                setStreamComplete(prev => new Set(prev).add(assistantMessageId))
                
                // Ensure assistant message exists - create it if it doesn't
                set((state: { messages: Message[] }) => {
                  let currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)
                  
                  // Create assistant message if it doesn't exist
                  if (!currentMessage) {
                    console.log(`[HITL] [INTERRUPT] Creating assistant message for interrupt: session=${currentSession.id}`)
                    const newMessage: Message = {
                      id: assistantMessageId,
                      role: 'assistant',
                      content: '',
                      tokens_used: 0,
                      created_at: new Date().toISOString(),
                      metadata: {
                        agent_name: 'assistant',
                        tool_calls: []
                      }
                    }
                    return {
                      messages: [...state.messages, newMessage]
                    }
                  }
                  
                  // Update existing message with tool calls requiring approval
                  const existingToolCalls = currentMessage.metadata?.tool_calls || []
                  const updatedToolCalls = [...existingToolCalls]
                  
                  // Add or update tool calls from interrupt
                  for (const toolInfo of tools) {
                    const existingIndex = updatedToolCalls.findIndex((tc: any) => 
                      tc.id === toolInfo.tool_call_id || 
                      (tc.name === toolInfo.tool || tc.tool === toolInfo.tool)
                    )
                    
                    const toolCallData = {
                      id: toolInfo.tool_call_id,
                      name: toolInfo.tool,
                      tool: toolInfo.tool,
                      args: toolInfo.args || {},
                      status: 'pending' as const,
                      requires_approval: true
                    }
                    
                    if (existingIndex >= 0) {
                      updatedToolCalls[existingIndex] = { ...updatedToolCalls[existingIndex], ...toolCallData }
                    } else {
                      updatedToolCalls.push(toolCallData)
                    }
                  }
                  
                  return {
                    messages: state.messages.map((msg: Message) =>
                      msg.id === assistantMessageId
                        ? {
                            ...msg,
                            metadata: {
                              ...msg.metadata,
                              tool_calls: updatedToolCalls
                            }
                          }
                        : msg
                    ),
                  }
                })
              } else if (interruptValue && interruptValue.type === 'player_approval') {
                // Player approval interrupt - HITL Gate B for scouting workflow
                // Backend sends: { type: "player_approval", session_id, player_fields: {...}, report_summary: [...], report_text: "..." }
                
                // Convert backend format to frontend expected format
                const playerPreview = {
                  player: interruptValue.player_fields,
                  report_summary: interruptValue.report_summary,
                  report_text: interruptValue.report_text,
                  session_id: interruptValue.session_id
                }

                console.log(`[PLAYER_HITL] [INTERRUPT] Received player approval interrupt: session=${currentSession?.id} player=${playerPreview?.player?.display_name}`, playerPreview)

                // Mark message as ready to show player preview
                setStreamComplete(prev => new Set(prev).add(assistantMessageId))

                // Update/create assistant message with player preview data
                set((state: { messages: Message[] }) => {
                  let currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)

                  // Create assistant message if it doesn't exist
                  if (!currentMessage) {
                    console.log(`[PLAYER_HITL] [INTERRUPT] Creating assistant message for player preview: session=${currentSession.id}`)
                    const newMessage: Message = {
                      id: assistantMessageId,
                      role: 'assistant',
                      content: '',
                      tokens_used: 0,
                      created_at: new Date().toISOString(),
                      metadata: {
                        agent_name: 'scouting'
                      },
                      response_type: 'player_preview',
                      player_preview: playerPreview
                    }
                    return {
                      messages: [...state.messages, newMessage]
                    }
                  }

                  // Update existing message with player preview data
                  return {
                    messages: state.messages.map((msg: Message) =>
                      msg.id === assistantMessageId
                        ? {
                            ...msg,
                            response_type: 'player_preview',
                            player_preview: playerPreview
                          }
                        : msg
                    )
                  }
                })
                
                // Persist player preview to backend (UI-only message)
                // This ensures the player preview survives page refresh
                savePlayerPreview(assistantMessageId, playerPreview).catch(err => {
                  console.error('[UI_PERSIST] Failed to save player preview:', err)
                })

              // Don't set sending=false here - we're waiting for resume
              // Connection stays open to receive final response after resume
            }
          } else if (eventType === 'heartbeat') {
                // Heartbeat event to keep connection alive (scalability best practice)
                // Prevents idle connection timeouts
                // Log periodically to track connection health
                const elapsed = Date.now() - streamStartTime
                if (elapsed % 60000 < 1000) { // Log roughly every minute
                  console.log(`[FRONTEND] [HEARTBEAT] Connection alive session=${currentSession.id} elapsed=${Math.floor(elapsed / 1000)}s`)
                }
            } else if (eventType === 'final') {
              // Final event contains the complete response after approval
              const finalData = event.data || event.response || {}
              const duration = Date.now() - streamStartTime
              console.log(`[FRONTEND] [STREAM] Final event received session=${currentSession.id} duration=${duration}ms has_response=${!!finalData.reply} response_length=${finalData.reply?.length || 0}`)
              
              // Update message with final response if present
              if (finalData.reply && assistantMessageId) {
                set((state: { messages: Message[] }) => ({
                  messages: state.messages.map((msg: Message) =>
                    msg.id === assistantMessageId
                      ? { ...msg, content: finalData.reply }
                      : msg
                  ),
                }))
              }
            } else if (eventType === 'agent_start') {
              const agentData = event.data || {}
              console.log(`[FRONTEND] [STREAM] Agent started: agent=${agentData.agent_name || 'unknown'} session=${currentSession.id}`)
            } else {
              // Handle unknown event types gracefully
              console.debug(`[FRONTEND] Unknown event type received session=${currentSession.id} type=${eventType}`, event)
            }
          },
          (error: Error) => {
            const duration = Date.now() - streamStartTime
            console.error(`[FRONTEND] [STREAM_ERROR] Stream connection error session=${currentSession.id} duration=${duration}ms error=${error.message} event_counts=${JSON.stringify(eventTypeCounts)}`, error)
            toast.error(error.message || 'Streaming connection error')
            setSending(false)
            setWaitingForResponse(false)
            setWaitingMessageId(null)
          },
          () => {
            // Stream complete
            const duration = Date.now() - streamStartTime
            console.log(`[FRONTEND] [STREAM_COMPLETE] Stream finished session=${currentSession.id} duration=${duration}ms event_counts=${JSON.stringify(eventTypeCounts)}`)

            // If a plan was executing, reload messages to get the execution results
            // Plan execution saves results to DB but doesn't stream them as tokens
            if (executingPlanMessageId) {
              console.log(`[FRONTEND] [PLAN_EXEC_COMPLETE] Plan execution completed, reloading messages session=${currentSession.id}`)
              loadMessages(currentSession.id)
            }

            setSending(false)
            setWaitingForResponse(false)
            setWaitingMessageId(null)
            setExecutingPlanMessageId(null)
          }
        )

        streamRef.current = stream
      }
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to send message'))
      setSending(false)
    }
  }, [currentSession, sending, loadMessages])

  // Handle initial message from navigation state - only once when session is loaded
  useEffect(() => {
    if (
      initialMessageRef.current &&
      currentSession &&
      messages.length === 0 &&
      !initialMessageSentRef.current &&
      !sending
    ) {
      const initialMessage = initialMessageRef.current
      initialMessageSentRef.current = true
      
      // Auto-send the initial message after a short delay to ensure session is ready
      const timeoutId = setTimeout(() => {
        handleSendWithMessage(initialMessage)
        // Clear the ref after sending
        initialMessageRef.current = null
      }, 500)
      
      return () => {
        clearTimeout(timeoutId)
      }
    }
  }, [currentSession?.id, messages.length, sending, handleSendWithMessage])



  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================
  
  // Session Management Handlers
  // Location: These handlers manage session CRUD operations
  // Note: Could be extracted to useSessionManagement hook in the future
  const handleNewChat = async () => {
    const newSession = await createSession()
    if (newSession) {
      navigate(`/chat/${newSession.id}`)
    }
  }

  const handleSelectSession = (id: number) => {
    navigate(`/chat/${id}`)
    // Keep sidebar open - don't auto-close when selecting a chat
  }

  // Message Sending Handler
  // Location: Main message sending logic - calls handleSendWithMessage
  // Note: handleSendWithMessage contains the complex streaming logic (lines ~191-944)
  const handleSend = async () => {
    if (!input.trim() && attachedFiles.length === 0) return
    const content = input.trim()
    setInput('')
    setAttachedFiles([]) // Clear attached files after sending
    if (content) {
      await handleSendWithMessage(content)
    }
  }

  // Cleanup stream on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.close()
      }
      if (resumeStreamRef.current) {
        resumeStreamRef.current.close()
      }
    }
  }, [])

  const handleDeleteSession = async (id: number, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation()
    }
    setSessionToDelete(id)
    setDeleteDialogOpen(true)
    // Note: ChatHeader manages its own menu state, so no need to close it here
    setSessionMenuOpen(null)
  }
  
  const handleDeleteCurrentChat = () => {
    if (currentSession) {
      handleDeleteSession(currentSession.id)
    }
  }

  const handleRenameSession = (sessionId: number, currentTitle: string) => {
    setRenameSessionId(sessionId)
    setRenameSessionTitle(currentTitle || '')
    setSessionMenuOpen(null)
  }

  const handleSaveRename = async () => {
    if (renameSessionId === null) return
    
    try {
      await chatAPI.updateSessionTitle(renameSessionId, renameSessionTitle.trim())
      await loadSessions()
      
      // Update current session if it's the one being renamed
      if (currentSession?.id === renameSessionId) {
        const updatedSession = { ...currentSession, title: renameSessionTitle.trim() }
        set({ currentSession: updatedSession })
      }
      
      setRenameSessionId(null)
      setRenameSessionTitle('')
      toast.success('Chat renamed successfully')
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to rename chat'))
    }
  }

  const handleCancelRename = () => {
    setRenameSessionId(null)
    setRenameSessionTitle('')
  }

  const confirmDeleteSession = async () => {
    if (sessionToDelete === null) return
    
    await deleteSession(sessionToDelete)
    if (currentSession?.id === sessionToDelete) {
      navigate('/chat')
    }
    setDeleteDialogOpen(false)
    setSessionToDelete(null)
  }

  const cancelDeleteSession = () => {
    setDeleteDialogOpen(false)
    setSessionToDelete(null)
  }

  const handleDeleteAllSessions = () => {
    setDeleteAllDialogOpen(true)
  }

  const confirmDeleteAllSessions = async () => {
    try {
      await deleteAllSessions()
      navigate('/chat')
      toast.success('All chat sessions deleted successfully')
      setDeleteAllDialogOpen(false)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to delete all sessions'))
    }
  }

  const cancelDeleteAllSessions = () => {
    setDeleteAllDialogOpen(false)
  }

  // Load chat statistics
  // Location: Statistics loading logic - used by StatsDialog component
  const loadChatStats = useCallback(async (sessionId: number) => {
    setLoadingStats(true)
    try {
      const response = await chatAPI.getStats(sessionId)
      setStats(response.data)
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'response' in error) {
        const apiError = error as { response?: { status?: number } }
        if (apiError.response?.status !== 404 && apiError.response?.status !== 422) {
          toast.error('Failed to load statistics')
        }
      }
      setStats(null)
    } finally {
      setLoadingStats(false)
    }
  }, [])

  const handleOpenStats = () => {
    if (currentSession) {
      setStatsDialogOpen(true)
      loadChatStats(currentSession.id)
    }
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    // Add files to attached files list
    setAttachedFiles((prev) => [...prev, ...files])

    // Add badge for files
    const fileNames = files.map(f => f.name).join(', ')
    const fileLabel = files.length === 1 ? fileNames : `${files.length} files`
    setSelectedOptions((prev) => [...prev, {
      type: 'files',
      label: fileLabel,
      icon: (
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
        </svg>
      ),
      data: files
    }])

    // Upload files
    for (const file of files) {
      try {
        await documentAPI.uploadDocument(file)
        toast.success(`File "${file.name}" uploaded successfully`)
      } catch (error: unknown) {
        toast.error(getErrorMessage(error, `Failed to upload ${file.name}`))
      }
    }

  }

  const handleRemoveFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index))
  }

  // Remove selected option badge
  // Location: Removes badges from selected options (used by ChatInput component)
  const removeSelectedOption = (index: number) => {
    const option = selectedOptions[index]
    setSelectedOptions((prev) => prev.filter((_, i) => i !== index))
    
    // If it was a file option, also remove from attachedFiles
    if (option.type === 'files' && option.data) {
      setAttachedFiles((prev) => prev.filter((_, i) => !option.data.includes(i)))
    }
  }

  // ============================================================================
  // CUSTOM HOOKS
  // ============================================================================
  
  // UI Message Persistence Hook - MUST be defined before handleResumeStream
  // Location: frontend/src/hooks/useUiMessagePersistence.ts
  // Persists plan proposals and player previews to the database (UI-only messages)
  const {
    savePlanProposal,
    updatePlanProgress,
    savePlayerPreview,
    clearSavedMessages,
  } = useUiMessagePersistence({
    sessionId: currentSession?.id ?? null,
  })
  
  // Clear saved messages when session changes
  useEffect(() => {
    clearSavedMessages()
  }, [currentSession?.id, clearSavedMessages])

  /**
   * Handle resume stream after HITL approval (plan or player).
   * 
   * This function opens a new SSE connection to receive events from the resumed workflow.
   * The original stream closes on interrupt, so we need a new stream for execution events.
   * 
   * @param planMessageId - Optional message ID to use for plan progress updates.
   *                        Pass this directly to avoid race conditions with state updates.
   */
  const handleResumeStream = useCallback((planMessageId?: number) => {
    if (!currentSession) {
      console.error('[RESUME_STREAM] No current session')
      return
    }

    // Close any existing resume stream
    if (resumeStreamRef.current) {
      resumeStreamRef.current.close()
    }

    // Use passed planMessageId first (avoids race condition), then fall back to state, then generate temp ID
    const assistantMessageId = planMessageId || executingPlanMessageId || generateTempMessageId()
    
    console.log(`[RESUME_STREAM] Opening resume stream for session=${currentSession.id}, planMessageId=${planMessageId}, executingPlanMessageId=${executingPlanMessageId}, using assistantMessageId=${assistantMessageId}`)
    
    // Track if we received a player_approval interrupt - if so, don't reload messages on complete
    // This prevents loadMessages() from clearing the player preview we just set
    let receivedPlayerApproval = false

    const resumeStream = createResumeStream(
      currentSession.id,
      (event: StreamEvent) => {
        const eventType = event.type
        console.log(`[RESUME_STREAM] Received event: ${eventType}`)

        if (eventType === 'plan_step_progress') {
          // Handle plan step progress events
          const progressData = event.data || {}
          console.log(`[RESUME_STREAM] [PLAN_PROGRESS] Step ${progressData.step_index + 1}/${progressData.total_steps}: ${progressData.status} - ${progressData.step_name}`)
          
          set((state: { messages: Message[] }) => {
            const currentMessage = state.messages.find((msg: Message) => msg.id === assistantMessageId)
            if (!currentMessage) {
              console.warn(`[RESUME_STREAM] [PLAN_PROGRESS] Message not found! assistantMessageId=${assistantMessageId}, available message IDs:`, state.messages.map(m => m.id))
              return state
            }
            
            console.log(`[RESUME_STREAM] [PLAN_PROGRESS] Updating message ${currentMessage.id} with step progress`)
            
            const currentProgress = currentMessage.plan_progress || {
              current_step_index: -1,
              total_steps: progressData.total_steps || 0,
              steps_status: {}
            }
            
            const updatedProgress = {
              ...currentProgress,
              current_step_index: progressData.status === 'in_progress' ? progressData.step_index : currentProgress.current_step_index,
              total_steps: progressData.total_steps || currentProgress.total_steps,
              steps_status: {
                ...currentProgress.steps_status,
                [progressData.step_index]: {
                  status: progressData.status,
                  step_name: progressData.step_name,
                  result: progressData.result,
                }
              }
            }
            
            return {
              messages: state.messages.map((msg: Message) =>
                msg.id === assistantMessageId
                  ? { ...msg, plan_progress: updatedProgress }
                  : msg
              ),
            }
          })

          // Persist plan progress to backend
          if (progressData.status === 'completed' || progressData.status === 'error') {
            const updatedProgress = {
              current_step_index: progressData.step_index,
              total_steps: progressData.total_steps,
              steps_status: {
                [progressData.step_index]: {
                  status: progressData.status,
                  step_name: progressData.step_name,
                  result: progressData.result,
                }
              }
            }
            updatePlanProgress(assistantMessageId, updatedProgress).catch(err => {
              console.error('[RESUME_STREAM] Failed to update plan progress:', err)
            })
          }
        } else if (eventType === 'token') {
          // Handle streaming tokens (for final answer)
          const token = event.data?.token || event.data?.content || ''
          if (token) {
            set((state: { messages: Message[] }) => ({
              messages: state.messages.map((msg: Message) =>
                msg.id === assistantMessageId
                  ? { ...msg, content: (msg.content || '') + token }
                  : msg
              ),
            }))
          }
        } else if (eventType === 'message_saved') {
          // Update message with real DB id
          const savedData = event.data || {}
          if (savedData.db_id && savedData.role === 'assistant') {
            console.log(`[RESUME_STREAM] Message saved with db_id=${savedData.db_id}`)
            set((state: { messages: Message[] }) => ({
              messages: state.messages.map((msg: Message) =>
                msg.id === assistantMessageId
                  ? { ...msg, id: savedData.db_id }
                  : msg
              ),
            }))
          }
        } else if (eventType === 'interrupt') {
          // Another HITL gate (e.g., player approval after plan execution)
          const interruptData = event.data || {}
          const interruptValue = interruptData.value || interruptData
          console.log(`[RESUME_STREAM] [INTERRUPT] Another interrupt received: type=${interruptValue?.type}`, interruptValue)
          
          if (interruptValue && interruptValue.type === 'player_approval') {
            // Player approval interrupt - HITL Gate B for scouting workflow
            // Backend sends: { type: "player_approval", session_id, player_fields: {...}, report_summary: [...], report_text: "..." }
            
            // Mark that we received player approval - this prevents loadMessages() from clearing the preview
            receivedPlayerApproval = true
            
            // Convert backend format to frontend expected format
            const playerPreview = {
              player: interruptValue.player_fields,
              report_summary: interruptValue.report_summary,
              report_text: interruptValue.report_text,
              session_id: interruptValue.session_id
            }

            console.log(`[RESUME_STREAM] [PLAYER_HITL] Received player approval interrupt: session=${currentSession?.id} player=${playerPreview?.player?.display_name}`, playerPreview)

            // Update the SAME message that has the plan (identified by executingPlanMessageId)
            // Don't create a new message - update the existing plan message with player preview
            set((state: { messages: Message[] }) => {
              // Try to find message by executingPlanMessageId first, then by assistantMessageId
              const messageIdToUpdate = executingPlanMessageId || assistantMessageId
              let currentMessage = state.messages.find((msg: Message) => msg.id === messageIdToUpdate)

              // If not found by temp ID, try to find by checking if it's a plan proposal message
              if (!currentMessage) {
                currentMessage = state.messages.find((msg: Message) => 
                  msg.response_type === 'plan_proposal' && msg.role === 'assistant'
                )
              }

              // If still not found, create new message
              if (!currentMessage) {
                console.log(`[RESUME_STREAM] [PLAYER_HITL] Creating assistant message for player preview: session=${currentSession?.id}`)
                const newMessage: Message = {
                  id: assistantMessageId,
                  role: 'assistant',
                  content: '',
                  tokens_used: 0,
                  created_at: new Date().toISOString(),
                  metadata: {
                    agent_name: 'scouting'
                  },
                  response_type: 'player_preview',
                  player_preview: playerPreview
                }
                return {
                  messages: [...state.messages, newMessage]
                }
              }

              console.log(`[RESUME_STREAM] [PLAYER_HITL] Updating existing message ${currentMessage.id} with player preview`)
              // Update existing message with player preview data
              return {
                messages: state.messages.map((msg: Message) =>
                  msg.id === currentMessage!.id
                    ? {
                        ...msg,
                        response_type: 'player_preview',
                        player_preview: playerPreview
                      }
                    : msg
                )
              }
            })
            
            // Persist player preview to backend (UI-only message)
            // This ensures the player preview survives page refresh
            // Use a new temp ID for the player preview since it's a separate UI message
            const playerPreviewMessageId = Date.now()
            savePlayerPreview(playerPreviewMessageId, playerPreview).catch(err => {
              console.error('[RESUME_STREAM] Failed to save player preview:', err)
            })
            
            // DON'T clear executingPlanMessageId yet - we're in player approval stage
            // The user needs to approve/reject the player before we're done
            // setExecutingPlanMessageId(null) -- REMOVED to prevent loadMessages from clearing data
            
            // Mark the plan as completed (all steps finished, now waiting for player approval)
            // This ensures buttons don't reappear after loadMessages
            setCompletedPlanMessageIds(prev => new Set(prev).add(assistantMessageId))
            setApprovedPlanMessageIds(prev => new Set(prev).add(assistantMessageId))
            // Auto-collapse plan panel when execution reaches player approval
            setPlanPanelCollapsed(true)
          }
          // Stream will close on interrupt, which is expected behavior
          // DON'T reload messages here - we have the data we need and loadMessages would clear temp messages
        } else if (eventType === 'final' || eventType === 'done') {
          console.log(`[RESUME_STREAM] Stream finished with ${eventType}`)
          // Mark plan as completed
          setCompletedPlanMessageIds(prev => new Set(prev).add(assistantMessageId))
          setApprovedPlanMessageIds(prev => new Set(prev).add(assistantMessageId))
          setPlanPanelCollapsed(true)
          setExecutingPlanMessageId(null)
          // Reload messages to get final state from DB
          loadMessages(currentSession.id)
        } else if (eventType === 'error') {
          console.error(`[RESUME_STREAM] Error event:`, event.data)
          toast.error(event.data?.error || 'Error during plan execution')
          setExecutingPlanMessageId(null)
        }
      },
      (error: Error) => {
        console.error(`[RESUME_STREAM] Stream error:`, error)
        toast.error('Lost connection to server')
        setExecutingPlanMessageId(null)
      },
      () => {
        console.log(`[RESUME_STREAM] Stream complete, receivedPlayerApproval=${receivedPlayerApproval}`)
        // Only reload messages if we didn't receive a player approval interrupt
        // If we received player approval, loading messages would clear the temp player preview message
        // The player preview is already saved to the backend via savePlayerPreview()
        if (currentSession && !receivedPlayerApproval) {
          loadMessages(currentSession.id)
          setExecutingPlanMessageId(null)
        }
        // If we received player approval, DON'T clear executingPlanMessageId
        // The player card needs this to show in the UI, and we're waiting for user approval/rejection
      }
    )

    resumeStreamRef.current = resumeStream
  }, [currentSession, executingPlanMessageId, set, loadMessages, updatePlanProgress, savePlayerPreview, setCompletedPlanMessageIds, setApprovedPlanMessageIds])

  // Tool Approval Hook
  // Location: frontend/src/hooks/useToolApproval.ts
  // Handles tool approval logic for human-in-the-loop workflows
  const { handleApproveTool, handleRejectTool, approvingToolCalls, setApprovingToolCalls } = useToolApproval({
    currentSession,
    updateMessages: (updater) => {
      set((state: { messages: Message[] }) => ({ messages: updater(state.messages) }))
    },
    loadMessages,
  })
  
  // Callback to mark a plan as approved (persists across loadMessages)
  const markPlanApproved = useCallback((messageId: number) => {
    setApprovedPlanMessageIds(prev => new Set(prev).add(messageId))
  }, [])
  
  // Callback to mark a plan as completed
  const markPlanCompleted = useCallback((messageId: number) => {
    setCompletedPlanMessageIds(prev => new Set(prev).add(messageId))
    // Auto-collapse the plan panel when completed
    setPlanPanelCollapsed(true)
  }, [])
  
  const { handleApprovePlan, handleRejectPlan, approvingPlans } = usePlanApproval({
    currentSession,
    updateMessages: (updater) => {
      set((state: { messages: Message[] }) => ({ messages: updater(state.messages) }))
    },
    setExecutingPlanMessageId,
    markPlanApproved,
    onResumeStream: handleResumeStream,
  })
  
  const {
    handleApprovePlayer,
    handleRejectPlayer,
    handleEditWording,
    handleEditContent,
    approvingPlayers,
  } = usePlayerApproval({
    currentSession,
    updateMessages: (updater) => {
      set((state: { messages: Message[] }) => ({ messages: updater(state.messages) }))
    },
    loadMessages,
    onResumeStream: handleResumeStream,
  })
  
  // Compute the active plan for the plan panel
  // Find the most recent message with a plan (either awaiting approval or executing)
  const activePlanData = useMemo(() => {
    // Find messages with plans, prioritizing the one being executed
    let planMessage: Message | undefined
    
    if (executingPlanMessageId) {
      // If we're executing a plan, show that one
      planMessage = messages.find(m => m.id === executingPlanMessageId)
    }
    
    if (!planMessage) {
      // Find the most recent message with a plan proposal
      const messagesWithPlans = messages.filter(m => 
        m.response_type === 'plan_proposal' && m.plan
      )
      planMessage = messagesWithPlans[messagesWithPlans.length - 1]
    }
    
    if (!planMessage?.plan) return null
    
    // Check if this plan has been approved or completed
    const isApproved = approvedPlanMessageIds.has(planMessage.id)
    const isCompleted = completedPlanMessageIds.has(planMessage.id)
    const isExecuting = !!executingPlanMessageId && planMessage.id === executingPlanMessageId
    
    return {
      plan: planMessage.plan,
      progress: planMessage.plan_progress,
      isExecuting,
      isApproved: isApproved || isExecuting, // Show as approved if executing or explicitly approved
      isCompleted,
      messageId: planMessage.id,
    }
  }, [messages, executingPlanMessageId, approvedPlanMessageIds, completedPlanMessageIds])

  // Auto-show plan panel when a new plan arrives (even if user previously closed it)
  // Track the last seen plan message ID to detect new plans
  const lastSeenPlanIdRef = useRef<number | null>(null)
  useEffect(() => {
    if (activePlanData && activePlanData.messageId !== lastSeenPlanIdRef.current) {
      // New plan detected - show the panel
      setShowPlanPanel(true)
      lastSeenPlanIdRef.current = activePlanData.messageId
    }
  }, [activePlanData])

  // Handle plan rejection (legacy - kept for backward compatibility)
  const handlePlanRejection = useCallback((messageId: number) => {
    // Update message to show rejection
    set((state: { messages: Message[] }) => ({
      messages: state.messages.map((msg: Message) =>
        msg.id === messageId
          ? {
              ...msg,
              content: msg.content || 'Plan rejected. You can modify your query or continue the conversation.',
              response_type: 'answer',
            }
          : msg
      ),
    }))
    toast.info('Plan rejected')
  }, [])

  // ============================================================================
  // RENDER
  // ============================================================================
  // Component Structure:
  // 1. ChatSidebar - Left sidebar with session list (collapsible)
  // 2. Main Chat Area:
  //    a. ChatHeader - Top bar with model selection and menu
  //    b. MessageList - Scrollable messages area (or empty state with ChatInput)
  //    c. ChatInput - Bottom input area (only when messages exist)
  // 3. DeleteDialogs - Delete confirmation modals
  // 4. StatsDialog - Statistics modal with activity timeline
  return (
    <>
    <div className="flex h-[calc(100vh-120px)] sm:h-[calc(100vh-145px)] bg-background">
      {/* Sidebar Component - Handles session list, new chat, rename, delete */}
      {/* Location: frontend/src/components/chat/ChatSidebar.tsx */}
      <ChatSidebar
        sidebarOpen={sidebarOpen}
        sessions={sessions}
        currentSession={currentSession}
        loading={loading}
        chatsSectionOpen={chatsSectionOpen}
        onToggleChatsSection={() => setChatsSectionOpen(!chatsSectionOpen)}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onDeleteAllChats={handleDeleteAllSessions}
        renameSessionId={renameSessionId}
        renameSessionTitle={renameSessionTitle}
        setRenameSessionTitle={setRenameSessionTitle}
        onSaveRename={handleSaveRename}
        onCancelRename={handleCancelRename}
        sessionMenuOpen={sessionMenuOpen}
        setSessionMenuOpen={setSessionMenuOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {!currentSession ? (
          // No session selected - show welcome screen
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-md">
              <h2 className="text-2xl font-semibold mb-2">Start a new conversation</h2>
              <p className="text-muted-foreground mb-6">
                Create a new chat to begin talking with AI agents
              </p>
              <Button onClick={handleNewChat} size="lg">New Chat</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Header Component - Model selection and menu */}
            {/* Location: frontend/src/components/chat/ChatHeader.tsx */}
            <ChatHeader
              sidebarOpen={sidebarOpen}
              onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
              selectedModel={selectedModel}
              availableModels={availableModels}
              onModelChange={handleModelChange}
              onOpenStats={handleOpenStats}
              onDeleteChat={handleDeleteCurrentChat}
              onDeleteAllChats={handleDeleteAllSessions}
              hasCurrentSession={!!currentSession}
              sessionCount={sessions.length}
              messages={messages}
            />

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto">
              {messages.length === 0 ? (
                // Empty state - show centered input with welcome message
                <ChatInput
                  input={input}
                  setInput={setInput}
                  attachedFiles={attachedFiles}
                  onFileSelect={handleFileSelect}
                  selectedOptions={selectedOptions}
                  onRemoveOption={removeSelectedOption}
                  onSend={handleSend}
                  sending={sending}
                  inputFocused={inputFocused}
                  setInputFocused={setInputFocused}
                  error={error}
                  isEmptyState={true}
                />
              ) : (
                // Messages List Component - Renders all messages
                // Location: frontend/src/components/chat/MessageList.tsx
                <MessageList
                  messages={messages}
                  streamComplete={streamComplete}
                  expandedToolCalls={expandedToolCalls}
                  onToggleToolCall={(toolCallId) => {
                    setExpandedToolCalls((prev) => {
                      const next = new Set(prev)
                      if (next.has(toolCallId)) {
                        next.delete(toolCallId)
                      } else {
                        next.add(toolCallId)
                      }
                      return next
                    })
                  }}
                  onApproveTool={async (messageId, toolCall, toolCallId, toolName) => {
                    await handleApproveTool(messageId, toolCall, toolCallId, toolName)
                  }}
                  onRejectTool={async (messageId, toolCall, toolCallId, toolName) => {
                    await handleRejectTool(messageId, toolCall, toolCallId, toolName)
                  }}
                  approvingToolCalls={approvingToolCalls}
                  currentSession={currentSession}
                  onPlanApproval={handleApprovePlan}
                  onPlanRejection={handleRejectPlan}
                  executingPlanMessageId={executingPlanMessageId}
                  onApprovePlayer={handleApprovePlayer}
                  onRejectPlayer={handleRejectPlayer}
                  onEditPlayerWording={handleEditWording}
                  onEditPlayerContent={handleEditContent}
                  approvingPlayers={approvingPlayers}
                  userEmail={user?.email}
                />
              )}
            </div>

            {/* Input Area - Only show when messages exist */}
            {/* Location: frontend/src/components/chat/ChatInput.tsx */}
            {messages.length > 0 && (
              <ChatInput
                input={input}
                setInput={setInput}
                attachedFiles={attachedFiles}
                onFileSelect={handleFileSelect}
                selectedOptions={selectedOptions}
                onRemoveOption={removeSelectedOption}
                onSend={handleSend}
                sending={sending}
                inputFocused={inputFocused}
                setInputFocused={setInputFocused}
                error={error}
                isEmptyState={false}
              />
            )}
          </>
        )}
      </div>
      
      {/* Plan Panel - Right Side */}
      {/* Shows active plan with real-time progress during execution */}
      {currentSession && activePlanData && showPlanPanel && (
        <PlanPanel
          plan={activePlanData.plan}
          progress={activePlanData.progress}
          isExecuting={activePlanData.isExecuting}
          isCollapsed={planPanelCollapsed}
          onToggleCollapse={() => setPlanPanelCollapsed(!planPanelCollapsed)}
          onClose={() => setShowPlanPanel(false)}
          onApprove={() => {
            // handleApprovePlan expects (messageId, planData)
            handleApprovePlan(activePlanData.messageId, activePlanData.plan)
          }}
          onReject={() => {
            // handleRejectPlan expects (messageId)
            handleRejectPlan(activePlanData.messageId)
          }}
          isApproved={activePlanData.isApproved}
          isCompleted={activePlanData.isCompleted}
        />
      )}
    </div>

    {/* Delete Confirmation Dialogs */}
    {/* Location: frontend/src/components/chat/DeleteDialogs.tsx */}
    <DeleteDialogs
      deleteDialogOpen={deleteDialogOpen}
      deleteAllDialogOpen={deleteAllDialogOpen}
      sessionToDelete={sessionToDelete}
      sessionCount={sessions.length}
      onConfirmDelete={confirmDeleteSession}
      onCancelDelete={cancelDeleteSession}
      onConfirmDeleteAll={confirmDeleteAllSessions}
      onCancelDeleteAll={cancelDeleteAllSessions}
    />

    {/* Stats Dialog */}
    {/* Location: frontend/src/components/chat/StatsDialog.tsx */}
    <StatsDialog
      open={statsDialogOpen}
      onClose={() => setStatsDialogOpen(false)}
      stats={stats}
      loading={loadingStats}
      messages={messages}
      expandedChains={expandedChains}
      expandedActivities={expandedActivities}
      onToggleChain={(traceId) => {
        setExpandedChains((prev) => 
          prev.includes(traceId) 
            ? prev.filter(id => id !== traceId)
            : [...prev, traceId]
        )
      }}
      onToggleActivity={(activityKey) => {
        setExpandedActivities((prev) => 
          prev.includes(activityKey) 
            ? prev.filter(key => key !== activityKey)
            : [...prev, activityKey]
        )
      }}
    />
    </>
  )
}
