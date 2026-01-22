/**
 * PlayerPreview Component
 *
 * HITL Gate B UI for scouting workflow player approval.
 * Shows extracted player fields, report summary, and full report text.
 * User can approve, reject, edit wording, or edit content.
 */

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import JsonViewer from '@/components/JsonViewer'

export interface PlayerFields {
  display_name: string
  sport: 'nba' | 'football' | 'unknown'
  positions?: string[]
  teams?: string[]
  league?: string
  aliases?: string[]
  physical?: {
    height_cm?: number
    weight_kg?: number
    measurements?: Record<string, any>
  }
  scouting?: {
    strengths?: string[]
    weaknesses?: string[]
    style_tags?: string[]
    risk_notes?: string[]
    role_projection?: string
  }
}

export interface PlayerPreviewData {
  player: PlayerFields
  report_summary: string[]
  report_text: string
  db_payload_preview?: Record<string, any>
}

interface PlayerPreviewProps {
  preview: PlayerPreviewData
  onApprove: () => void
  onReject: () => void
  onEditWording?: () => void
  onEditContent?: (feedback: string) => void
  isExecuting?: boolean
  /** Whether the player has been approved/rejected (show collapsed summary) */
  isCompleted?: boolean
  /** The action taken: 'approved' | 'rejected' | undefined */
  completedAction?: 'approved' | 'rejected'
}

