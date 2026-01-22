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
      savedMessagesRef.current.set(`plan_${tempMessageId}`, { id: savedId, tempId: tempMessageId })
      
      console.log(`[UI_PERSIST] Saved plan proposal: tempId=${tempMessageId} dbId=${savedId}`)
      return savedId
    } catch (error) {
      console.error('[UI_PERSIST] Failed to save plan proposal:', error)
      return null
    }
  }, [sessionId])

  /**
   * Update a saved plan message with progress information.
   */
  const updatePlanProgress = useCallback(async (
    tempMessageId: number,
    progress: PlanProgress
  ): Promise<boolean> => {
    if (!sessionId) {
      console.warn('[UI_PERSIST] No session ID, cannot update plan progress')
      return false
    }

    const savedMessage = savedMessagesRef.current.get(`plan_${tempMessageId}`)
    if (!savedMessage) {
      console.warn(`[UI_PERSIST] No saved message found for tempId=${tempMessageId}`)
      return false
    }

    try {
      await chatAPI.updateUiMessage(sessionId, savedMessage.id, {
        metadata: {
          plan_progress: progress
        }
      })

      console.log(`[UI_PERSIST] Updated plan progress: tempId=${tempMessageId} dbId=${savedMessage.id} step=${progress.current_step_index + 1}/${progress.total_steps}`)
      return true
    } catch (error) {
      console.error('[UI_PERSIST] Failed to update plan progress:', error)
      return false
    }
  }, [sessionId])

  /**
   * Save a player preview message to the backend.
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
    savePlayerPreview,
    clearSavedMessages,
    getDbIdForTempId,
  }
}
