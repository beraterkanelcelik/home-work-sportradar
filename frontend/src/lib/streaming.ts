/**
 * SSE (Server-Sent Events) streaming utilities for agent responses.
 */

export interface StreamEvent {
  type: 'token' | 'update' | 'agent_start' | 'tool_call' | 'error' | 'done' | 'interrupt' | 'message_saved' | 'heartbeat' | 'final' | 'plan_step_progress' | 'context_usage' | 'plan_proposal' | 'player_preview' | 'workflow_status' | 'tasks_updated' | 'tool_start' | 'tool_complete'
  data?: any
  response?: any  // For final events
  interrupt?: any  // For interrupt events (contains interrupt payload)
}

/**
 * Agent task from StateGraph workflow.
 */
export interface AgentTask {
  id: string
  description: string
  status: 'pending' | 'in_progress' | 'completed'
}

export class SSEStream {
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null
  private controller: AbortController | null = null
  private onMessage: (event: StreamEvent) => void
  private onError: (error: Error) => void
  private onComplete: () => void
  private eventCounts: Map<string, number> = new Map()
  private tokenCount: number = 0
  private startTime: number = Date.now()

  constructor(
    url: string,
    body: any,
    headers: Record<string, string>,
    onMessage: (event: StreamEvent) => void,
    onError: (error: Error) => void,
    onComplete: () => void
  ) {
    this.onMessage = onMessage
    this.onError = onError
    this.onComplete = onComplete
    this.controller = new AbortController()

    const sessionId = body.chat_session_id || 'unknown'

    // Use fetch for POST requests with SSE
    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify(body),
      signal: this.controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        return response.body
      })
      .then((body) => {
        if (!body) {
          throw new Error('Response body is null')
        }
        this.reader = body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        const processStream = () => {
          if (!this.reader) return

          this.reader
            .read()
            .then(({ done, value }) => {
              if (done) {
                this.onComplete()
                return
              }

              buffer += decoder.decode(value, { stream: true })
              const lines = buffer.split('\n\n')
              buffer = lines.pop() || ''

              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  try {
                    const data = JSON.parse(line.slice(6))
                    // Validate event structure
                    if (data && typeof data === 'object' && 'type' in data) {
                      const eventType = data.type
                      // Track event counts
                      this.eventCounts.set(eventType, (this.eventCounts.get(eventType) || 0) + 1)
                      
                      // Track token count
                      if (eventType === 'token') {
                        this.tokenCount++
                      }
                      
                      // Log critical human-in-the-loop events (aligned with LangGraph interrupt pattern)
                      // Reference: https://docs.langchain.com/oss/python/langgraph/use-functional-api#review-tool-calls
                      // This is the equivalent of LangGraph's interrupt() in our Temporal + Redis architecture
                      if (eventType === 'update' && data.data?.type === 'tool_approval_required') {
                        console.log(`[HITL] [REVIEW] [SSE_STREAM] Received tool_approval_required (interrupt equivalent): tool=${data.data.tool_info?.tool} tool_call_id=${data.data.tool_info?.tool_call_id} session=${sessionId}`)
                      }
                      
                      this.onMessage(data)
                    } else {
                      console.warn(`[SSE_STREAM] Received invalid event structure for session=${sessionId}:`, data)
                    }
                  } catch (error) {
                    // Log parsing errors in development
                    if (import.meta.env.MODE === 'development') {
                      console.warn(`[SSE_STREAM] Failed to parse event for session=${sessionId}:`, error, 'Line:', line.substring(0, 100))
                    }
                  }
                }
              }

              processStream()
            })
            .catch((error) => {
              if (error.name !== 'AbortError') {
                console.error(`[SSE_STREAM] Error reading stream for session=${sessionId}:`, error.message)
                this.onError(error)
              }
            })
        }

        processStream()
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error(`[SSE_STREAM] Failed to start stream for session=${sessionId}:`, error.message)
          this.onError(error)
        }
      })
  }

  close() {
    if (this.controller) {
      this.controller.abort()
      this.controller = null
    }
    if (this.reader) {
      this.reader.cancel()
      this.reader = null
    }
  }
}

/**
 * Create SSE stream for agent response.
 */
export function createAgentStream(
  chatSessionId: number,
  message: string,
  token: string,
  onMessage: (event: StreamEvent) => void,
  onError: (error: Error) => void,
  onComplete: () => void,
  model?: string
): SSEStream {
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  const url = `${API_URL}/api/agent/stream/`

  const body: Record<string, any> = {
    chat_session_id: chatSessionId,
    message,
    model: model || undefined,  // Pass selected model to backend
  }

  return new SSEStream(
    url,
    body,
    { Authorization: `Bearer ${token}` },
    onMessage,
    onError,
    onComplete
  )
}

/**
 * SSE Stream for GET requests (used for resume streams after HITL approval).
 * 
 * Unlike SSEStream which uses POST, this uses GET with query parameters
 * and native EventSource for cleaner SSE handling.
 */
export class SSEResumeStream {
  private eventSource: EventSource | null = null
  private controller: AbortController | null = null
  private onMessage: (event: StreamEvent) => void
  private onError: (error: Error) => void
  private onComplete: () => void

  constructor(
    url: string,
    onMessage: (event: StreamEvent) => void,
    onError: (error: Error) => void,
    onComplete: () => void
  ) {
    this.onMessage = onMessage
    this.onError = onError
    this.onComplete = onComplete
    this.controller = new AbortController()

    console.log(`[SSE_RESUME] Opening resume stream: ${url}`)

    // Use fetch for GET SSE (EventSource doesn't support custom headers for auth)
    fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      },
      signal: this.controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        return response.body
      })
      .then((body) => {
        if (!body) {
          throw new Error('Response body is null')
        }
        const reader = body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        const processStream = () => {
          reader
            .read()
            .then(({ done, value }) => {
              if (done) {
                console.log(`[SSE_RESUME] Stream completed`)
                this.onComplete()
                return
              }

              buffer += decoder.decode(value, { stream: true })
              const lines = buffer.split('\n\n')
              buffer = lines.pop() || ''

              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  try {
                    const data = JSON.parse(line.slice(6))
                    if (data && typeof data === 'object' && 'type' in data) {
                      console.log(`[SSE_RESUME] Received event: ${data.type}`)
                      this.onMessage(data)
                    }
                  } catch (error) {
                    console.warn(`[SSE_RESUME] Failed to parse event:`, error)
                  }
                }
              }

              processStream()
            })
            .catch((error) => {
              if (error.name !== 'AbortError') {
                console.error(`[SSE_RESUME] Error reading stream:`, error.message)
                this.onError(error)
              }
            })
        }

        processStream()
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error(`[SSE_RESUME] Failed to start stream:`, error.message)
          this.onError(error)
        }
      })
  }

  close() {
    console.log(`[SSE_RESUME] Closing stream`)
    if (this.controller) {
      this.controller.abort()
      this.controller = null
    }
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
  }
}

/**
 * Create SSE stream for resuming after HITL approval (plan or player approval).
 * 
 * This is called after the user approves a plan/player to receive the execution events.
 * The original stream closes on interrupt, so we need a new stream for the resumed workflow.
 */
export function createResumeStream(
  chatSessionId: number,
  onMessage: (event: StreamEvent) => void,
  onError: (error: Error) => void,
  onComplete: () => void
): SSEResumeStream {
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  const url = `${API_URL}/api/agent/stream-resume/?chat_session_id=${chatSessionId}`

  return new SSEResumeStream(
    url,
    onMessage,
    onError,
    onComplete
  )
}
