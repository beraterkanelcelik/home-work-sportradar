import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { ChevronDown, ChevronRight, Check, Loader2, Circle } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface PlanStep {
  action: string
  tool?: string  // For "tool" actions
  answer?: string  // For "answer" actions
  props?: Record<string, any>  // Optional - only present for "tool" actions with arguments
  agent: string
  query: string
  status?: 'pending' | 'in_progress' | 'completed' | 'error'  // Execution status
}

export interface PlanProposalData {
  type: string
  plan: PlanStep[]
  plan_index: number
  plan_total: number
  player_name?: string  // For scouting plans
  sport_guess?: string  // For scouting plans
}

interface PlanProposalProps {
  plan: PlanProposalData
  onApprove: () => void
  onReject: () => void
  isExecuting?: boolean
  currentStepIndex?: number  // Current step being executed (0-based)
}

export default function PlanProposal({ 
  plan, 
  onApprove, 
  onReject, 
  isExecuting = false,
  currentStepIndex = -1 
}: PlanProposalProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set())

  // Debug logging
  console.log('[PLAN_PROPOSAL] Rendering with plan:', {
    type: plan.type,
    steps_count: plan.plan?.length || 0,
    plan_total: plan.plan_total,
    isExecuting,
    currentStepIndex
  })

  const toggleStep = (index: number) => {
    setExpandedSteps(prev => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const formatAgentName = (agent: string): string => {
    if (!agent) return 'Unknown'
    return agent.charAt(0).toUpperCase() + agent.slice(1)
  }

  const getStepStatus = (step: PlanStep, index: number): 'pending' | 'in_progress' | 'completed' | 'error' => {
    // Use explicit status if provided
    if (step.status) return step.status
    
    // Infer status from currentStepIndex during execution
    if (!isExecuting) return 'pending'
    if (index < currentStepIndex) return 'completed'
    if (index === currentStepIndex) return 'in_progress'
    return 'pending'
  }

  const getStatusIcon = (status: 'pending' | 'in_progress' | 'completed' | 'error') => {
    switch (status) {
      case 'completed':
        return <Check className="w-4 h-4 text-green-500" />
      case 'in_progress':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
      case 'error':
        return <Circle className="w-4 h-4 text-destructive fill-destructive" />
      default:
        return <Circle className="w-4 h-4 text-muted-foreground" />
    }
  }

  const getStatusBgColor = (status: 'pending' | 'in_progress' | 'completed' | 'error') => {
    switch (status) {
      case 'completed':
        return 'bg-green-500/10 border-green-500/20'
      case 'in_progress':
        return 'bg-blue-500/10 border-blue-500/30'
      case 'error':
        return 'bg-destructive/10 border-destructive/20'
      default:
        return 'bg-background/50'
    }
  }

  // Check if step description is long (scouting plans have long descriptions)
  const isLongDescription = (step: PlanStep): boolean => {
    if (step.tool?.startsWith('Step ') && step.query) {
      return step.query.length > 60
    }
    return false
  }

  // Get short preview for collapsed state
  const getStepPreview = (step: PlanStep): string => {
    if (step.action === 'answer') {
      return step.answer || 'Provide Answer'
    }
    if (step.tool?.startsWith('Step ') && step.query) {
      if (step.query.length > 60) {
        return step.query.substring(0, 60) + '...'
      }
      return step.query
    }
    if (!step.tool) return 'Direct Answer'
    return step.tool.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
  }

  // Get full description
  const getStepFullDescription = (step: PlanStep): string => {
    if (step.tool?.startsWith('Step ') && step.query) {
      return step.query
    }
    return ''
  }

  const completedCount = plan.plan.filter((step, idx) => getStepStatus(step, idx) === 'completed').length
  const progressPercent = plan.plan_total > 0 ? (completedCount / plan.plan_total) * 100 : 0

  return (
    <div className="border rounded-lg bg-muted/30 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-foreground">
            {isExecuting ? 'Executing Plan' : 'Plan Proposal'}
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            {isExecuting 
              ? `${completedCount} of ${plan.plan_total} steps completed`
              : `${plan.plan_total} step${plan.plan_total !== 1 ? 's' : ''} to execute`
            }
            {plan.player_name && (
              <span className="ml-2 text-primary">
                for {plan.player_name}
              </span>
            )}
          </p>
        </div>
        {!isExecuting && (
          <div className="flex gap-2">
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
              Approve & Execute
            </Button>
          </div>
        )}
      </div>

      {/* Progress bar during execution */}
      {isExecuting && (
        <div className="w-full bg-muted rounded-full h-2">
          <div
            className="bg-blue-500 h-2 rounded-full transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      )}

      {/* Steps list */}
      <div className="space-y-2">
        {plan.plan.map((step, index) => {
          const status = getStepStatus(step, index)
          const isExpanded = expandedSteps.has(index)
          const hasLongDesc = isLongDescription(step)
          const isCollapsible = hasLongDesc || (step.props && Object.keys(step.props).length > 0)

          return (
            <div
              key={index}
              className={cn(
                "border rounded-md transition-all duration-200",
                getStatusBgColor(status)
              )}
            >
              {/* Step header - always visible */}
              <div 
                className={cn(
                  "flex items-start gap-3 p-3",
                  isCollapsible && "cursor-pointer hover:bg-muted/50"
                )}
                onClick={() => isCollapsible && toggleStep(index)}
              >
                {/* Status icon */}
                <div className="flex-shrink-0 mt-0.5">
                  {getStatusIcon(status)}
                </div>

                {/* Step number */}
                <div className={cn(
                  "w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0",
                  status === 'completed' ? 'bg-green-500/20 text-green-600' :
                  status === 'in_progress' ? 'bg-blue-500/20 text-blue-600' :
                  'bg-muted text-muted-foreground'
                )}>
                  {index + 1}
                </div>

                {/* Step content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={cn(
                      "text-sm",
                      status === 'completed' ? 'text-muted-foreground' : 'text-foreground'
                    )}>
                      {isExpanded && hasLongDesc ? getStepFullDescription(step) : getStepPreview(step)}
                    </span>
                  </div>
                  
                  {/* Agent badge */}
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
                      {formatAgentName(step.agent)}
                    </span>
                    {status === 'in_progress' && (
                      <span className="text-xs text-muted-foreground animate-pulse">
                        Processing...
                      </span>
                    )}
                  </div>
                </div>

                {/* Expand/collapse icon */}
                {isCollapsible && (
                  <div className="flex-shrink-0 text-muted-foreground">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4" />
                    ) : (
                      <ChevronRight className="w-4 h-4" />
                    )}
                  </div>
                )}
              </div>

              {/* Expanded content */}
              {isExpanded && (
                <div className="px-3 pb-3 ml-12 space-y-2 border-t border-border/50 pt-2">
                  {/* Full description for scouting steps (shown when collapsed text was truncated) */}
                  {hasLongDesc && (
                    <div className="text-sm text-foreground">
                      {getStepFullDescription(step)}
                    </div>
                  )}

                  {/* Arguments if present */}
                  {step.props && Object.keys(step.props).length > 0 && (
                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-muted-foreground">Arguments:</div>
                      <div className="text-xs font-mono bg-muted/50 p-2 rounded border overflow-x-auto">
                        <pre>{JSON.stringify(step.props, null, 2)}</pre>
                      </div>
                    </div>
                  )}

                  {/* Query for non-scouting plans */}
                  {step.query && !step.tool?.startsWith('Step ') && (
                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-muted-foreground">Query:</div>
                      <div className="text-xs text-foreground">{step.query}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer */}
      {!isExecuting && plan.plan_total > 0 && (
        <div className="text-xs text-muted-foreground pt-2 border-t">
          Click on a step to expand details. Review the plan before approving.
        </div>
      )}
    </div>
  )
}
