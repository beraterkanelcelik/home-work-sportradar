import React, { useState, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/state/useAuthStore'
import { useChatStore } from '@/state/useChatStore'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { getErrorMessage } from '@/lib/utils'
import { documentAPI } from '@/lib/api'
import logoWithText from '@/assets/logowithtextblacktransparent.png'

export default function HomePage() {
  const { isAuthenticated } = useAuthStore()
  const { createSession } = useChatStore()
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [plusMenuOpen, setPlusMenuOpen] = useState(false)
  const [selectedOptions, setSelectedOptions] = useState<Array<{type: string, label: string, icon?: React.ReactNode, data?: any}>>([])
  const [inputFocused, setInputFocused] = useState(false)
  const [attachedFiles, setAttachedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    // Add files to attached files list
    setAttachedFiles((prev) => [...prev, ...files])

    // Add badge for files
    const fileNames = files.map(f => f.name).join(', ')
    const fileLabel = files.length === 1 ? fileNames : `${files.length} files`
    setSelectedOptions((prev) => [...prev, {
      type: 'files',
      label: fileLabel,
      icon: (
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
        </svg>
      ),
      data: files
    }])

    // Upload files
    for (const file of files) {
      try {
        await documentAPI.uploadDocument(file)
        toast.success(`File "${file.name}" uploaded successfully`)
      } catch (error: unknown) {
        toast.error(getErrorMessage(error, `Failed to upload ${file.name}`))
      }
    }

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleFileSelectionFromPlus = () => {
    setPlusMenuOpen(false)
    fileInputRef.current?.click()
  }

  const removeSelectedOption = (index: number) => {
    const option = selectedOptions[index]
    setSelectedOptions((prev) => prev.filter((_, i) => i !== index))
    
    // If it was a file option, also remove from attachedFiles
    if (option.type === 'files' && option.data) {
      setAttachedFiles((prev) => prev.filter((_, i) => !option.data.includes(i)))
    }
  }

  const handleSubmit = async (e?: React.FormEvent<HTMLFormElement>) => {
    if (e) {
      e.preventDefault()
    }
    if ((!input.trim() && attachedFiles.length === 0) || !isAuthenticated) return

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
        <div className="w-full max-w-2xl px-4">
          <div className="relative">
            {/* Selected Options Badges */}
            {selectedOptions.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3 justify-center">
                {selectedOptions.map((option, idx) => (
                  <div
                    key={idx}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary/10 text-primary text-sm"
                  >
                    {option.icon}
                    <span>{option.label}</span>
                    <button
                      onClick={() => removeSelectedOption(idx)}
                      className="ml-1 hover:bg-primary/20 rounded-full p-0.5 transition-colors"
                      aria-label="Remove"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
            
            {/* Input Bar */}
            <form onSubmit={handleSubmit} className="relative">
              <div className="relative flex flex-col bg-background border rounded-2xl shadow-sm">
                {/* Textarea Area */}
                <textarea
                  value={input}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                    setInput(e.target.value)
                    e.target.style.height = 'auto'
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
                  }}
                  onFocus={() => setInputFocused(true)}
                  onBlur={() => setInputFocused(false)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleSubmit()
                    }
                  }}
                  placeholder="Ask anything"
                  className="flex-1 min-h-[52px] max-h-[200px] px-4 pt-3 pb-2 border-0 bg-transparent resize-none focus:outline-none text-[15px] leading-relaxed"
                  disabled={sending}
                  rows={1}
                />

                {/* Bottom Controls */}
                <div className="flex items-center justify-between px-3 pb-2.5">
                  {/* Plus Button */}
                  <div className="relative flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => setPlusMenuOpen(!plusMenuOpen)}
                      className="w-8 h-8 rounded-full hover:bg-muted flex items-center justify-center transition-colors"
                      aria-label="More options"
                      disabled={sending}
                    >
                      <svg className="w-5 h-5 text-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                    </button>
                    
                    {/* Plus Menu Dropdown */}
                    {plusMenuOpen && (
                      <>
                        <div
                          className="fixed inset-0 z-10"
                          onClick={() => setPlusMenuOpen(false)}
                        />
                        <div className="absolute bottom-full left-0 mb-2 w-64 bg-background border rounded-lg shadow-lg p-2 z-20">
                          <button
                            type="button"
                            onClick={handleFileSelectionFromPlus}
                            className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-muted rounded-md text-sm text-left transition-colors"
                          >
                            <svg className="w-5 h-5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                            </svg>
                            <span>Add photos & files</span>
                          </button>
                          <button
                            type="button"
                            className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-muted rounded-md text-sm text-left transition-colors"
                            disabled
                          >
                            <svg className="w-5 h-5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                            </svg>
                            <span className="text-muted-foreground">... More</span>
                          </button>
                        </div>
                      </>
                    )}
                  </div>

                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    onChange={handleFileSelect}
                    className="hidden"
                    disabled={sending}
                  />

                  {/* Send Button */}
                  <button
                    type="submit"
                    onClick={handleSubmit}
                    disabled={sending || (!input.trim() && attachedFiles.length === 0)}
                    className="p-2 rounded-lg hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Send message"
                  >
                    <svg className="w-5 h-5 text-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                  </button>
                </div>
              </div>
            </form>
          </div>
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
