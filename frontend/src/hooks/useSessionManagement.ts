/**
 * useSessionManagement Hook
 * 
 * Manages chat session CRUD operations.
 * 
 * Features:
 * - Create new sessions
 * - Select sessions
 * - Rename sessions
 * - Delete sessions (single and all)
 * 
 * Location: frontend/src/hooks/useSessionManagement.ts
 */

import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { chatAPI } from '@/lib/api'
import { getErrorMessage } from '@/lib/utils'
import type { ChatSession } from '@/state/useChatStore'

interface UseSessionManagementProps {
  /** Function to create a new session in the store */
  createSession: () => Promise<ChatSession | null>
  /** Function to load a session */
  loadSession: (sessionId: number) => Promise<void>
  /** Function to delete a session */
  deleteSession: (sessionId: number) => Promise<void>
  /** Function to delete all sessions */
  deleteAllSessions: () => Promise<void>
  /** Current session */
  currentSession: ChatSession | null
}

/**
 * useSessionManagement - Hook for managing chat sessions
 * 
 * Returns:
 * - handleNewChat: Create a new chat session and navigate to it
 * - handleSelectSession: Load and select a session
 * - handleRenameSession: Start renaming a session
 * - handleSaveRename: Save the renamed session
 * - handleCancelRename: Cancel renaming
 * - handleDeleteSession: Delete a session (shows confirmation)
 * - handleDeleteCurrentChat: Delete the current chat
 * - handleDeleteAllSessions: Delete all sessions (shows confirmation)
 * - confirmDeleteSession: Confirm and execute session deletion
 * - confirmDeleteAllSessions: Confirm and execute delete all
 */
export function useSessionManagement({
  createSession,
  loadSession,
  deleteSession,
  deleteAllSessions,
  currentSession,
}: UseSessionManagementProps) {
  const navigate = useNavigate()

  const handleNewChat = useCallback(async () => {
    const newSession = await createSession()
    if (newSession) {
      navigate(`/chat/${newSession.id}`)
    }
  }, [createSession, navigate])

  const handleSelectSession = useCallback((id: number) => {
    navigate(`/chat/${id}`)
  }, [navigate])

  const handleRenameSession = useCallback((sessionId: number, currentTitle: string) => {
    // This is handled by parent component state
    // Return the sessionId and title for parent to manage
    return { sessionId, currentTitle }
  }, [])

  const handleSaveRename = useCallback(async (
    sessionId: number,
    newTitle: string
  ) => {
    try {
      await chatAPI.updateSessionTitle(sessionId, newTitle)
      toast.success('Session renamed successfully')
      // Reload session to get updated title
      await loadSession(sessionId)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to rename session'))
      throw error
    }
  }, [loadSession])

  const handleDeleteSession = useCallback((id: number, e?: React.MouseEvent) => {
    // This triggers the delete confirmation dialog
    // Return the session ID for parent to manage dialog state
    return id
  }, [])

  const handleDeleteCurrentChat = useCallback(() => {
    if (currentSession) {
      // Trigger delete confirmation for current session
      return currentSession.id
    }
    return null
  }, [currentSession])

  const confirmDeleteSession = useCallback(async (sessionId: number) => {
    await deleteSession(sessionId)
    if (currentSession?.id === sessionId) {
      navigate('/chat')
    }
  }, [deleteSession, currentSession, navigate])

  const confirmDeleteAllSessions = useCallback(async () => {
    try {
      await deleteAllSessions()
      navigate('/chat')
      toast.success('All chat sessions deleted successfully')
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to delete all sessions'))
      throw error
    }
  }, [deleteAllSessions, navigate])

  return {
    handleNewChat,
    handleSelectSession,
    handleRenameSession,
    handleSaveRename,
    handleDeleteSession,
    handleDeleteCurrentChat,
    confirmDeleteSession,
    confirmDeleteAllSessions,
  }
}
