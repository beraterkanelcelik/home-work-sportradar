/**
 * usePlayerApproval Hook
 *
 * Manages player approval logic for scouting workflow HITL Gate B.
 * Handles approve and reject actions for player previews.
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
  db_payload_preview?: Record<string, any>
}

interface UsePlayerApprovalProps {
  currentSession: { id: number } | null
  updateMessages: (updater: (messages: Message[]) => Message[]) => void
  /** Callback to open a new SSE stream after approval to receive execution events.
   *  Accepts optional planMessageId for consistency with plan approval.
   */
  onResumeStream?: (planMessageId?: number) => void
}

export function usePlayerApproval({
  currentSession,
  updateMessages,
  onResumeStream,
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

        // Mark the player preview as approved
        updateMessages((messages) =>
          messages.map((msg) =>
            msg.id === messageId
              ? { ...msg, player_preview_status: 'approved' as const }
              : msg
          )
        )

        // Open resume stream to receive final response after save
        if (onResumeStream) {
          console.log(`[PLAYER_APPROVAL] Triggering resume stream`)
          onResumeStream()
        }
        // No fallback loadMessages - stream handles all updates
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
  }, [currentSession, updateMessages, approvingPlayers, onResumeStream])

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
        
        // Mark the player preview as rejected
        updateMessages((messages) =>
          messages.map((msg) =>
            msg.id === messageId
              ? { ...msg, player_preview_status: 'rejected' as const }
              : msg
          )
        )
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
  }, [currentSession, approvingPlayers, updateMessages])

  return {
    handleApprovePlayer,
    handleRejectPlayer,
    approvingPlayers,
  }
}
