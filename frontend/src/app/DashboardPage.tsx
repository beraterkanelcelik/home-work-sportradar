import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useChatStore } from '@/state/useChatStore'
import { documentAPI, userAPI, agentAPI } from '@/lib/api'
import { toast } from 'sonner'
import { getErrorMessage } from '@/lib/utils'

interface Document {
  id: number
  title: string
  status: 'UPLOADED' | 'EXTRACTED' | 'INDEXING' | 'READY' | 'FAILED'
  chunks_count: number
  created_at: string
  updated_at: string
}

interface TokenStats {
  total_tokens: number
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  tokens_this_month: number
  tokens_last_30_days: number
  total_cost: number
  cost_this_month: number
  total_sessions: number
  sessions_this_month: number
}

interface ScoutReport {
  id: string
  player: {
    id: string
    display_name: string
    sport: string
    positions?: string[]
    teams?: string[]
  }
  coverage?: {
    confidence: 'low' | 'med' | 'high'
  }
  created_at: string
}

export default function DashboardPage() {
  const { createSession } = useChatStore()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState<Document[]>([])
  const [tokenStats, setTokenStats] = useState<TokenStats | null>(null)
  const [scoutReports, setScoutReports] = useState<ScoutReport[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [docsResponse, statsResponse, reportsResponse] = await Promise.allSettled([
        documentAPI.getDocuments(),
        userAPI.getUserStats(),
        agentAPI.listScoutReports(),
      ])

      if (docsResponse.status === 'fulfilled') {
        setDocuments(docsResponse.value.data.results || [])
      }
      if (statsResponse.status === 'fulfilled') {
        setTokenStats(statsResponse.value.data)
      }
      if (reportsResponse.status === 'fulfilled') {
        setScoutReports(reportsResponse.value.data.reports || [])
      }
    } catch (error: unknown) {
      // Silently fail - dashboard should still render
    } finally {
      setLoading(false)
    }
  }

  const handleNewChat = async () => {
    const session = await createSession()
    if (session) {
      navigate(`/chat/${session.id}`)
    }
  }

  // Sort documents by updated_at (most recent first)
  const sortedDocuments = [...documents].sort((a, b) => {
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })

  // Document status counts
  const docStatusCounts = documents.reduce((acc, doc) => {
    acc[doc.status] = (acc[doc.status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  // Sort scout reports by created_at (most recent first)
  const sortedReports = [...scoutReports].sort((a, b) => {
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })

  const formatNumber = (num: number) => {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
    return num.toLocaleString()
  }

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-2xl sm:text-3xl font-bold mb-6 sm:mb-8">Dashboard</h1>

      {loading ? (
        <div className="text-center py-12">
          <div className="inline-flex items-center gap-2 text-muted-foreground">
            <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>Loading...</span>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Token Usage Stats */}
          {tokenStats && (
            <div className="border rounded-lg p-4 sm:p-6">
              <h2 className="text-lg sm:text-xl font-semibold mb-4">Token Usage</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 bg-muted/30 rounded-lg">
                  <p className="text-sm text-muted-foreground">Total Tokens</p>
                  <p className="text-2xl font-bold">{formatNumber(tokenStats.total_tokens)}</p>
                </div>
                <div className="p-4 bg-muted/30 rounded-lg">
                  <p className="text-sm text-muted-foreground">This Month</p>
                  <p className="text-2xl font-bold">{formatNumber(tokenStats.tokens_this_month)}</p>
                </div>
                <div className="p-4 bg-muted/30 rounded-lg">
                  <p className="text-sm text-muted-foreground">Input / Output</p>
                  <p className="text-2xl font-bold">
                    {formatNumber(tokenStats.input_tokens)} / {formatNumber(tokenStats.output_tokens)}
                  </p>
                </div>
                <div className="p-4 bg-muted/30 rounded-lg">
                  <p className="text-sm text-muted-foreground">Total Sessions</p>
                  <p className="text-2xl font-bold">{tokenStats.total_sessions}</p>
                </div>
              </div>
              {tokenStats.total_cost > 0 && (
                <div className="mt-4 pt-4 border-t flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Total Cost</span>
                  <span className="text-xl font-bold">${tokenStats.total_cost.toFixed(4)}</span>
                </div>
              )}
            </div>
          )}

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 sm:p-6 border rounded-lg hover:bg-muted/50 transition-colors">
              <h2 className="text-lg sm:text-xl font-semibold mb-2">Start New Chat</h2>
              <p className="text-muted-foreground mb-4 text-sm">
                Begin a new conversation with the agent
              </p>
              <Button onClick={handleNewChat} className="rounded-lg">New Chat</Button>
            </div>
            <div className="p-4 sm:p-6 border rounded-lg hover:bg-muted/50 transition-colors">
              <h2 className="text-lg sm:text-xl font-semibold mb-2">Documents</h2>
              <p className="text-muted-foreground mb-4 text-sm">
                Upload and manage your documents
              </p>
              <Link to="/documents">
                <Button variant="outline" className="rounded-lg">View Documents</Button>
              </Link>
            </div>
          </div>

          {/* Scout Reports */}
          <div className="border rounded-lg p-4 sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg sm:text-xl font-semibold">Scout Reports</h2>
              <span className="text-sm text-muted-foreground">{scoutReports.length} reports</span>
            </div>
            {sortedReports.length === 0 ? (
              <div className="text-center py-8">
                <svg className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-muted-foreground">No scout reports yet</p>
                <p className="text-sm text-muted-foreground mt-1">Start a chat to generate player reports</p>
              </div>
            ) : (
              <div className="space-y-3">
                {sortedReports.slice(0, 5).map((report) => (
                  <div
                    key={report.id}
                    className="p-4 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-medium">{report.player.display_name}</h3>
                        <p className="text-sm text-muted-foreground">
                          {report.player.positions?.join(', ') || '—'} {report.player.teams?.length ? `• ${report.player.teams.join(', ')}` : ''}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className={`inline-block px-2 py-1 text-xs rounded-full ${
                          report.coverage?.confidence === 'high' ? 'bg-green-500/10 text-green-600' :
                          report.coverage?.confidence === 'med' ? 'bg-yellow-500/10 text-yellow-600' :
                          'bg-red-500/10 text-red-600'
                        }`}>
                          {report.coverage?.confidence || 'low'} confidence
                        </span>
                        <p className="text-xs text-muted-foreground mt-1">
                          {new Date(report.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Document Status */}
          <div className="border rounded-lg p-4 sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg sm:text-xl font-semibold">Document Status</h2>
              <Link to="/documents" className="text-sm text-primary hover:underline">
                View all
              </Link>
            </div>
            {documents.length === 0 ? (
              <div className="text-center py-8">
                <svg className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                <p className="text-muted-foreground">No documents uploaded</p>
                <Link to="/documents">
                  <Button variant="outline" className="mt-4 rounded-lg">Upload Document</Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Status summary */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="flex items-center gap-2 p-3 bg-green-500/10 rounded-lg">
                    <div className="w-2 h-2 rounded-full bg-green-500"></div>
                    <span className="text-sm">Ready: {docStatusCounts['READY'] || 0}</span>
                  </div>
                  <div className="flex items-center gap-2 p-3 bg-blue-500/10 rounded-lg">
                    <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></div>
                    <span className="text-sm">Indexing: {docStatusCounts['INDEXING'] || 0}</span>
                  </div>
                  <div className="flex items-center gap-2 p-3 bg-yellow-500/10 rounded-lg">
                    <div className="w-2 h-2 rounded-full bg-yellow-500"></div>
                    <span className="text-sm">Uploaded: {(docStatusCounts['UPLOADED'] || 0) + (docStatusCounts['EXTRACTED'] || 0)}</span>
                  </div>
                  <div className="flex items-center gap-2 p-3 bg-red-500/10 rounded-lg">
                    <div className="w-2 h-2 rounded-full bg-red-500"></div>
                    <span className="text-sm">Failed: {docStatusCounts['FAILED'] || 0}</span>
                  </div>
                </div>

                {/* Recent documents */}
                <div className="space-y-2">
                  {sortedDocuments.slice(0, 3).map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between p-3 bg-muted/30 rounded-lg"
                    >
                      <div className="flex items-center gap-3">
                        <svg className="w-5 h-5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <div>
                          <p className="text-sm font-medium">{doc.title}</p>
                          <p className="text-xs text-muted-foreground">
                            {doc.chunks_count > 0 && `${doc.chunks_count} chunks • `}
                            {new Date(doc.updated_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <span className={`px-2 py-1 text-xs rounded-full ${
                        doc.status === 'READY' ? 'bg-green-500/10 text-green-600' :
                        doc.status === 'INDEXING' ? 'bg-blue-500/10 text-blue-600' :
                        doc.status === 'FAILED' ? 'bg-red-500/10 text-red-600' :
                        'bg-yellow-500/10 text-yellow-600'
                      }`}>
                        {doc.status.toLowerCase()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
