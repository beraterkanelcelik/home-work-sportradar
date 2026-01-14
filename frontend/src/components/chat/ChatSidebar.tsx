/**
 * ChatSidebar Component
 * 
 * Sidebar displaying chat sessions list with management features.
 * 
 * Features:
 * - Collapsible chats section
 * - New chat button
 * - Session list with selection
 * - Session rename functionality
 * - Session delete (via menu)
 * - Session menu (three dots) with rename/delete options
 * 
 * Location: frontend/src/components/chat/ChatSidebar.tsx
 */

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'

interface ChatSession {
  id: number
  title: string
  updated_at: string
}

interface ChatSidebarProps {
  /** Whether sidebar is open */
  sidebarOpen: boolean
  /** Array of chat sessions */
  sessions: ChatSession[]
  /** Currently selected session */
  currentSession: ChatSession | null
  /** Whether sessions are loading */
  loading: boolean
  /** Whether chats section is open */
  chatsSectionOpen: boolean
  /** Callback to toggle chats section */
  onToggleChatsSection: () => void
  /** Callback to create new chat */
  onNewChat: () => Promise<void>
  /** Callback to select a session */
  onSelectSession: (sessionId: number) => void
  /** Callback to rename a session */
  onRenameSession: (sessionId: number, currentTitle: string) => void
  /** Callback to delete a session */
  onDeleteSession: (sessionId: number, e?: React.MouseEvent) => void
  /** ID of session being renamed (null if none) */
  renameSessionId: number | null
  /** Title for session being renamed */
  renameSessionTitle: string
  /** Callback when rename title changes */
  setRenameSessionTitle: (title: string) => void
  /** Callback to save rename */
  onSaveRename: () => Promise<void>
  /** Callback to cancel rename */
  onCancelRename: () => void
  /** ID of session with open menu (null if none) */
  sessionMenuOpen: number | null
  /** Callback to set session menu open */
  setSessionMenuOpen: (sessionId: number | null) => void
  /** Callback to close sidebar (for mobile) */
  onClose?: () => void
}

/**
 * ChatSidebar - Sidebar with chat sessions list
 * 
 * This component provides:
 * 1. Collapsible "Chats" section header
 * 2. "New Chat" button
 * 3. List of chat sessions with:
 *    - Active session highlighting
 *    - Click to select
 *    - Hover menu (three dots) with rename/delete
 *    - Inline rename editing
 * 4. Loading and empty states
 */
export default function ChatSidebar({
  sidebarOpen,
  sessions,
  currentSession,
  loading,
  chatsSectionOpen,
  onToggleChatsSection,
  onNewChat,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
  renameSessionId,
  renameSessionTitle,
  setRenameSessionTitle,
  onSaveRename,
  onCancelRename,
  sessionMenuOpen,
  setSessionMenuOpen,
  onClose,
}: ChatSidebarProps) {
  // Handle session selection on mobile - close sidebar after selection
  const handleSelectSession = (sessionId: number) => {
    onSelectSession(sessionId)
    // Close sidebar on mobile after selection
    if (onClose && window.innerWidth < 768) {
      onClose()
    }
  }

  // Handle new chat on mobile - close sidebar after creation
  const handleNewChat = async () => {
    await onNewChat()
    // Close sidebar on mobile after creation
    if (onClose && window.innerWidth < 768) {
      onClose()
    }
  }

  return (
    <>
      {/* Mobile Backdrop - only show when sidebar is open on mobile */}
      {sidebarOpen && onClose && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden transition-opacity"
          onClick={onClose}
        />
      )}
      
      {/* Sidebar */}
      <div className={`
        ${sidebarOpen ? 'w-[280px] max-w-[85vw] md:w-64' : 'w-0 md:w-0'}
        fixed md:relative
        top-0 left-0 md:left-auto
        h-full md:h-auto
        transition-all duration-300
        overflow-hidden border-r
        flex flex-col bg-background
        z-50 md:z-auto
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
      `}>
        <div className="flex-1 overflow-y-auto min-w-0">
        {/* Chats Section Header */}
        <div className="px-3 py-2 space-y-2">
          <div className="flex items-center justify-between">
            <button
              onClick={onToggleChatsSection}
              className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              <span>Chats</span>
              <svg
                className={`w-4 h-4 transition-transform ${chatsSectionOpen ? 'rotate-90' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          {chatsSectionOpen && (
            <Button onClick={handleNewChat} className="w-full" size="sm">
              New Chat
            </Button>
          )}
        </div>

        {chatsSectionOpen && (
          <>
            {loading && sessions.length === 0 ? (
              <div className="px-3 py-2 text-center text-muted-foreground text-sm">Loading...</div>
            ) : sessions.length === 0 ? (
              <div className="px-3 py-2 text-center text-muted-foreground text-sm">
                No chats yet
              </div>
            ) : (
              <div>
                {sessions.map((session) => (
                  <div
                    key={session.id}
                    className={`group relative px-3 py-2 mx-2 rounded-lg cursor-pointer transition-colors ${
                      currentSession?.id === session.id 
                        ? 'bg-primary/10 hover:bg-primary/15' 
                        : 'hover:bg-muted/50'
                    }`}
                  >
                    {renameSessionId === session.id ? (
                      // Rename Mode
                      <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="text"
                          value={renameSessionTitle}
                          onChange={(e) => setRenameSessionTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              onSaveRename()
                            } else if (e.key === 'Escape') {
                              onCancelRename()
                            }
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="flex-1 px-2 py-1 text-sm border rounded bg-background"
                          autoFocus
                        />
                        <button
                          onClick={onSaveRename}
                          className="p-1 hover:bg-muted rounded"
                          title="Save"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        </button>
                        <button
                          onClick={onCancelRename}
                          className="p-1 hover:bg-muted rounded"
                          title="Cancel"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ) : (
                      // Normal Mode
                      <>
                        <div
                          onClick={() => {
                            handleSelectSession(session.id)
                          }}
                          className="flex items-center justify-between"
                        >
                          <div className="flex-1 min-w-0">
                            <p className={`text-sm truncate ${
                              currentSession?.id === session.id 
                                ? 'font-semibold text-foreground' 
                                : 'font-medium'
                            }`}>
                              {session.title || 'Untitled Chat'}
                            </p>
                          </div>
                          <button
                            onClick={(e: React.MouseEvent) => {
                              e.stopPropagation()
                              setSessionMenuOpen(sessionMenuOpen === session.id ? null : session.id)
                            }}
                            className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-muted rounded"
                            title="More options"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
                            </svg>
                          </button>
                        </div>

                        {/* Three-dot menu dropdown */}
                        {sessionMenuOpen === session.id && (
                          <>
                            <div
                              className="fixed inset-0 z-10"
                              onClick={() => setSessionMenuOpen(null)}
                            />
                            <div className="absolute right-0 top-full mt-1 w-48 bg-background border rounded-lg shadow-lg p-1 z-20">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onRenameSession(session.id, session.title || '')
                                }}
                                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted rounded-md transition-colors text-left text-sm"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                </svg>
                                <span>Rename</span>
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onDeleteSession(session.id, e)
                                }}
                                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted rounded-md transition-colors text-left text-sm text-destructive"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                                <span>Delete</span>
                              </button>
                            </div>
                          </>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
    </>
  )
}
