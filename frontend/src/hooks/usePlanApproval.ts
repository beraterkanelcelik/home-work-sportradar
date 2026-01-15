/**
 * usePlanApproval Hook
 *
 * Manages plan approval logic for human-in-the-loop workflows.
 * Similar to useToolApproval but for plan proposals.
 */

import { useState, useCallback } from 'react'
import { toast } from 'sonner'
import { agentAPI } from '@/lib/api'
import { getErrorMessage } from '@/lib/utils'
import type { Message } from '@/state/useChatStore'

export interface PlanProposalData {
  type: string
  plan: Array<{
    action: string
    tool: string
    props: Record<string, any>
    agent: string
    query: string
  }>
  plan_index: number
  plan_total: number
}

interface UsePlanApprovalProps {
  currentSession: { id: number } | null
  updateMessages: (updater: (messages: Message[]) => Message[]) => void
  setExecutingPlanMessageId: (id: number | null) => void
}

export function usePlanApproval({
  currentSession,
  updateMessages,
  setExecutingPlanMessageId,
}: UsePlanApprovalProps) {
  const [approvingPlans, setApprovingPlans] = useState<Set<number>>(new Set())

  const handleApprovePlan = useCallback(async (
    messageId: number,
    plan: PlanProposalData
  ) => {
    if (!currentSession) {
      toast.error('No active session')
      return
    }

    // Prevent double-click
    if (approvingPlans.has(messageId)) {
      console.log(`[PLAN_APPROVAL] Already approving plan for message ${messageId}`)
      return
    }

    console.log(`[PLAN_APPROVAL] User approved plan: message=${messageId} steps=${plan.plan_total}`)

    setApprovingPlans(prev => new Set(prev).add(messageId))
    setExecutingPlanMessageId(messageId)

    try {
      const response = await agentAPI.approvePlan({
        chat_session_id: currentSession.id,
        resume: {
          approved: true
        }
      })

      if (response.data.success) {
        toast.success('Plan approved - executing...')
        console.log(`[PLAN_APPROVAL] Plan approved successfully: message=${messageId}, keeping connection open for results`)
        // Keep setExecutingPlanMessageId set - don't clear it yet
        // It will be cleared when the stream completes
      } else {
        toast.error(response.data.error || 'Plan approval failed')
        setExecutingPlanMessageId(null)
      }
    } catch (error: any) {
      console.error(`[PLAN_APPROVAL] Error approving plan:`, error)
      toast.error(getErrorMessage(error, 'Failed to approve plan'))
      setExecutingPlanMessageId(null)
    } finally {
      setApprovingPlans(prev => {
        const next = new Set(prev)
        next.delete(messageId)
        return next
      })
    }
  }, [currentSession, approvingPlans, setExecutingPlanMessageId])

  const handleRejectPlan = useCallback(async (messageId: number) => {
    if (!currentSession) {
      toast.error('No active session')
      return
    }

    console.log(`[PLAN_APPROVAL] User rejected plan: message=${messageId}`)

    try {
      const response = await agentAPI.approvePlan({
        chat_session_id: currentSession.id,
        resume: {
          approved: false,
          reason: 'User rejected plan'
        }
      })

      if (response.data.success) {
        toast.info('Plan rejected')
      } else {
        toast.error(response.data.error || 'Failed to reject plan')
      }
    } catch (error: any) {
      console.error(`[PLAN_APPROVAL] Error rejecting plan:`, error)
      toast.error(getErrorMessage(error, 'Failed to reject plan'))
    }
  }, [currentSession])

  return {
    handleApprovePlan,
    handleRejectPlan,
    approvingPlans,
  }
}
