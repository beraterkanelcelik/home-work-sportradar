/**
 * StatsDialog Component
 * 
 * Displays comprehensive statistics for a chat session including:
 * - Message counts and token usage
 * - Cost breakdown
 * - Agent and tool usage
 * - Activity timeline with collapsible chains
 * 
 * Features:
 * - Overview metrics (total messages, tokens, etc.)
 * - Detailed token and cost breakdowns
 * - Agent and tool usage statistics
 * - Interactive activity timeline grouped by trace_id
 * - Collapsible activity chains and individual activities
 * - Nested activity visualization with indentation
 * 
 * Location: frontend/src/components/chat/StatsDialog.tsx
 */

import React, { useState } from 'react'
import type { Message } from '@/state/useChatStore'

interface StatsDialogProps {
  /** Whether the dialog is open */
  open: boolean
  /** Callback to close the dialog */
  onClose: () => void
  /** Statistics data from the API */
  stats: any | null
  /** Whether statistics are currently loading */
  loading: boolean
  /** Messages array (used to match user messages with activity chains) */
  messages: Message[]
  /** Array of expanded chain trace IDs */
  expandedChains: string[]
  /** Array of expanded activity keys */
  expandedActivities: string[]
  /** Callback to toggle chain expansion */
  onToggleChain: (traceId: string) => void
  /** Callback to toggle activity expansion */
  onToggleActivity: (activityKey: string) => void
}

/**
 * StatsDialog - Modal dialog displaying chat session statistics
 * 
 * This component shows:
 * 1. Overview metrics (messages, tokens)
 * 2. Token breakdown (input, output, cached)
 * 3. Cost breakdown (if available)
 * 4. Agent and tool usage
 * 5. Session information
 * 6. Activity timeline with collapsible chains
 * 
 * The activity timeline groups activities by trace_id (message chains)
 * and allows expanding/collapsing both chains and individual activities.
 */
