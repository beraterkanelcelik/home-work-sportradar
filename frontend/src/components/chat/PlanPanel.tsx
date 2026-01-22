/**
 * PlanPanel Component
 * 
 * Displays the active plan on the right side of the chat.
 * Shows plan steps with real-time progress updates.
 * 
 * Location: frontend/src/components/chat/PlanPanel.tsx
 */
import React from 'react'
import { X, ChevronLeft, ChevronRight, Check, Loader2, Circle, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface PlanStep {
  action: string
  tool?: string
  answer?: string
  props?: Record<string, any>
  params?: Record<string, any>
  agent: string
  query: string
  description?: string
  status?: 'pending' | 'in_progress' | 'completed' | 'error'
}

interface PlanProgress {
  current_step_index: number
  total_steps: number
  steps_status: Record<number, {
    status: 'pending' | 'in_progress' | 'completed' | 'error'
    step_name: string
    result?: string
  }>
}

interface PlanData {
  type: string
  plan: PlanStep[]
  plan_index: number
  plan_total: number
  player_name?: string
  sport_guess?: string
  intent?: string
  reasoning?: string
}

interface PlanPanelProps {
  plan: PlanData | null
  progress?: PlanProgress
  isExecuting: boolean
  isCollapsed: boolean
  onToggleCollapse: () => void
  onClose: () => void
  /** Called when user approves the plan */
  onApprove?: () => void
  /** Called when user rejects the plan */
  onReject?: () => void
  /** Whether the plan has been approved (hide buttons after approval) */
  isApproved?: boolean
  /** Whether the plan has completed execution */
  isCompleted?: boolean
}

export default function PlanPanel({
  plan,
  progress,
  isExecuting,
  isCollapsed,
  onToggleCollapse,
  onClose,
  onApprove,
  onReject,
  isApproved,
  isCompleted,
}: PlanPanelProps) {
  if (!plan) return null

  const getStepStatus = (step: PlanStep, index: number): 'pending' | 'in_progress' | 'completed' | 'error' => {
    // If plan is completed, all steps are completed
    if (isCompleted) {
      return 'completed'
    }
    
    // Check progress data first (streaming updates)
    if (progress?.steps_status?.[index]) {
      return progress.steps_status[index].status
    }
    
    // Fall back to step's own status
    if (step.status) return step.status
    
    // If plan is approved/executing, steps 0 and 1 (1 and 2 in UI) are already completed
    // because they represent the intake and planning phases that run BEFORE approval
    if (isApproved && index <= 1) {
      return 'completed'
    }
    
    // Infer from progress current_step_index
    if (progress && isExecuting) {
      if (index < progress.current_step_index) return 'completed'
      if (index === progress.current_step_index) return 'in_progress'
    }
    return 'pending'
  }

  const getStatusIcon = (status: 'pending' | 'in_progress' | 'completed' | 'error') => {
    switch (status) {
      case 'completed':
        return <Check className="w-3.5 h-3.5 text-green-500" />
      case 'in_progress':
        return <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
      case 'error':
        return <AlertCircle className="w-3.5 h-3.5 text-destructive" />
      default:
        return <Circle className="w-3.5 h-3.5 text-muted-foreground" />
    }
  }

  const completedCount = plan.plan.filter((step, idx) => getStepStatus(step, idx) === 'completed').length
  const progressPercent = plan.plan_total > 0 ? (completedCount / plan.plan_total) * 100 : 0

  // Collapsed view - just a thin bar with expand button
  if (isCollapsed) {
    return (
      <div className="w-10 border-l bg-card flex flex-col items-center py-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          className="mb-4"
          title="Expand plan panel"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        
        {/* Vertical progress indicator */}
        <div className="flex-1 flex flex-col items-center gap-1 w-full px-2">
          {plan.plan.map((step, index) => {
            const status = getStepStatus(step, index)
            return (
              <div
                key={index}
                className={cn(
                  "w-2 h-2 rounded-full",
                  status === 'completed' && 'bg-green-500',
                  status === 'in_progress' && 'bg-primary animate-pulse',
                  status === 'error' && 'bg-destructive',
                  status === 'pending' && 'bg-muted-foreground/30'
                )}
                title={`Step ${index + 1}: ${status}`}
              />
            )
          })}
        </div>
      </div>
    )
  }

  // Expanded view
  return (
    <div className="w-72 border-l bg-card flex flex-col">
      {/* Header */}
      <div className="p-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={onToggleCollapse}
            title="Collapse panel"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          <div>
            <h3 className="font-medium text-sm">
              {isCompleted ? 'Plan Completed' : isExecuting ? 'Executing Plan' : 'Plan'}
            </h3>
            {plan.player_name && (
              <p className="text-xs text-muted-foreground">
                {plan.player_name}
                {plan.sport_guess && ` (${plan.sport_guess})`}
              </p>
            )}
            {plan.intent && !plan.player_name && (
              <p className="text-xs text-muted-foreground capitalize">
                {plan.intent.replace(/_/g, ' ')}
              </p>
            )}
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={onClose}
          title="Close panel"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Progress bar */}
      {isExecuting && (
        <div className="px-3 py-2 border-b">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
            <span>Progress</span>
            <span>{completedCount}/{plan.plan_total}</span>
          </div>
          <div className="w-full bg-muted rounded-full h-1.5">
            <div 
              className="bg-primary h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {/* Steps list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {plan.plan.map((step, index) => {
          const status = getStepStatus(step, index)
          const stepResult = progress?.steps_status?.[index]?.result
          
          // Get the step description from various possible fields
          const stepDescription = step.description || step.query || step.tool || step.answer || 'Process'
          
          // Get action badge text
          const getActionBadge = (action: string) => {
            const actionLabels: Record<string, string> = {
              'rag_search': 'Search',
              'extract_player': 'Extract',
              'compose_report': 'Compose',
              'update_report': 'Update',
              'save_player': 'Save',
              'answer': 'Answer',
              'tool': 'Tool',
            }
            return actionLabels[action] || action
          }
          
          return (
            <div
              key={index}
              className={cn(
                "p-2 rounded-md border text-xs cursor-default",
                status === 'completed' && 'bg-green-500/5 border-green-500/20',
                status === 'in_progress' && 'bg-primary/5 border-primary/20',
                status === 'error' && 'bg-destructive/5 border-destructive/20',
                status === 'pending' && 'bg-muted/30 border-transparent'
              )}
              title={stepDescription}
            >
              <div className="flex items-start gap-2">
                <div className="flex-shrink-0 mt-0.5">
                  {getStatusIcon(status)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground">
                      Step {index + 1}
                    </span>
                    {step.action && step.action !== 'tool' && (
                      <span className={cn(
                        "px-1.5 py-0.5 rounded text-[10px] font-medium",
                        step.action === 'rag_search' && 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
                        step.action === 'extract_player' && 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
                        step.action === 'compose_report' && 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
                        step.action === 'save_player' && 'bg-green-500/10 text-green-600 dark:text-green-400',
                        step.action === 'answer' && 'bg-gray-500/10 text-gray-600 dark:text-gray-400',
                      )}>
                        {getActionBadge(step.action)}
                      </span>
                    )}
                  </div>
                  <div 
                    className={cn(
                      "mt-0.5 line-clamp-2",
                      status === 'completed' ? 'text-muted-foreground' : 'text-foreground/80'
                    )}
                    title={stepDescription}
                  >
                    {stepDescription}
                  </div>
                  {stepResult && (
                    <div className="mt-1 text-muted-foreground italic line-clamp-1" title={stepResult}>
                      {stepResult}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div className="p-3 border-t">
        {isCompleted ? (
          // Plan completed - show completion message
          <div className="flex items-center gap-2 text-xs text-green-600 dark:text-green-400">
            <Check className="w-3.5 h-3.5" />
            <span>All {plan.plan_total} steps completed</span>
          </div>
        ) : isExecuting ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>Executing step {(progress?.current_step_index ?? -1) + 2} of {plan.plan_total}...</span>
          </div>
        ) : !isApproved && onApprove && onReject ? (
          // Show approval buttons when plan is awaiting approval
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground mb-2">
              Review the plan above and approve to begin execution.
            </p>
            <div className="flex gap-2">
              <Button
                onClick={onApprove}
                size="sm"
                className="flex-1"
              >
                <Check className="w-3.5 h-3.5 mr-1.5" />
                Approve Plan
              </Button>
              <Button
                onClick={onReject}
                variant="outline"
                size="sm"
                className="flex-1"
              >
                <X className="w-3.5 h-3.5 mr-1.5" />
                Reject
              </Button>
            </div>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">{plan.plan_total} steps total</span>
        )}
      </div>
    </div>
  )
}