export default function PlayerPreview({
  preview,
  onApprove,
  onReject,
  onEditWording,
  onEditContent,
  isExecuting = false,
  isCompleted = false,
  completedAction,
}: PlayerPreviewProps) {
  const navigate = useNavigate()
  const [showFullReport, setShowFullReport] = useState(false)
  const [feedback, setFeedback] = useState('')

  const { player, report_summary, report_text } = preview

  const formatSportName = (sport: string): string => {
    return sport === 'nba' ? 'NBA' : sport === 'football' ? 'Football' : 'Unknown'
  }

  const handleEditContent = () => {
    if (onEditContent && feedback.trim()) {
      onEditContent(feedback)
      setFeedback('')
    }
  }

  // Collapsed view for completed (approved/rejected) player previews
  if (isCompleted) {
    const handleViewReport = () => {
      if (completedAction === 'approved') {
        navigate('/scout-reports')
      }
    }

    return (
      <div
        className={`border rounded-lg p-3 ${completedAction === 'approved' ? 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800 cursor-pointer hover:border-green-400 dark:hover:border-green-600 transition-colors' : 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800'}`}
        onClick={handleViewReport}
        role={completedAction === 'approved' ? 'button' : undefined}
        tabIndex={completedAction === 'approved' ? 0 : undefined}
        onKeyDown={(e) => {
          if (completedAction === 'approved' && (e.key === 'Enter' || e.key === ' ')) {
            handleViewReport()
          }
        }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-medium ${player.sport === 'nba' ? 'bg-blue-600' : player.sport === 'football' ? 'bg-green-600' : 'bg-gray-600'}`}>
              {player.sport === 'nba' ? '🏀' : player.sport === 'football' ? '⚽' : '❓'}
            </div>
            <div>
              <div className="font-semibold text-foreground">{player.display_name}</div>
              <div className="text-xs text-muted-foreground">
                {formatSportName(player.sport)}
                {player.positions && player.positions.length > 0 && ` • ${player.positions.join(', ')}`}
                {player.teams && player.teams.length > 0 && ` • ${player.teams.join(', ')}`}
              </div>
            </div>
          </div>
          <div className={`flex items-center gap-2 text-sm font-medium ${completedAction === 'approved' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
            {completedAction === 'approved' ? (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span>Player Saved</span>
                <svg className="w-4 h-4 ml-1 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                Rejected
              </>
            )}
          </div>
        </div>
        {completedAction === 'approved' && (
          <div className="text-xs text-green-600 dark:text-green-400 mt-2 text-right">
            Click to view in Scout Reports
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="border rounded-lg bg-muted/30 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-foreground">Player Preview</h3>
          <p className="text-sm text-muted-foreground mt-1">
            {player.display_name} • {formatSportName(player.sport)}
          </p>
        </div>
        {!isExecuting && (
          <div className="flex gap-2">
            {onEditWording && (
              <Button
                variant="outline"
                size="sm"
                onClick={onEditWording}
                className="text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
              >
                Edit Wording
              </Button>
            )}
            {onEditContent && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowFullReport(true)}
                className="text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
              >
                Edit Content
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={onReject}
              className="text-destructive hover:text-destructive"
            >
              Reject
            </Button>
            <Button
              size="sm"
              onClick={onApprove}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              Approve & Save
            </Button>
          </div>
        )}
        {isExecuting && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="w-2 h-2 bg-primary rounded-full animate-pulse"></div>
            <span>Saving player and report...</span>
          </div>
        )}
      </div>

      {/* Player Fields */}
      <div className="space-y-3">
        <div className="text-sm font-semibold text-muted-foreground">Player Information</div>
        <div className="border rounded-md p-3 bg-background/50 space-y-2">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-muted-foreground">Display Name</div>
              <div className="text-sm font-medium">{player.display_name}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Sport</div>
              <div className="text-sm font-medium">{formatSportName(player.sport)}</div>
            </div>
            {player.positions && (
              <div>
                <div className="text-xs text-muted-foreground">Positions</div>
                <div className="text-sm font-medium">{player.positions.join(', ')}</div>
              </div>
            )}
            {player.teams && (
              <div>
                <div className="text-xs text-muted-foreground">Teams</div>
                <div className="text-sm font-medium">{player.teams.join(', ')}</div>
              </div>
            )}
            {player.league && (
              <div>
                <div className="text-xs text-muted-foreground">League</div>
                <div className="text-sm font-medium">{player.league}</div>
              </div>
            )}
          </div>
          {player.aliases && player.aliases.length > 0 && (
            <div>
              <div className="text-xs text-muted-foreground">Aliases</div>
              <div className="text-sm font-medium">{player.aliases.join(', ')}</div>
            </div>
          )}
          {player.physical && (
            <div className="grid grid-cols-3 gap-4 mt-2 pt-2 border-t">
              {player.physical.height_cm && (
                <div>
                  <div className="text-xs text-muted-foreground">Height</div>
                  <div className="text-sm font-medium">{player.physical.height_cm} cm</div>
                </div>
              )}
              {player.physical.weight_kg && (
                <div>
                  <div className="text-xs text-muted-foreground">Weight</div>
                  <div className="text-sm font-medium">{player.physical.weight_kg} kg</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Scouting Attributes */}
      {player.scouting && (
        <div className="space-y-3">
          <div className="text-sm font-semibold text-muted-foreground">Scouting Assessment</div>
          <div className="border rounded-md p-3 bg-background/50 space-y-2">
            {player.scouting.strengths && player.scouting.strengths.length > 0 && (
              <div>
                <div className="text-xs text-muted-foreground">Strengths</div>
                <div className="flex flex-wrap gap-1">
                  {player.scouting.strengths.map((strength, idx) => (
                    <span key={idx} className="text-xs px-2 py-1 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded">
                      {strength}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {player.scouting.weaknesses && player.scouting.weaknesses.length > 0 && (
              <div>
                <div className="text-xs text-muted-foreground">Weaknesses</div>
                <div className="flex flex-wrap gap-1">
                  {player.scouting.weaknesses.map((weakness, idx) => (
                    <span key={idx} className="text-xs px-2 py-1 bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 rounded">
                      {weakness}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {player.scouting.style_tags && player.scouting.style_tags.length > 0 && (
              <div>
                <div className="text-xs text-muted-foreground">Style Tags</div>
                <div className="flex flex-wrap gap-1">
                  {player.scouting.style_tags.map((tag, idx) => (
                    <span key={idx} className="text-xs px-2 py-1 bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 rounded">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {player.scouting.role_projection && (
              <div>
                <div className="text-xs text-muted-foreground">Role Projection</div>
                <div className="text-sm font-medium">{player.scouting.role_projection}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Report Summary */}
      {report_summary && report_summary.length > 0 && (
        <div className="space-y-3">
          <div className="text-sm font-semibold text-muted-foreground">Report Summary</div>
          <div className="border rounded-md p-3 bg-background/50">
            <ul className="space-y-1">
              {report_summary.map((point, idx) => (
                <li key={idx} className="text-sm text-foreground flex items-start gap-2">
                  <span className="text-primary">•</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Report Text - Toggle */}
      <div className="space-y-3">
        <button
          onClick={() => setShowFullReport(!showFullReport)}
          className="text-sm text-primary hover:underline"
        >
          {showFullReport ? 'Hide Full Report' : 'Show Full Report'}
        </button>
        {showFullReport && (
          <div className="border rounded-md p-3 bg-background/50">
            <div className="text-sm whitespace-pre-wrap text-foreground">
              {report_text}
            </div>
          </div>
        )}
      </div>

      {/* Edit Content Feedback */}
      {showFullReport && onEditContent && (
        <div className="space-y-3 pt-3 border-t">
          <div className="text-sm font-semibold text-muted-foreground">
            Feedback for Content Edit
          </div>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Describe what additional information should be gathered..."
            className="w-full min-h-24 rounded-md border bg-background p-2 text-sm"
          />
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowFullReport(false)
                setFeedback('')
              }}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleEditContent}
              disabled={!feedback.trim()}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              Submit & Re-run
            </Button>
          </div>
        </div>
      )}

      {!isExecuting && (
        <div className="text-xs text-muted-foreground pt-2 border-t">
          Approving will create a new player record and save the scouting report to the database.
        </div>
      )}
    </div>
  )
}
