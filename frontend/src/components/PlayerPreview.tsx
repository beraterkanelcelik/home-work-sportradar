/**
 * PlayerPreview Component
 *
 * HITL Gate B UI for scouting workflow player approval.
 * Shows extracted player fields, report summary, and full report text.
 * User can approve, reject, edit wording, or edit content.
 */

import React, { useState } from 'react'
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
}

export default function PlayerPreview({
  preview,
  onApprove,
  onReject,
  onEditWording,
  onEditContent,
  isExecuting = false
}: PlayerPreviewProps) {
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
