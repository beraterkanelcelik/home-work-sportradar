/**
 * useUiMessagePersistence Hook
 *
 * Persists UI-only messages (plans, status updates, progress) to the backend.
 * These messages are saved with sender_type='ui' so they are:
 * - Displayed in the UI (survive page refresh)
 * - Excluded from LLM context (won't confuse the AI)
 */

import { useCallback, useRef } from 'react'
import { chatAPI } from '@/lib/api'

interface SavedMessage {
  id: number
  tempId?: number
}

interface PlanData {
  type: string
  plan: Array<{
    action: string
    tool?: string
    answer?: string
    props?: Record<string, any>
    agent: string
    query: string
    status?: 'pending' | 'in_progress' | 'completed' | 'error'
  }>
  plan_index: number
  plan_total: number
  player_name?: string
  sport_guess?: string
}

interface PlanProgress {
  current_step_index: number
  total_steps: number
  steps_status: Record<number, {
    status: 'pending' | 'in_progress' | 'completed' | 'error'
    step_name: string
    result?: string
  }>
}

interface UseUiMessagePersistenceProps {
  sessionId: number | null
}

export function useUiMessagePersistence({ sessionId }: UseUiMessagePersistenceProps) {
  // Track saved message IDs to enable updates
  const savedMessagesRef = useRef<Map<string, SavedMessage>>(new Map())

  /**
   * Save a plan proposal message to the backend.
   * Returns the saved message ID for future updates.
   */
  const savePlanProposal = useCallback(async (
    tempMessageId: number,
    plan: PlanData
  ): Promise<number | null> => {
    if (!sessionId) {
      console.warn('[UI_PERSIST] No session ID, cannot save plan proposal')
      return null
    }

    try {
      const response = await chatAPI.saveUiMessage(sessionId, {
        role: 'assistant',
        content: `Plan proposal with ${plan.plan?.length || 0} step(s) to execute.`,
        metadata: {
          type: 'plan_proposal',
          response_type: 'plan_proposal',
          plan: plan,
          agent_name: 'planner',
        }
      })

      const savedId = response.data.id
      // Store mapping with BOTH temp ID and DB ID as keys
      // This ensures updatePlanProgress works whether called with temp ID or DB ID
      savedMessagesRef.current.set(`plan_${tempMessageId}`, { id: savedId, tempId: tempMessageId })
      savedMessagesRef.current.set(`plan_${savedId}`, { id: savedId, tempId: tempMessageId })

      console.log(`[UI_PERSIST] Saved plan proposal: tempId=${tempMessageId} dbId=${savedId}`)
      return savedId
    } catch (error) {
      console.error('[UI_PERSIST] Failed to save plan proposal:', error)
      return null
    }
  }, [sessionId])

  /**
   * Update a saved plan message with progress information.
   * Handles both temp IDs (from streaming) and DB IDs (after message_saved event).
   */
  const updatePlanProgress = useCallback(async (
    messageId: number,
    progress: PlanProgress
  ): Promise<boolean> => {
    if (!sessionId) {
      console.warn('[UI_PERSIST] No session ID, cannot update plan progress')
      return false
    }

    // Try to find mapping in ref (works for both temp ID and DB ID keys)
    const savedMessage = savedMessagesRef.current.get(`plan_${messageId}`)

    // Determine the DB ID to use for the API call
    let dbIdToUpdate: number
    if (savedMessage) {
      dbIdToUpdate = savedMessage.id
    } else if (messageId > 0 && messageId < 1000000) {
      // If messageId looks like a real DB ID (positive, reasonable size),
      // try to update it directly. This handles cases after page refresh
      // where savedMessagesRef is empty but we have the real DB ID.
      dbIdToUpdate = messageId
      console.log(`[UI_PERSIST] No mapping found for messageId=${messageId}, using it directly as DB ID`)
    } else {
      console.warn(`[UI_PERSIST] No saved message found for messageId=${messageId} and it doesn't look like a DB ID`)
      return false
    }

    try {
      await chatAPI.updateUiMessage(sessionId, dbIdToUpdate, {
        metadata: {
          plan_progress: progress
        }
      })

      console.log(`[UI_PERSIST] Updated plan progress: messageId=${messageId} dbId=${dbIdToUpdate} step=${progress.current_step_index + 1}/${progress.total_steps}`)
      return true
    } catch (error) {
      console.error('[UI_PERSIST] Failed to update plan progress:', error)
      return false
    }
  }, [sessionId])

  /**
   * Update an existing message with player preview data.
   * This updates the plan message to include player_preview instead of creating a separate message.
   */
  const updateMessageWithPlayerPreview = useCallback(async (
    messageId: number,
    playerPreview: {
      player: Record<string, any>
      report_summary: string[]
      report_text: string
      session_id?: number
    }
  ): Promise<boolean> => {
    if (!sessionId) {
      console.warn('[UI_PERSIST] No session ID, cannot update with player preview')
      return false
    }

    // Try to find mapping in ref (works for both temp ID and DB ID keys)
    const savedMessage = savedMessagesRef.current.get(`plan_${messageId}`)

    // Determine the DB ID to use for the API call
    let dbIdToUpdate: number
    if (savedMessage) {
      dbIdToUpdate = savedMessage.id
    } else if (messageId > 0 && messageId < 1000000) {
      // If messageId looks like a real DB ID, use it directly
      dbIdToUpdate = messageId
      console.log(`[UI_PERSIST] No mapping found for messageId=${messageId}, using it directly as DB ID`)
    } else {
      console.warn(`[UI_PERSIST] No saved message found for messageId=${messageId} and it doesn't look like a DB ID`)
      return false
    }

    try {
      await chatAPI.updateUiMessage(sessionId, dbIdToUpdate, {
        metadata: {
          response_type: 'player_preview',
          player_preview: playerPreview,
        }
      })

      console.log(`[UI_PERSIST] Updated message with player preview: messageId=${messageId} dbId=${dbIdToUpdate}`)
      return true
    } catch (error) {
      console.error('[UI_PERSIST] Failed to update with player preview:', error)
      return false
    }
  }, [sessionId])

  /**
   * Save a player preview message to the backend (creates new message - DEPRECATED).
   * Use updateMessageWithPlayerPreview instead to update existing plan message.
   */
  const savePlayerPreview = useCallback(async (
    tempMessageId: number,
    playerPreview: {
      player: Record<string, any>
      report_summary: string[]
      report_text: string
      session_id?: number
    }
  ): Promise<number | null> => {
    if (!sessionId) {
      console.warn('[UI_PERSIST] No session ID, cannot save player preview')
      return null
    }

    try {
      const response = await chatAPI.saveUiMessage(sessionId, {
        role: 'assistant',
        content: `Player preview: ${playerPreview.player?.display_name || 'Unknown player'}`,
        metadata: {
          type: 'player_preview',
          response_type: 'player_preview',
          player_preview: playerPreview,
          agent_name: 'scouting',
        }
      })

      const savedId = response.data.id
      savedMessagesRef.current.set(`player_${tempMessageId}`, { id: savedId, tempId: tempMessageId })

      console.log(`[UI_PERSIST] Saved player preview: tempId=${tempMessageId} dbId=${savedId}`)
      return savedId
    } catch (error) {
      console.error('[UI_PERSIST] Failed to save player preview:', error)
      return null
    }
  }, [sessionId])

  /**
   * Clear saved message references (call when session changes)
   */
  const clearSavedMessages = useCallback(() => {
    savedMessagesRef.current.clear()
  }, [])

  /**
   * Get the database ID for a temporary message ID
   */
  const getDbIdForTempId = useCallback((type: 'plan' | 'player', tempId: number): number | null => {
    const saved = savedMessagesRef.current.get(`${type}_${tempId}`)
    return saved?.id ?? null
  }, [])

  return {
    savePlanProposal,
    updatePlanProgress,
    updateMessageWithPlayerPreview,
    savePlayerPreview,
    clearSavedMessages,
    getDbIdForTempId,
  }
}
