/**
 * ScoutReportsPage Component
 *
 * Displays all saved scouting reports with filtering, search, and detail view.
 */

import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/state/useAuthStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toast } from 'sonner'
import { agentAPI } from '@/lib/api'
import { getErrorMessage } from '@/lib/utils'
import { Search, Filter, X, ChevronLeft, Download, Trash2 } from 'lucide-react'

interface PlayerData {
  id: string
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

interface ScoutingReport {
  id: string
  player: PlayerData
  report_text: string
  report_summary: string[]
  coverage: {
    found: string[]
    missing: string[]
    confidence: 'low' | 'med' | 'high'
  }
  created_at: string
  run_id?: string
  request_text?: string
  source_doc_ids?: string[]
}

export default function ScoutReportsPage() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  
  const [reports, setReports] = useState<ScoutingReport[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [sportFilter, setSportFilter] = useState<'all' | 'nba' | 'football' | 'unknown'>('all')
  const [selectedReport, setSelectedReport] = useState<ScoutingReport | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [reportToDelete, setReportToDelete] = useState<ScoutingReport | null>(null)
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    loadReports()
  }, [])

  const loadReports = async () => {
    if (!user) return
    
    setLoading(true)
    setError(null)
    
    try {
      const response = await agentAPI.listScoutReports()
      setReports(response.data.reports || [])
    } catch (err: any) {
      setError(getErrorMessage(err, 'Failed to load scout reports'))
      toast.error(getErrorMessage(err, 'Failed to load scout reports'))
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteReport = async (report: ScoutingReport) => {
    setDeleting(true)
    try {
      await agentAPI.deleteScoutReport(report.id)
      setReports(prev => prev.filter(r => r.id !== report.id))
      toast.success(`Deleted report for ${report.player.display_name}`)
      setDeleteDialogOpen(false)
      setReportToDelete(null)
      // If viewing detail of deleted report, go back to list
      if (selectedReport?.id === report.id) {
        setSelectedReport(null)
      }
    } catch (err: any) {
      toast.error(getErrorMessage(err, 'Failed to delete report'))
    } finally {
      setDeleting(false)
    }
  }

  const handleDeleteAllReports = async () => {
    setDeleting(true)
    try {
      await agentAPI.deleteAllScoutReports()
      setReports([])
      toast.success('All reports deleted')
      setDeleteAllDialogOpen(false)
      setSelectedReport(null)
    } catch (err: any) {
      toast.error(getErrorMessage(err, 'Failed to delete reports'))
    } finally {
      setDeleting(false)
    }
  }

  const handleFilter = (sport: 'nba' | 'football' | 'unknown' | 'all') => {
    setSportFilter(sport)
  }

  const filteredReports = reports.filter(report => {
    // Search filter
    const matchesSearch = searchTerm === '' || 
      report.player.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (report.report_summary && report.report_summary.some((bullet: string) => 
        bullet.toLowerCase().includes(searchTerm.toLowerCase())
      )) ||
      (report.report_text && report.report_text.toLowerCase().includes(searchTerm.toLowerCase()))
    
    // Sport filter
    const matchesSport = sportFilter === 'all' || report.player.sport === sportFilter
    
    return matchesSearch && matchesSport
  })

  const getConfidenceColor = (confidence: string): string => {
    switch (confidence) {
      case 'high':
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
      case 'med':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
      case 'low':
        return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200'
    }
  }

  const formatSportName = (sport: string): string => {
    return sport === 'nba' ? 'NBA' : sport === 'football' ? 'Football' : 'Unknown'
  }

  const getSportIcon = (sport: string): string => {
    return sport === 'nba' ? '🏀' : sport === 'football' ? '⚽' : '❓'
  }

  const getSportColor = (sport: string): string => {
    return sport === 'nba'
      ? 'bg-blue-600'
      : sport === 'football'
      ? 'bg-green-600'
      : 'bg-gray-600'
  }

  // Detail View Component
  const ReportDetailView = ({ report, onClose }: { report: ScoutingReport; onClose: () => void }) => {
    const { player } = report

    const handleDownloadPDF = () => {
      // Create a printable HTML content
      const printContent = `
        <!DOCTYPE html>
        <html>
        <head>
          <title>Scout Report - ${player.display_name}</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; }
            h1 { color: #1a1a1a; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }
            h2 { color: #374151; margin-top: 24px; font-size: 18px; }
            .header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
            .avatar { width: 60px; height: 60px; border-radius: 50%; background: ${player.sport === 'nba' ? '#2563eb' : player.sport === 'football' ? '#16a34a' : '#6b7280'}; display: flex; align-items: center; justify-content: center; color: white; font-size: 24px; }
            .meta { color: #6b7280; font-size: 14px; }
            .section { margin-bottom: 24px; padding: 16px; background: #f9fafb; border-radius: 8px; }
            .tag { display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; margin: 4px; }
            .tag-green { background: #dcfce7; color: #166534; }
            .tag-red { background: #fee2e2; color: #991b1b; }
            .tag-blue { background: #dbeafe; color: #1e40af; }
            .tag-orange { background: #ffedd5; color: #9a3412; }
            .bullet { color: #3b82f6; font-weight: bold; margin-right: 8px; }
            .report-text { white-space: pre-wrap; line-height: 1.6; }
            .confidence { padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }
            .confidence-high { background: #dcfce7; color: #166534; }
            .confidence-med { background: #fef3c7; color: #92400e; }
            .confidence-low { background: #fee2e2; color: #991b1b; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
            .field-label { font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }
            .field-value { font-size: 14px; color: #1a1a1a; margin-top: 4px; }
            @media print { body { padding: 20px; } }
          </style>
        </head>
        <body>
          <div class="header">
            <div class="avatar">${player.sport === 'nba' ? '🏀' : player.sport === 'football' ? '⚽' : '❓'}</div>
            <div>
              <h1 style="margin: 0; border: none; padding: 0;">${player.display_name}</h1>
              <div class="meta">
                ${formatSportName(player.sport)}
                ${player.positions && player.positions.length > 0 ? ` • ${player.positions.join(', ')}` : ''}
                ${player.teams && player.teams.length > 0 ? ` • ${player.teams.join(', ')}` : ''}
              </div>
              <div style="margin-top: 8px;">
                <span class="confidence confidence-${report.coverage?.confidence || 'low'}">${report.coverage?.confidence || 'unknown'} confidence</span>
                <span class="meta" style="margin-left: 12px;">Created ${new Date(report.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          </div>

          <div class="section">
            <h2 style="margin-top: 0;">Player Information</h2>
            <div class="grid">
              <div><div class="field-label">Display Name</div><div class="field-value">${player.display_name}</div></div>
              <div><div class="field-label">Sport</div><div class="field-value">${formatSportName(player.sport)}</div></div>
              ${player.league ? `<div><div class="field-label">League</div><div class="field-value">${player.league}</div></div>` : ''}
              ${player.positions && player.positions.length > 0 ? `<div><div class="field-label">Positions</div><div class="field-value">${player.positions.join(', ')}</div></div>` : ''}
              ${player.teams && player.teams.length > 0 ? `<div><div class="field-label">Teams</div><div class="field-value">${player.teams.join(', ')}</div></div>` : ''}
              ${player.aliases && player.aliases.length > 0 ? `<div><div class="field-label">Aliases</div><div class="field-value">${player.aliases.join(', ')}</div></div>` : ''}
            </div>
            ${player.physical && (player.physical.height_cm || player.physical.weight_kg) ? `
              <h3 style="margin-top: 16px; font-size: 14px; color: #6b7280;">Physical Attributes</h3>
              <div class="grid">
                ${player.physical.height_cm ? `<div><div class="field-label">Height</div><div class="field-value">${player.physical.height_cm} cm</div></div>` : ''}
                ${player.physical.weight_kg ? `<div><div class="field-label">Weight</div><div class="field-value">${player.physical.weight_kg} kg</div></div>` : ''}
              </div>
            ` : ''}
          </div>

          ${player.scouting ? `
            <div class="section">
              <h2 style="margin-top: 0;">Scouting Assessment</h2>
              ${player.scouting.strengths && player.scouting.strengths.length > 0 ? `
                <div style="margin-bottom: 12px;">
                  <div class="field-label">Strengths</div>
                  <div>${player.scouting.strengths.map(s => `<span class="tag tag-green">${s}</span>`).join('')}</div>
                </div>
              ` : ''}
              ${player.scouting.weaknesses && player.scouting.weaknesses.length > 0 ? `
                <div style="margin-bottom: 12px;">
                  <div class="field-label">Weaknesses</div>
                  <div>${player.scouting.weaknesses.map(w => `<span class="tag tag-red">${w}</span>`).join('')}</div>
                </div>
              ` : ''}
              ${player.scouting.style_tags && player.scouting.style_tags.length > 0 ? `
                <div style="margin-bottom: 12px;">
                  <div class="field-label">Style Tags</div>
                  <div>${player.scouting.style_tags.map(t => `<span class="tag tag-blue">${t}</span>`).join('')}</div>
                </div>
              ` : ''}
              ${player.scouting.risk_notes && player.scouting.risk_notes.length > 0 ? `
                <div style="margin-bottom: 12px;">
                  <div class="field-label">Risk Notes</div>
                  <div>${player.scouting.risk_notes.map(n => `<span class="tag tag-orange">${n}</span>`).join('')}</div>
                </div>
              ` : ''}
              ${player.scouting.role_projection ? `
                <div>
                  <div class="field-label">Role Projection</div>
                  <div class="field-value">${player.scouting.role_projection}</div>
                </div>
              ` : ''}
            </div>
          ` : ''}

          ${report.report_summary && report.report_summary.length > 0 ? `
            <div class="section">
              <h2 style="margin-top: 0;">Report Summary</h2>
              <ul style="margin: 0; padding-left: 0; list-style: none;">
                ${report.report_summary.map(point => `<li style="margin-bottom: 8px;"><span class="bullet">•</span>${point}</li>`).join('')}
              </ul>
            </div>
          ` : ''}

          ${report.report_text ? `
            <div class="section">
              <h2 style="margin-top: 0;">Full Report</h2>
              <div class="report-text">${report.report_text}</div>
            </div>
          ` : ''}

          ${report.coverage ? `
            <div class="section">
              <h2 style="margin-top: 0;">Coverage Analysis</h2>
              <div class="grid">
                ${report.coverage.found && report.coverage.found.length > 0 ? `
                  <div>
                    <div class="field-label">Fields Found (${report.coverage.found.length})</div>
                    <div>${report.coverage.found.map(f => `<span class="tag tag-green">✓ ${f}</span>`).join('')}</div>
                  </div>
                ` : ''}
                ${report.coverage.missing && report.coverage.missing.length > 0 ? `
                  <div>
                    <div class="field-label">Missing Fields (${report.coverage.missing.length})</div>
                    <div>${report.coverage.missing.map(f => `<span class="tag tag-red">✗ ${f}</span>`).join('')}</div>
                  </div>
                ` : ''}
              </div>
            </div>
          ` : ''}

          <div class="section" style="margin-top: 24px;">
            <h2 style="margin-top: 0;">Metadata</h2>
            <div class="grid">
              <div><div class="field-label">Created At</div><div class="field-value">${new Date(report.created_at).toLocaleString()}</div></div>
              ${report.request_text ? `<div><div class="field-label">Original Request</div><div class="field-value" style="font-style: italic;">"${report.request_text}"</div></div>` : ''}
            </div>
          </div>

          <div style="margin-top: 40px; text-align: center; color: #9ca3af; font-size: 12px;">
            Generated on ${new Date().toLocaleString()}
          </div>
        </body>
        </html>
      `

      // Open print dialog which allows saving as PDF
      const printWindow = window.open('', '_blank')
      if (printWindow) {
        printWindow.document.write(printContent)
        printWindow.document.close()
        printWindow.onload = () => {
          printWindow.print()
        }
      } else {
        toast.error('Could not open print window. Please allow popups.')
      }
    }

    return (
      <div className="min-h-screen bg-background">
        {/* Detail Header */}
        <div className="border-b bg-card sticky top-0 z-10">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center gap-4">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onClose}
                  className="gap-2"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Back to Reports
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadPDF}
                  className="gap-2"
                >
                  <Download className="w-4 h-4" />
                  Download PDF
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setReportToDelete(report)
                    setDeleteDialogOpen(true)
                  }}
                  className="gap-2 text-destructive hover:text-destructive"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onClose}
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Detail Content */}
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
          {/* Player Header */}
          <div className="flex items-start gap-4">
            <div
              className={`w-16 h-16 rounded-full flex items-center justify-center text-white text-2xl font-medium ${getSportColor(player.sport)}`}
            >
              {getSportIcon(player.sport)}
            </div>
            <div className="flex-1">
              <h1 className="text-2xl font-bold">{player.display_name}</h1>
              <div className="flex items-center gap-3 mt-1 text-muted-foreground">
                <span>{formatSportName(player.sport)}</span>
                {player.positions && player.positions.length > 0 && (
                  <>
                    <span>•</span>
                    <span>{player.positions.join(', ')}</span>
                  </>
                )}
                {player.teams && player.teams.length > 0 && (
                  <>
                    <span>•</span>
                    <span>{player.teams.join(', ')}</span>
                  </>
                )}
              </div>
              <div className="flex items-center gap-3 mt-2">
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${getConfidenceColor(report.coverage?.confidence || 'low')}`}
                >
                  {report.coverage?.confidence || 'unknown'} confidence
                </span>
                <span className="text-sm text-muted-foreground">
                  Created {new Date(report.created_at).toLocaleDateString()} at {new Date(report.created_at).toLocaleTimeString()}
                </span>
              </div>
            </div>
          </div>

          {/* Player Information */}
          <div className="border rounded-lg bg-card p-4 space-y-4">
            <h2 className="font-semibold text-lg">Player Information</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Display Name</div>
                <div className="text-sm font-medium mt-1">{player.display_name}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Sport</div>
                <div className="text-sm font-medium mt-1">{formatSportName(player.sport)}</div>
              </div>
              {player.league && (
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">League</div>
                  <div className="text-sm font-medium mt-1">{player.league}</div>
                </div>
              )}
              {player.positions && player.positions.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Positions</div>
                  <div className="text-sm font-medium mt-1">{player.positions.join(', ')}</div>
                </div>
              )}
              {player.teams && player.teams.length > 0 && (
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Teams</div>
                  <div className="text-sm font-medium mt-1">{player.teams.join(', ')}</div>
                </div>
              )}
              {player.aliases && player.aliases.length > 0 && (
                <div className="col-span-2">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Aliases</div>
                  <div className="text-sm font-medium mt-1">{player.aliases.join(', ')}</div>
                </div>
              )}
            </div>

            {/* Physical Attributes */}
            {player.physical && (player.physical.height_cm || player.physical.weight_kg) && (
              <div className="pt-4 border-t">
                <h3 className="text-sm font-semibold text-muted-foreground mb-3">Physical Attributes</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {player.physical.height_cm && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wide">Height</div>
                      <div className="text-sm font-medium mt-1">{player.physical.height_cm} cm</div>
                    </div>
                  )}
                  {player.physical.weight_kg && (
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wide">Weight</div>
                      <div className="text-sm font-medium mt-1">{player.physical.weight_kg} kg</div>
                    </div>
                  )}
                  {player.physical.measurements && Object.entries(player.physical.measurements).map(([key, value]) => (
                    <div key={key}>
                      <div className="text-xs text-muted-foreground uppercase tracking-wide">{key.replace(/_/g, ' ')}</div>
                      <div className="text-sm font-medium mt-1">{String(value)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Scouting Assessment */}
          {player.scouting && (
            <div className="border rounded-lg bg-card p-4 space-y-4">
              <h2 className="font-semibold text-lg">Scouting Assessment</h2>
              
              {player.scouting.strengths && player.scouting.strengths.length > 0 && (
                <div>
                  <div className="text-sm font-medium text-muted-foreground mb-2">Strengths</div>
                  <div className="flex flex-wrap gap-2">
                    {player.scouting.strengths.map((strength, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-3 py-1.5 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded-md text-sm"
                      >
                        {strength}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {player.scouting.weaknesses && player.scouting.weaknesses.length > 0 && (
                <div>
                  <div className="text-sm font-medium text-muted-foreground mb-2">Weaknesses</div>
                  <div className="flex flex-wrap gap-2">
                    {player.scouting.weaknesses.map((weakness, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-3 py-1.5 bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 rounded-md text-sm"
                      >
                        {weakness}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {player.scouting.style_tags && player.scouting.style_tags.length > 0 && (
                <div>
                  <div className="text-sm font-medium text-muted-foreground mb-2">Style Tags</div>
                  <div className="flex flex-wrap gap-2">
                    {player.scouting.style_tags.map((tag, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-3 py-1.5 bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 rounded-md text-sm"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {player.scouting.risk_notes && player.scouting.risk_notes.length > 0 && (
                <div>
                  <div className="text-sm font-medium text-muted-foreground mb-2">Risk Notes</div>
                  <div className="flex flex-wrap gap-2">
                    {player.scouting.risk_notes.map((note, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-3 py-1.5 bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200 rounded-md text-sm"
                      >
                        {note}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {player.scouting.role_projection && (
                <div>
                  <div className="text-sm font-medium text-muted-foreground mb-2">Role Projection</div>
                  <div className="text-sm bg-muted/50 rounded-md p-3">
                    {player.scouting.role_projection}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Report Summary */}
          {report.report_summary && report.report_summary.length > 0 && (
            <div className="border rounded-lg bg-card p-4 space-y-4">
              <h2 className="font-semibold text-lg">Report Summary</h2>
              <ul className="space-y-2">
                {report.report_summary.map((point, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <span className="text-primary font-bold">•</span>
                    <span className="text-sm">{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Full Report Text */}
          {report.report_text && (
            <div className="border rounded-lg bg-card p-4 space-y-4">
              <h2 className="font-semibold text-lg">Full Report</h2>
              <div className="text-sm whitespace-pre-wrap bg-muted/30 rounded-md p-4 leading-relaxed">
                {report.report_text}
              </div>
            </div>
          )}

          {/* Coverage Analysis */}
          {report.coverage && (
            <div className="border rounded-lg bg-card p-4 space-y-4">
              <h2 className="font-semibold text-lg">Coverage Analysis</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {report.coverage.found && report.coverage.found.length > 0 && (
                  <div>
                    <div className="text-sm font-medium text-muted-foreground mb-2">
                      Fields Found ({report.coverage.found.length})
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {report.coverage.found.map((field, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded text-xs"
                        >
                          ✓ {field}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                
                {report.coverage.missing && report.coverage.missing.length > 0 && (
                  <div>
                    <div className="text-sm font-medium text-muted-foreground mb-2">
                      Missing Fields ({report.coverage.missing.length})
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {report.coverage.missing.map((field, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 rounded text-xs"
                        >
                          ✗ {field}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="border rounded-lg bg-card p-4 space-y-2 text-sm text-muted-foreground">
            <h2 className="font-semibold text-lg text-foreground mb-3">Metadata</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-xs uppercase tracking-wide">Created At</span>
                <div className="text-xs mt-1">{new Date(report.created_at).toLocaleString()}</div>
              </div>
            </div>
            {report.request_text && (
              <div className="pt-2">
                <span className="text-xs uppercase tracking-wide">Original Request</span>
                <div className="text-xs mt-1 italic">"{report.request_text}"</div>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // If a report is selected, show detail view
  if (selectedReport) {
    return <ReportDetailView report={selectedReport} onClose={() => setSelectedReport(null)} />
  }

  // List View
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <h1 className="text-2xl font-bold">Scout Reports</h1>
              <p className="text-sm text-muted-foreground">
                {filteredReports.length} report{filteredReports.length !== 1 ? 's' : ''}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {reports.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDeleteAllDialogOpen(true)}
                  className="gap-2 text-destructive hover:text-destructive"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete All
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate('/chat')}
              >
                New Chat
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {loading ? (
          <div className="flex justify-center items-center py-12">
            <div className="text-center text-muted-foreground">
              Loading scout reports...
            </div>
          </div>
        ) : error ? (
          <div className="flex justify-center items-center py-12">
            <div className="text-destructive text-center">
              {error}
            </div>
          </div>
        ) : reports.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-16 h-16 mb-4">
              <Filter className="w-16 h-16 text-muted-foreground" />
            </div>
            <h2 className="text-xl font-semibold mb-2">No Scout Reports Yet</h2>
            <p className="text-muted-foreground mb-6">
              Scout reports will appear here after you approve player proposals in a chat.
            </p>
            <Button onClick={() => navigate('/chat')}>
              Go to Chat
            </Button>
          </div>
        ) : (
          <>
            {/* Filters */}
            <div className="mb-6 flex flex-col sm:flex-row gap-4">
              <div className="flex-1">
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
                  <Input
                    type="text"
                    placeholder="Search reports..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                  />
                </div>
              </div>
              
              <div className="flex gap-2">
                <Button
                  variant={sportFilter === 'all' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleFilter('all')}
                >
                  All
                </Button>
                <Button
                  variant={sportFilter === 'nba' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleFilter('nba')}
                >
                  NBA
                </Button>
                <Button
                  variant={sportFilter === 'football' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleFilter('football')}
                >
                  Football
                </Button>
              </div>
            </div>

            {/* Reports List */}
            <div className="space-y-4">
              {filteredReports.map((report) => (
                <div
                  key={report.id}
                  className="border rounded-lg bg-card p-4 hover:border-primary/50 transition-colors cursor-pointer"
                  onClick={() => setSelectedReport(report)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-medium ${getSportColor(report.player.sport)}`}
                      >
                        {getSportIcon(report.player.sport)}
                      </div>
                      <div>
                        <h3 className="font-semibold text-lg">{report.player.display_name}</h3>
                        <p className="text-sm text-muted-foreground">
                          {report.player.positions?.join(', ') || '—'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {new Date(report.created_at).toLocaleDateString()}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          setReportToDelete(report)
                          setDeleteDialogOpen(true)
                        }}
                        title="Delete report"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                  
                  {/* Coverage Badge */}
                  <div className="mb-3 flex items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${getConfidenceColor(report.coverage?.confidence || 'low')}`}
                    >
                      <Filter className="w-3 h-3" />
                      {report.coverage?.confidence || 'unknown'} confidence
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {report.coverage?.found?.length || 0} fields found
                    </span>
                  </div>

                  {/* Report Summary */}
                  {report.report_summary && report.report_summary.length > 0 && (
                    <div className="border-t pt-3">
                      <h4 className="text-sm font-semibold text-muted-foreground mb-2">Key Points</h4>
                      <ul className="space-y-1">
                        {report.report_summary.slice(0, 3).map((bullet, idx) => (
                          <li key={idx} className="text-sm flex items-start gap-2">
                            <span className="text-primary">•</span>
                            <span className="text-foreground">{bullet}</span>
                          </li>
                        ))}
                        {report.report_summary.length > 3 && (
                          <li className="text-sm text-muted-foreground">
                            +{report.report_summary.length - 3} more points...
                          </li>
                        )}
                      </ul>
                    </div>
                  )}

                  {/* Click hint */}
                  <div className="mt-3 pt-3 border-t text-xs text-muted-foreground">
                    Click to view full report details
                  </div>
                </div>
              ))}
            </div>

            {filteredReports.length === 0 && reports.length > 0 && (
              <div className="text-center py-12 text-muted-foreground">
                No reports match your filters.
              </div>
            )}
          </>
        )}
      </div>
      
      {/* Delete Single Report Dialog */}
      {deleteDialogOpen && reportToDelete && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-card border rounded-lg shadow-lg max-w-md w-full p-6">
            <h2 className="text-lg font-semibold mb-2">Delete Report</h2>
            <p className="text-muted-foreground mb-4">
              Are you sure you want to delete the scout report for <strong>{reportToDelete.player.display_name}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  setDeleteDialogOpen(false)
                  setReportToDelete(null)
                }}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={() => handleDeleteReport(reportToDelete)}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        </div>
      )}
      
      {/* Delete All Reports Dialog */}
      {deleteAllDialogOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-card border rounded-lg shadow-lg max-w-md w-full p-6">
            <h2 className="text-lg font-semibold mb-2">Delete All Reports</h2>
            <p className="text-muted-foreground mb-4">
              Are you sure you want to delete all <strong>{reports.length}</strong> scout report{reports.length !== 1 ? 's' : ''}? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => setDeleteAllDialogOpen(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleDeleteAllReports}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete All'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
