import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useChatStore } from '@/state/useChatStore'
import { documentAPI } from '@/lib/api'
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

export default function DashboardPage() {
  const { createSession } = useChatStore()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const response = await documentAPI.getDocuments()
      // Backend returns { results: [...], count, page, ... }
      setDocuments(response.data.results || [])
    } catch (error: unknown) {
      // Documents endpoint might not be implemented yet - silently fail
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

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Dashboard</h1>
      
      <div className="grid gap-6 md:grid-cols-2 mb-10">
        <div className="p-6 border rounded-lg hover:bg-muted/50 transition-colors">
          <h2 className="text-xl font-semibold mb-2">Start New Chat</h2>
          <p className="text-muted-foreground mb-4 text-sm">
            Begin a new conversation with the agent
          </p>
          <Button onClick={handleNewChat} className="rounded-lg">New Chat</Button>
        </div>
        <div className="p-6 border rounded-lg hover:bg-muted/50 transition-colors">
          <h2 className="text-xl font-semibold mb-2">Documents</h2>
          <p className="text-muted-foreground mb-4 text-sm">
            Upload and manage your documents
          </p>
          <Link to="/documents">
            <Button variant="outline" className="rounded-lg">View Documents</Button>
          </Link>
        </div>
      </div>

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
        <div>
          {/* Latest Documents */}
          <div>
            <h2 className="text-xl font-semibold mb-4">Latest Documents</h2>
            {sortedDocuments.length === 0 ? (
              <div className="border rounded-lg p-8 text-center">
                <p className="text-muted-foreground">No documents yet</p>
                <Link to="/documents">
                  <Button variant="outline" className="mt-4 rounded-lg">Upload Your First Document</Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {sortedDocuments.slice(0, 5).map((doc: Document) => (
                  <div
                    key={doc.id}
                    className="p-4 border rounded-lg hover:bg-muted/50 transition-colors cursor-pointer"
                  >
                    <div className="flex justify-between items-start">
                      <div className="flex items-start gap-3">
                        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                          <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                        </div>
                        <div>
                          <h3 className="font-medium text-sm">{doc.title}</h3>
                          <p className="text-xs text-muted-foreground mt-1">
                            {new Date(doc.updated_at).toLocaleDateString()}
                            {doc.status === 'READY' && doc.chunks_count > 0 && ` • ${doc.chunks_count} chunks`}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
