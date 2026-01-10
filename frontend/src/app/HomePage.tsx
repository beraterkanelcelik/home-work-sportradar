import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/state/useAuthStore'
import { useChatStore } from '@/state/useChatStore'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { getErrorMessage } from '@/lib/utils'
import logoWithText from '@/assets/logowithtextblacktransparent.png'

export default function HomePage() {
  const { isAuthenticated } = useAuthStore()
  const { createSession } = useChatStore()
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!input.trim() || !isAuthenticated) return

    const message = input.trim()
    setInput('')
    setSending(true)
    try {
      const session = await createSession()
      if (session) {
        navigate(`/chat/${session.id}`, { 
          state: { initialMessage: message } 
        })
      } else {
        toast.error('Failed to create chat session')
        setSending(false)
      }
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to start chat'))
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center -mb-32">
        <img 
          src={logoWithText} 
          alt="Agent Playground" 
          className="h-96 w-auto object-contain"
        />
      </div>
      <p className="text-muted-foreground mb-6 text-center text-sm">
        Chat with AI agents powered by LangChain and LangGraph
      </p>
      
      {isAuthenticated ? (
        <div className="w-full max-w-3xl">
          <form onSubmit={handleSubmit} className="relative">
            <div className="relative flex items-end gap-2">
              <input
                type="text"
                value={input}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInput(e.target.value)}
                placeholder="Ask me anything..."
                className="flex-1 px-4 py-3 pr-20 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background transition-all"
                disabled={sending}
              />
              <button
                type="submit"
                disabled={sending || !input.trim()}
                className="absolute right-2 bottom-2 p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                aria-label="Send message"
              >
                {sending ? (
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                )}
              </button>
            </div>
          </form>
        </div>
      ) : (
        <div className="flex gap-3">
          <Link to="/login">
            <Button variant="outline" size="lg" className="rounded-lg">Login</Button>
          </Link>
          <Link to="/signup">
            <Button size="lg" className="rounded-lg">Sign Up</Button>
          </Link>
        </div>
      )}
    </div>
  )
}
