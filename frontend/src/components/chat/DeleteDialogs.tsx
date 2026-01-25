/**
 * DeleteDialogs Component
 * 
 * Handles confirmation dialogs for deleting chat sessions.
 * 
 * Features:
 * - Single session delete confirmation
 * - Delete all sessions confirmation
 * - Prevents accidental deletions
 * 
 * Location: frontend/src/components/chat/DeleteDialogs.tsx
 */

import React from 'react'
import { Button } from '@/components/ui/button'

interface DeleteDialogsProps {
  /** Whether the single session delete dialog is open */
  deleteDialogOpen: boolean
  /** Whether the delete all sessions dialog is open */
  deleteAllDialogOpen: boolean
  /** ID of the session to delete (null if none selected) */
  sessionToDelete: number | null
  /** Total number of sessions (for delete all confirmation) */
  sessionCount: number
  /** Callback when user confirms single session delete */
  onConfirmDelete: () => void
  /** Callback when user cancels single session delete */
  onCancelDelete: () => void
  /** Callback when user confirms delete all sessions */
  onConfirmDeleteAll: () => void
  /** Callback when user cancels delete all sessions */
  onCancelDeleteAll: () => void
}

/**
 * DeleteDialogs - Confirmation dialogs for session deletion
 * 
 * This component renders two modal dialogs:
 * 1. Single session delete confirmation
 * 2. Delete all sessions confirmation
 * 
 * Both dialogs use a backdrop overlay and prevent accidental clicks outside.
 */
export default function DeleteDialogs({
  deleteDialogOpen,
  deleteAllDialogOpen,
  sessionToDelete,
  sessionCount,
  onConfirmDelete,
  onCancelDelete,
  onConfirmDeleteAll,
  onCancelDeleteAll,
}: DeleteDialogsProps) {
  return (
    <>
      {/* Single Session Delete Confirmation Dialog */}
      {deleteDialogOpen && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" 
          onClick={onCancelDelete}
        >
          <div 
            className="bg-background border rounded-lg p-6 max-w-md w-full mx-4 shadow-lg" 
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold mb-2">Delete Chat Session</h3>
            <p className="text-muted-foreground mb-6">
              Are you sure you want to delete this chat session? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={onCancelDelete}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={onConfirmDelete}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete All Sessions Confirmation Dialog */}
      {deleteAllDialogOpen && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" 
          onClick={onCancelDeleteAll}
        >
          <div 
            className="bg-background border rounded-lg p-6 max-w-md w-full mx-4 shadow-lg" 
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold mb-2">Delete All Chat Sessions</h3>
            <p className="text-muted-foreground mb-6">
              Are you sure you want to delete all {sessionCount} chat session{sessionCount !== 1 ? 's' : ''}? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={onCancelDeleteAll}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={onConfirmDeleteAll}>
                Delete All
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
