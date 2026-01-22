/**
 * MessageList Component
 * 
 * Container component for displaying chat messages.
 * 
 * Features:
 * - Renders list of messages using MessageItem
 * - Handles message deduplication
 * - Auto-scrolls to bottom when messages change
 * - Handles empty state
 * 
 * Location: frontend/src/components/chat/MessageList.tsx
 */

import React, { useEffect } from 'react'
import type { Message } from '@/state/useChatStore'
import type { PlanProposalData } from '@/components/PlanProposal'
import type { PlayerPreviewData } from '@/components/PlayerPreview'
import MessageItem, { type MessageItemProps } from './MessageItem'

interface MessageListProps {
  /** Ref to the scrollable container */
  scrollContainerRef?: React.RefObject<HTMLDivElement>
  /** Array of messages to display */
  messages: Message[]
  /** Set of message IDs that have completed streaming */
  streamComplete: Set<number>
  /** Set of expanded tool call IDs */
  expandedToolCalls: Set<string>
  /** Callback to toggle tool call expansion */
  onToggleToolCall: (toolCallId: string) => void
  /** Callback when user approves a tool call */
  onApproveTool: (messageId: number, toolCall: any, toolCallId: string, toolName: string) => Promise<void>
  /** Callback when user rejects a tool call */
  onRejectTool?: (messageId: number, toolCall: any, toolCallId: string, toolName: string) => Promise<void>
  /** Set of tool call IDs currently being approved */
  approvingToolCalls: Set<string>
  /** Current session (required for tool approval) */
  currentSession: { id: number } | null
  /** Callback when user approves a plan */
  onPlanApproval: (messageId: number, plan: PlanProposalData) => Promise<void>
  /** Callback when user rejects a plan */
  onPlanRejection: (messageId: number) => void
  /** ID of message currently executing a plan */
  executingPlanMessageId: number | null
  /** Callback when user approves a player */
  onApprovePlayer?: (messageId: number, playerPreview: PlayerPreviewData) => Promise<void>
  /** Callback when user rejects a player */
  onRejectPlayer?: (messageId: number) => void
  /** Set of player message IDs currently being approved */
  approvingPlayers?: Set<number>
  /** User email (for user avatar) */
  userEmail?: string | null
}

/**
 * MessageList - Container for chat messages
 * 
 * This component:
 * 1. Deduplicates messages by ID
 * 2. Renders each message using MessageItem
 * 3. Auto-scrolls to bottom when messages change
 * 4. Handles empty state (no messages)
 */
export default function MessageList({
  scrollContainerRef,
  messages,
  streamComplete,
  expandedToolCalls,
  onToggleToolCall,
  onApproveTool,
  onRejectTool,
  approvingToolCalls,
  currentSession,
  onPlanApproval,
  onPlanRejection,
  executingPlanMessageId,
  onApprovePlayer,
  onRejectPlayer,
  approvingPlayers,
  userEmail,
}: MessageListProps) {
  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollContainerRef?.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
    }
  }, [messages, scrollContainerRef])

  // Deduplicate messages by ID before rendering
  // Keep array order intact - status messages are inserted at correct positions
  const seenIds = new Set<number>()
  const uniqueMessages = messages.filter((msg: Message) => {
    if (seenIds.has(msg.id)) {
      return false
    }
    seenIds.add(msg.id)
    return true
  })

  if (uniqueMessages.length === 0) {
    return null
  }

  return (
    <div className="max-w-full sm:max-w-3xl mx-auto px-2 sm:px-4 py-4 sm:py-8">
      <div className="space-y-4 sm:space-y-6">
        {uniqueMessages.map((msg: Message) => (
          <MessageItem
            key={msg.id}
            message={msg}
            messages={messages}
            streamComplete={streamComplete}
            expandedToolCalls={expandedToolCalls}
            onToggleToolCall={onToggleToolCall}
            onApproveTool={onApproveTool}
            onRejectTool={onRejectTool}
            approvingToolCalls={approvingToolCalls}
            currentSession={currentSession}
            onPlanApproval={onPlanApproval}
            onPlanRejection={onPlanRejection}
            executingPlanMessageId={executingPlanMessageId}
            onApprovePlayer={onApprovePlayer}
            onRejectPlayer={onRejectPlayer}
            approvingPlayers={approvingPlayers}
            userEmail={userEmail}
          />
        ))}
      </div>
    </div>
  )
}
