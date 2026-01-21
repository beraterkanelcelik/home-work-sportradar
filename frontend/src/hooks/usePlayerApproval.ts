/**
 * usePlayerApproval Hook
 *
 * Manages player approval logic for scouting workflow HITL Gate B.
 * Similar to useToolApproval but for player approval with 4 actions.
 */

import { useState, useCallback } from 'react'
import { toast } from 'sonner'
import { agentAPI } from '@/lib/api'
import { getErrorMessage } from '@/lib/utils'
import type { Message } from '@/state/useChatStore'

export interface PlayerPreviewData {
  player: Record<string, any>
  report_summary: string[]
  report_text: string
  db_payload_preview: Record<string, any>
}

interface UsePlayerApprovalProps {
  currentSession: { id: number } | null
  updateMessages: (updater: (messages: Message[]) => Message[]) => void
  loadMessages: (sessionId: number) => Promise<void>
}

export function usePlayerApproval({
  currentSession,
  updateMessages,
  loadMessages,
}: UsePlayerApprovalProps) {
  const [approvingPlayers, setApprovingPlayers] = useState<Set<number>>(new Set())

  /**
   * Approve player and save report
   */
  const handleApprovePlayer = useCallback(async (
    messageId: number,
    playerPreview: PlayerPreviewData
  ) => {
    if (!currentSession) {
      toast.error('No active session')
      return
    }

    if (approvingPlayers.has(messageId)) {
      console.log(`[PLAYER_APPROVAL] Already approving player for message ${messageId}`)
      return
    }

    console.log(`[PLAYER_APPROVAL] User approved player: message=${messageId} player=${playerPreview.player?.display_name}`)

    setApprovingPlayers(prev => new Set(prev).add(messageId))

    try {
      const response = await agentAPI.approvePlayer({
        chat_session_id: currentSession.id,
        resume: {
          action: 'approve'
        }
      })

      if (response.data.success) {
        toast.success('Player approved - saving to database...')
        console.log(`[PLAYER_APPROVAL] Player approved successfully: message=${messageId}`)

        // Reload messages to get saved player
        await loadMessages(currentSession.id)
      } else {
        toast.error(response.data.error || 'Player approval failed')
      }
    } catch (error: any) {
      console.error(`[PLAYER_APPROVAL] Error approving player:`, error, `session=${currentSession?.id}`)
      toast.error(getErrorMessage(error, 'Failed to approve player'))
    } finally {
      setApprovingPlayers(prev => {
        const next = new Set(prev)
        next.delete(messageId)
        return next
      })
    }
  }, [currentSession, updateMessages, loadMessages, approvingPlayers])

  /**
   * Reject player proposal
   */
  const handleRejectPlayer = useCallback(async (messageId: number) => {
    if (!currentSession) {
      toast.error('No active session')
      return
    }

    if (approvingPlayers.has(messageId)) {
      return
    }

    console.log(`[PLAYER_APPROVAL] User rejected player: message=${messageId}`)

    setApprovingPlayers(prev => new Set(prev).add(messageId))

    try {
      const response = await agentAPI.approvePlayer({
        chat_session_id: currentSession.id,
        resume: {
          action: 'reject'
        }
      })

      if (response.data.success) {
        toast.info('Player proposal rejected')
      } else {
        toast.error(response.data.error || 'Failed to reject player')
      }
    } catch (error: any) {
      console.error(`[PLAYER_APPROVAL] Error rejecting player:`, error, `session=${currentSession?.id}`)
      toast.error(getErrorMessage(error, 'Failed to reject player'))
    } finally {
      setApprovingPlayers(prev => {
        const next = new Set(prev)
        next.delete(messageId)
        return next
      })
    }
  }, [currentSession, approvingPlayers])

  /**
   * Edit wording - re-run compose only
   */
  const handleEditWording = useCallback(async (
    messageId: number,
    playerPreview: PlayerPreviewData
  ) => {
    if (!currentSession) {
      toast.error('No active session')
      return
    }

    if (approvingPlayers.has(messageId)) {
      return
    }

    console.log(`[PLAYER_APPROVAL] User requested edit wording: message=${messageId}`)

    setApprovingPlayers(prev => new Set(prev).add(messageId))

    try {
      const response = await agentAPI.approvePlayer({
        chat_session_id: currentSession.id,
        resume: {
          action: 'edit_wording'
        }
      })

      if (response.data.success) {
        toast.success('Re-running report composition...')
        console.log(`[PLAYER_APPROVAL] Edit wording initiated: message=${messageId}`)
      } else {
        toast.error(response.data.error || 'Failed to edit wording')
      }
    } catch (error: any) {
      console.error(`[PLAYER_APPROVAL] Error editing wording:`, error, `session=${currentSession?.id}`)
      toast.error(getErrorMessage(error, 'Failed to edit wording'))
    } finally {
      setApprovingPlayers(prev => {
        const next = new Set(prev)
        next.delete(messageId)
        return next
      })
    }
  }, [currentSession, approvingPlayers])

  /**
   * Edit content - re-run from build_queries with feedback
   */
  const handleEditContent = useCallback(async (
    messageId: number,
    playerPreview: PlayerPreviewData,
    feedback: string
  ) => {
    if (!currentSession) {
      toast.error('No active session')
      return
    }

    if (approvingPlayers.has(messageId)) {
      return
    }

    if (!feedback.trim()) {
      toast.error('Please provide feedback for content edit')
      return
    }

    console.log(`[PLAYER_APPROVAL] User requested edit content: message=${messageId} feedback=${feedback}`)

    setApprovingPlayers(prev => new Set(prev).add(messageId))

    try {
      const response = await agentAPI.approvePlayer({
        chat_session_id: currentSession.id,
        resume: {
          action: 'edit_content',
          feedback: feedback
        }
      })

      if (response.data.success) {
        toast.success('Re-running evidence retrieval with new hints...')
        console.log(`[PLAYER_APPROVAL] Edit content initiated: message=${messageId}`)
      } else {
        toast.error(response.data.error || 'Failed to edit content')
      }
    } catch (error: any) {
      console.error(`[PLAYER_APPROVAL] Error editing content:`, error, `session=${currentSession?.id}`)
      toast.error(getErrorMessage(error, 'Failed to edit content'))
    } finally {
      setApprovingPlayers(prev => {
        const next = new Set(prev)
        next.delete(messageId)
        return next
      })
    }
  }, [currentSession, approvingPlayers])

  return {
    handleApprovePlayer,
    handleRejectPlayer,
    handleEditWording,
    handleEditContent,
    approvingPlayers,
  }
}
