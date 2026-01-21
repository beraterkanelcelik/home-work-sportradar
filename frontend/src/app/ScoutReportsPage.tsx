/**
 * ScoutReportsPage Component
 *
 * Displays all saved scouting reports with filtering and search.
 */

import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/state/useAuthStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toast } from 'sonner'
import { agentAPI } from '@/lib/api'
import { getErrorMessage } from '@/lib/utils'
import { Search, Filter, User } from 'lucide-react'

interface ScoutingReport {
  id: string
  player: {
    id: string
    display_name: string
    sport: 'nba' | 'football' | 'unknown'
  }
  report_text: string
  report_summary: string[]
  coverage: {
    found: string[]
    missing: string[]
    confidence: 'low' | 'med' | 'high'
  }
  created_at: string
}

export default function ScoutReportsPage() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  
  const [reports, setReports] = useState<ScoutingReport[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [sportFilter, setSportFilter] = useState<'all' | 'nba' | 'football' | 'unknown'>('all')

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

  const handleSearch = () => {
    loadReports()
  }

  const handleFilter = (sport: 'nba' | 'football' | 'unknown' | 'all') => {
    setSportFilter(sport)
  }

  const filteredReports = reports.filter(report => {
    // Search filter
    const matchesSearch = searchTerm === '' || 
      report.player.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      report.report_summary.some((bullet: string) => 
        bullet.toLowerCase().includes(searchTerm.toLowerCase())
      ) ||
      report.report_text.toLowerCase().includes(searchTerm.toLowerCase())
    
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

  const handleViewReport = (report: ScoutingReport) => {
    navigate(`/chat/${report.player.id}`)
  }

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
                  onClick={() => handleViewReport(report)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-medium ${
                          report.player.sport === 'nba'
                            ? 'bg-blue-600'
                            : report.player.sport === 'football'
                            ? 'bg-green-600'
                            : 'bg-gray-600'
                        }`}
                      >
                        {report.player.sport === 'nba' ? '🏀' : report.player.sport === 'football' ? '⚽' : '❓'}
                      </div>
                      <div>
                        <h3 className="font-semibold text-lg">{report.player.display_name}</h3>
                        <p className="text-sm text-muted-foreground">
                          {report.player.positions?.join(', ') || '—'}
                        </p>
                      </div>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {new Date(report.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  
                  {/* Coverage Badge */}
                  <div className="mb-3">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${getConfidenceColor(report.coverage.confidence)}`}
                    >
                      <Filter className="w-3 h-3" />
                      {report.coverage.confidence} confidence
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {report.coverage.found.length} fields found
                    </span>
                  </div>

                  {/* Report Summary */}
                  {report.report_summary && report.report_summary.length > 0 && (
                    <div className="border-t pt-3">
                      <h4 className="text-sm font-semibold text-muted-foreground mb-2">Key Points</h4>
                      <ul className="space-y-1">
                        {report.report_summary.map((bullet, idx) => (
                          <li key={idx} className="text-sm flex items-start gap-2">
                            <span className="text-primary">•</span>
                            <span className="text-foreground">{bullet}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Coverage Details */}
                  <div className="border-t pt-3">
                    <h4 className="text-sm font-semibold text-muted-foreground mb-2">Coverage Analysis</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Fields Found:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
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
                      
                      {report.coverage.missing.length > 0 && (
                        <div>
                          <span className="text-muted-foreground">Missing:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
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
    </div>
  )
}
