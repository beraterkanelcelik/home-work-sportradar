import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useChatStore } from '@/state/useChatStore'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

export default function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const {
    sessions,
    currentSession,
    messages,
    loading,
    error,
    loadSessions,
    createSession,
    loadSession,
    sendMessage,
    deleteSession,
    clearCurrentSession,
  } = useChatStore()

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  useEffect(() => {
    if (sessionId) {
      loadSession(Number(sessionId))
    } else {
      clearCurrentSession()
    }
  }, [sessionId, loadSession, clearCurrentSession])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleNewChat = async () => {
    const newSession = await createSession()
    if (newSession) {
      navigate(`/chat/${newSession.id}`)
    }
  }

  const handleSelectSession = (id: number) => {
    navigate(`/chat/${id}`)
  }

  const handleSend = async () => {
    if (!input.trim() || sending || !currentSession) return

    const content = input.trim()
    setInput('')
    setSending(true)

    try {
      await sendMessage(currentSession.id, content)
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Failed to send message')
    } finally {
      setSending(false)
    }
  }

  const handleDeleteSession = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm('Are you sure you want to delete this chat session?')) {
      await deleteSession(id)
      if (currentSession?.id === id) {
        navigate('/chat')
      }
    }
  }

  return (
    <div className="flex h-[calc(100vh-200px)]">
      {/* Sidebar */}
      <div className="w-64 border-r flex flex-col">
        <div className="p-4 border-b">
          <Button onClick={handleNewChat} className="w-full">
            New Chat
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading && sessions.length === 0 ? (
            <div className="p-4 text-center text-muted-foreground">Loading...</div>
          ) : sessions.length === 0 ? (
            <div className="p-4 text-center text-muted-foreground text-sm">
              No chat sessions yet. Create a new chat to get started.
            </div>
          ) : (
            <div className="divide-y">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  onClick={() => handleSelectSession(session.id)}
                  className={`p-3 cursor-pointer hover:bg-muted transition-colors ${
                    currentSession?.id === session.id ? 'bg-muted' : ''
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">
                        {session.title || 'Untitled Chat'}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {new Date(session.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                    <button
                      onClick={(e) => handleDeleteSession(session.id, e)}
                      className="ml-2 text-muted-foreground hover:text-destructive"
                      title="Delete session"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Chat Window */}
      <div className="flex-1 flex flex-col">
        {!currentSession ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <h2 className="text-xl font-semibold mb-2">No chat selected</h2>
              <p className="text-muted-foreground mb-4">
                Select a chat from the sidebar or create a new one
              </p>
              <Button onClick={handleNewChat}>New Chat</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Chat Header */}
            <div className="border-b p-4">
              <h2 className="font-semibold">{currentSession.title || 'Untitled Chat'}</h2>
              <p className="text-sm text-muted-foreground">
                Created {new Date(currentSession.created_at).toLocaleDateString()}
              </p>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 ? (
                <div className="text-center text-muted-foreground py-8">
                  Start a conversation by typing a message below
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${
                      msg.role === 'user' ? 'justify-end' : 'justify-start'
                    }`}
                  >
                    <div
                      className={`max-w-[70%] rounded-lg p-3 ${
                        msg.role === 'user'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted'
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t p-4">
              {error && (
                <div className="mb-2 p-2 bg-destructive/10 text-destructive text-sm rounded">
                  {error}
                </div>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  handleSend()
                }}
                className="flex gap-2"
              >
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your message..."
                  className="flex-1 px-4 py-2 border rounded-md"
                  disabled={sending}
                />
                <Button type="submit" disabled={sending || !input.trim()}>
                  {sending ? 'Sending...' : 'Send'}
                </Button>
              </form>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