export default function StatsDialog({
  open,
  onClose,
  stats,
  loading,
  messages,
  expandedChains,
  expandedActivities,
  onToggleChain,
  onToggleActivity,
}: StatsDialogProps) {
  // Track expanded input/output sections within activities
  // Format: "activityKey-input" or "activityKey-output"
  const [expandedFields, setExpandedFields] = useState<Set<string>>(new Set())

  const toggleField = (fieldKey: string) => {
    setExpandedFields(prev => {
      const next = new Set(prev)
      if (next.has(fieldKey)) {
        next.delete(fieldKey)
      } else {
        next.add(fieldKey)
      }
      return next
    })
  }

  if (!open) return null

  return (
    <div 
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" 
      onClick={onClose}
    >
      <div 
        className="bg-background border rounded-lg p-6 max-w-4xl w-full mx-4 shadow-lg max-h-[90vh] overflow-y-auto" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Chat Statistics</h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        {/* Content */}
        {loading ? (
          <div className="text-center text-muted-foreground py-8">Loading statistics...</div>
        ) : stats ? (
          <div className="space-y-6">
            {/* Overview Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="border rounded-lg p-4">
                <div className="text-sm text-muted-foreground">Total Messages</div>
                <div className="text-2xl font-bold mt-1">{stats.total_messages}</div>
              </div>
              <div className="border rounded-lg p-4">
                <div className="text-sm text-muted-foreground">User Messages</div>
                <div className="text-2xl font-bold mt-1">{stats.user_messages}</div>
              </div>
              <div className="border rounded-lg p-4">
                <div className="text-sm text-muted-foreground">Assistant Messages</div>
                <div className="text-2xl font-bold mt-1">{stats.assistant_messages}</div>
              </div>
              <div className="border rounded-lg p-4">
                <div className="text-sm text-muted-foreground">Total Tokens</div>
                <div className="text-2xl font-bold mt-1">{stats.total_tokens?.toLocaleString() || 0}</div>
              </div>
            </div>

            {/* Token Breakdown */}
            <div className="border rounded-lg p-4">
              <h3 className="font-semibold mb-4">Token Usage</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <div className="text-sm text-muted-foreground">Input Tokens</div>
                  <div className="text-xl font-bold mt-1">{(stats.input_tokens || 0).toLocaleString()}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Output Tokens</div>
                  <div className="text-xl font-bold mt-1">{(stats.output_tokens || 0).toLocaleString()}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Cached Tokens</div>
                  <div className="text-xl font-bold mt-1">{(stats.cached_tokens || 0).toLocaleString()}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Total Tokens</div>
                  <div className="text-xl font-bold mt-1">{stats.total_tokens?.toLocaleString() || 0}</div>
                </div>
              </div>
            </div>

            {/* Cost Breakdown */}
            {stats.cost && (
              <div className="border rounded-lg p-4">
                <h3 className="font-semibold mb-4">Cost Breakdown</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-sm text-muted-foreground">Input Cost</div>
                    <div className="text-xl font-bold mt-1">${(stats.cost.input || 0).toFixed(6)}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Output Cost</div>
                    <div className="text-xl font-bold mt-1">${(stats.cost.output || 0).toFixed(6)}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Cached Cost</div>
                    <div className="text-xl font-bold mt-1">${(stats.cost.cached || 0).toFixed(6)}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Total Cost</div>
                    <div className="text-xl font-bold mt-1 text-primary">${(stats.cost.total || 0).toFixed(6)}</div>
                  </div>
                </div>
              </div>
            )}

            {/* Agent Usage */}
            {stats.agent_usage && Object.keys(stats.agent_usage).length > 0 && (
              <div className="border rounded-lg p-4">
                <h3 className="font-semibold mb-4">Agent Usage</h3>
                <div className="space-y-2">
                  {Object.entries(stats.agent_usage).map(([agent, count]) => (
                    <div key={agent} className="flex items-center justify-between">
                      <span className="capitalize">{agent}</span>
                      <span className="font-medium">{count as number} messages</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tool Usage */}
            {stats.tool_usage && Object.keys(stats.tool_usage).length > 0 && (
              <div className="border rounded-lg p-4">
                <h3 className="font-semibold mb-4">Tool Usage</h3>
                <div className="space-y-2">
                  {Object.entries(stats.tool_usage).map(([tool, count]) => (
                    <div key={tool} className="flex items-center justify-between">
                      <span className="font-mono text-sm">{tool}</span>
                      <span className="font-medium">{count as number} calls</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Session Info */}
            <div className="border rounded-lg p-4">
              <h3 className="font-semibold mb-4">Session Information</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Model Used:</span>
                  <span>{stats.model_used || 'Not specified'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Created:</span>
                  <span>{new Date(stats.created_at).toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last Updated:</span>
                  <span>{new Date(stats.updated_at).toLocaleString()}</span>
                </div>
              </div>
            </div>

            {/* Activity Timeline */}
            {stats.activity_timeline && stats.activity_timeline.length > 0 && (
              <div className="border rounded-lg p-4">
                <h3 className="font-semibold mb-4">Activity Timeline</h3>
                {(() => {
                  // Group activities by trace_id (message chains)
                  const chainsMap = new Map<string, any>()
                  
                  stats.activity_timeline.forEach((activity: any, index: number) => {
                    const traceId = activity.trace_id || `no-trace-${index}`
                    
                    if (!chainsMap.has(traceId)) {
                      chainsMap.set(traceId, {
                        trace_id: traceId,
                        activities: [],
                        total_tokens: 0,
                        total_cost: 0,
                        first_timestamp: activity.timestamp,
                        agents: []
                      })
                    }
                    
                    const chain = chainsMap.get(traceId)!
                    chain.activities.push(activity)
                    
                    if (activity.tokens) {
                      chain.total_tokens += activity.tokens.total || 0
                    }
                    if (activity.cost) {
                      chain.total_cost += activity.cost || 0
                    }
                    if (activity.agent && !chain.agents.includes(activity.agent)) {
                      chain.agents.push(activity.agent)
                    }
                    if (activity.timestamp && (!chain.first_timestamp || activity.timestamp < chain.first_timestamp)) {
                      chain.first_timestamp = activity.timestamp
                    }
                  })
                  
                  const chains = Array.from(chainsMap.values()).sort((a, b) => {
                    if (!a.first_timestamp || !b.first_timestamp) return 0
                    return a.first_timestamp.localeCompare(b.first_timestamp)
                  })
                  
                  return (
                    <div className="space-y-4">
                      {chains.map((chain) => {
                        const isChainExpanded = expandedChains.includes(chain.trace_id)
                        
                        // Find the user message for this chain
                        // Look for the first activity that has a user message or input_preview
                        const userMessage = chain.activities.find((activity: any) => 
                          activity.category === 'llm' && activity.input_preview
                        )?.input_preview || 
                        chain.activities.find((activity: any) => 
                          activity.message
                        )?.message ||
                        // Try to find matching user message from messages array by timestamp
                        (() => {
                          if (!chain.first_timestamp) return null
                          const chainTime = new Date(chain.first_timestamp).getTime()
                          const userMsg = messages.find((msg: Message) => {
                            if (msg.role !== 'user') return false
                            const msgTime = new Date(msg.created_at).getTime()
                            // Match if within 5 seconds
                            return Math.abs(msgTime - chainTime) < 5000
                          })
                          return userMsg?.content || null
                        })() ||
                        'No message preview available'
                        
                        // Truncate long messages
                        const displayMessage = typeof userMessage === 'string' 
                          ? (userMessage.length > 100 ? userMessage.substring(0, 100) + '...' : userMessage)
                          : 'No message preview available'
                        
                        return (
                          <div key={chain.trace_id} className="border rounded-lg p-3 bg-muted/20">
                            {/* Chain Header - Collapsible */}
                            <div 
                              className="flex items-start justify-between cursor-pointer hover:bg-muted/50 rounded p-2 -m-2"
                              onClick={() => onToggleChain(chain.trace_id)}
                            >
                              <div className="flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <svg
                                    className={`w-4 h-4 text-muted-foreground transition-transform ${isChainExpanded ? 'rotate-90' : ''}`}
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                  >
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                  </svg>
                                  <span className="font-semibold text-sm text-muted-foreground">Message:</span>
                                  <span className="text-sm font-medium">{displayMessage}</span>
                                  {chain.agents.length > 0 && (
                                    <div className="flex gap-1">
                                      {chain.agents.map((agent: string) => (
                                        <span key={agent} className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
                                          {agent}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                  <span className="text-xs text-muted-foreground">
                                    {chain.activities.length} {chain.activities.length === 1 ? 'activity' : 'activities'}
                                  </span>
                                </div>
                                <div className="text-xs text-muted-foreground mt-1 ml-6">
                                  {displayMessage !== 'No message preview available' && displayMessage.length > 100 && (
                                    <span className="italic">(truncated)</span>
                                  )}
                                </div>
                                {chain.first_timestamp && (
                                  <div className="text-xs text-muted-foreground mt-1 ml-6">
                                    {new Date(chain.first_timestamp).toLocaleString()}
                                  </div>
                                )}
                              </div>
                              
                              {/* Chain Summary */}
                              <div className="text-right text-sm">
                                <div className="text-muted-foreground">
                                  {chain.total_tokens || 0} tokens
                                </div>
                                {(chain.total_cost || 0) > 0 && (
                                  <div className="text-muted-foreground">
                                    ${chain.total_cost.toFixed(6)}
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Chain Activities - Collapsible */}
                            {isChainExpanded && (
                              <div className="mt-3 space-y-3 pl-6 border-l-2 border-muted">
                                {chain.activities.map((activity: any, activityIndex: number) => {
                                  const activityKey = `${chain.trace_id}-${activity.id || String(activityIndex)}`
                                  const isExpanded = expandedActivities.includes(activityKey)
                                  const hasDetails = !!(activity.model || activity.tools?.length || activity.input_preview || activity.output_preview || activity.message)
                                  // Get indentation level (0 = root, 1 = child, 2 = grandchild, etc.)
                                  const level = activity.level || 0
                                  const indentPx = level * 20  // 20px per level
                                  
                                  return (
                                    <div key={activity.id || activityIndex} className="relative">
                                      {/* Indentation container */}
                                      <div style={{ marginLeft: `${indentPx}px`, position: 'relative' }}>
                                        {/* Vertical connecting lines for nested activities */}
                                        {level > 0 && (
                                          <>
                                            {/* Vertical line from parent */}
                                            <div 
                                              className="absolute top-0 bottom-0 w-0.5 bg-muted/50" 
                                              style={{ 
                                                left: `${-20}px`,
                                                height: '100%'
                                              }}
                                            ></div>
                                            {/* Horizontal connector line */}
                                            <div 
                                              className="absolute top-2 w-4 h-0.5 bg-muted/50" 
                                              style={{ 
                                                left: `${-20}px`
                                              }}
                                            ></div>
                                          </>
                                        )}
                                        
                                        {/* Timeline dot */}
                                        <div className="absolute -left-3 top-0 w-3 h-3 rounded-full bg-primary/70 border-2 border-background z-10"></div>
                                        
                                        <div className="space-y-2">
                                          {/* Activity Header - Clickable if has details */}
                                          <div 
                                            className={`flex items-start justify-between ${hasDetails ? 'cursor-pointer hover:bg-muted/50 rounded p-2 -m-2' : ''}`}
                                            onClick={() => {
                                              if (hasDetails) {
                                                onToggleActivity(activityKey)
                                              }
                                            }}
                                          >
                                            <div className="flex-1">
                                              <div className="flex items-center gap-2">
                                                {hasDetails && (
                                                  <svg
                                                    className={`w-4 h-4 text-muted-foreground transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                                    fill="none"
                                                    stroke="currentColor"
                                                    viewBox="0 0 24 24"
                                                  >
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                  </svg>
                                                )}
                                                <span className="font-medium text-sm">{activity.name}</span>
                                                {activity.agent && (
                                                  <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
                                                    {activity.agent}
                                                  </span>
                                                )}
                                                {activity.tool && (
                                                  <span className="text-xs px-2 py-0.5 rounded bg-secondary text-secondary-foreground">
                                                    {activity.tool}
                                                  </span>
                                                )}
                                                <span className="text-xs text-muted-foreground capitalize">
                                                  {activity.category?.replace('_', ' ') || 'other'}
                                                </span>
                                              </div>
                                              {activity.timestamp && (
                                                <div className="text-xs text-muted-foreground mt-1 ml-6">
                                                  {new Date(activity.timestamp).toLocaleString()}
                                                  {activity.latency_ms && (
                                                    <span className="ml-2">• {activity.latency_ms.toFixed(0)}ms</span>
                                                  )}
                                                </div>
                                              )}
                                            </div>
                                            
                                            {/* Tokens and Cost */}
                                            <div className="text-right text-sm">
                                              {activity.tokens && (
                                                <div className="text-muted-foreground">
                                                  {activity.tokens.total || 0} tokens
                                                </div>
                                              )}
                                              {activity.cost && (
                                                <div className="text-muted-foreground">
                                                  ${activity.cost.toFixed(6)}
                                                </div>
                                              )}
                                            </div>
                                          </div>

                                          {/* Collapsible Details */}
                                          {isExpanded && hasDetails && (
                                            <div className="mt-2 space-y-2 pl-6">
                                              {/* Model info */}
                                              {activity.model && (
                                                <div className="text-xs text-muted-foreground">
                                                  Model: {activity.model}
                                                </div>
                                              )}

                                              {/* Tool calls */}
                                              {activity.tools && activity.tools.length > 0 && (
                                                <div className="mt-2 space-y-1">
                                                  {activity.tools.map((tool: any, toolIndex: number) => {
                                                    const toolFieldKey = `${activityKey}-tool-${toolIndex}`
                                                    const isToolExpanded = expandedFields.has(toolFieldKey)
                                                    const toolInputStr = tool.input ? (typeof tool.input === 'string' ? tool.input : JSON.stringify(tool.input, null, 2)) : ''
                                                    const isLongToolInput = toolInputStr.length > 200

                                                    return (
                                                      <div key={toolIndex} className="text-sm bg-muted/50 p-2 rounded">
                                                        <div className="flex items-center justify-between">
                                                          <span className="font-mono text-xs">{tool.name}</span>
                                                          {isLongToolInput && (
                                                            <button
                                                              onClick={(e) => {
                                                                e.stopPropagation()
                                                                toggleField(toolFieldKey)
                                                              }}
                                                              className="text-xs text-primary hover:underline"
                                                            >
                                                              {isToolExpanded ? 'Collapse' : 'Expand'}
                                                            </button>
                                                          )}
                                                        </div>
                                                        {tool.input && (
                                                          <div className="text-xs text-muted-foreground mt-1 break-words whitespace-pre-wrap">
                                                            {isToolExpanded || !isLongToolInput
                                                              ? toolInputStr
                                                              : toolInputStr.substring(0, 200) + '...'}
                                                          </div>
                                                        )}
                                                      </div>
                                                    )
                                                  })}
                                                </div>
                                              )}

                                              {/* Input/Output previews - collapsible */}
                                              {(activity.input_preview || activity.output_preview) && (
                                                <div className="mt-2 space-y-2 text-sm">
                                                  {activity.input_preview && (() => {
                                                    const inputFieldKey = `${activityKey}-input`
                                                    const isInputExpanded = expandedFields.has(inputFieldKey)
                                                    const inputStr = typeof activity.input_preview === 'string'
                                                      ? activity.input_preview
                                                      : JSON.stringify(activity.input_preview, null, 2)
                                                    const isLongInput = inputStr.length > 300

                                                    return (
                                                      <div className="bg-muted/30 p-2 rounded">
                                                        <div className="flex items-center justify-between mb-1">
                                                          <div className="text-xs text-muted-foreground">Input:</div>
                                                          {isLongInput && (
                                                            <button
                                                              onClick={(e) => {
                                                                e.stopPropagation()
                                                                toggleField(inputFieldKey)
                                                              }}
                                                              className="text-xs text-primary hover:underline"
                                                            >
                                                              {isInputExpanded ? 'Collapse' : 'Expand'}
                                                            </button>
                                                          )}
                                                        </div>
                                                        <div className={`text-xs font-mono break-words whitespace-pre-wrap ${isLongInput && !isInputExpanded ? 'max-h-32 overflow-hidden relative' : ''}`}>
                                                          {inputStr}
                                                          {isLongInput && !isInputExpanded && (
                                                            <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-muted/30 to-transparent" />
                                                          )}
                                                        </div>
                                                      </div>
                                                    )
                                                  })()}
                                                  {activity.output_preview && (() => {
                                                    const outputFieldKey = `${activityKey}-output`
                                                    const isOutputExpanded = expandedFields.has(outputFieldKey)
                                                    const outputStr = typeof activity.output_preview === 'string'
                                                      ? activity.output_preview
                                                      : JSON.stringify(activity.output_preview, null, 2)
                                                    const isLongOutput = outputStr.length > 300

                                                    return (
                                                      <div className="bg-muted/30 p-2 rounded">
                                                        <div className="flex items-center justify-between mb-1">
                                                          <div className="text-xs text-muted-foreground">Output:</div>
                                                          {isLongOutput && (
                                                            <button
                                                              onClick={(e) => {
                                                                e.stopPropagation()
                                                                toggleField(outputFieldKey)
                                                              }}
                                                              className="text-xs text-primary hover:underline"
                                                            >
                                                              {isOutputExpanded ? 'Collapse' : 'Expand'}
                                                            </button>
                                                          )}
                                                        </div>
                                                        <div className={`text-xs font-mono break-words whitespace-pre-wrap ${isLongOutput && !isOutputExpanded ? 'max-h-32 overflow-hidden relative' : ''}`}>
                                                          {outputStr}
                                                          {isLongOutput && !isOutputExpanded && (
                                                            <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-muted/30 to-transparent" />
                                                          )}
                                                        </div>
                                                      </div>
                                                    )
                                                  })()}
                                                </div>
                                              )}

                                              {/* Event message */}
                                              {activity.message && (
                                                <div className="text-sm text-muted-foreground italic">
                                                  {activity.message}
                                                </div>
                                              )}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )
                })()}
              </div>
            )}
          </div>
        ) : (
          <div className="text-center text-muted-foreground py-8">
            No statistics available
          </div>
        )}
      </div>
    </div>
  )
}
