import React from 'react'
import { Button } from '@/components/ui/button'

export interface PlanStep {
  action: string
  tool: string
  props: Record<string, any>
  agent: string
  query: string
}

export interface PlanProposalData {
  type: string
  plan: PlanStep[]
  plan_index: number
  plan_total: number
}

interface PlanProposalProps {
  plan: PlanProposalData
  onApprove: () => void
  onReject: () => void
  isExecuting?: boolean
}

export default function PlanProposal({ plan, onApprove, onReject, isExecuting = false }: PlanProposalProps) {
  const formatAgentName = (agent: string): string => {
    return agent.charAt(0).toUpperCase() + agent.slice(1)
  }

  const formatToolName = (tool: string): string => {
    return tool.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
  }

  return (
    <div className="border rounded-lg bg-muted/30 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-foreground">Plan Proposal</h3>
          <p className="text-sm text-muted-foreground mt-1">
            {plan.plan_total} step{plan.plan_total !== 1 ? 's' : ''} to execute
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
        {isExecuting && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="w-2 h-2 bg-primary rounded-full animate-pulse"></div>
            <span>Executing plan...</span>
          </div>
        )}
      </div>

      <div className="space-y-3">
        {plan.plan.map((step, index) => (
          <div
            key={index}
            className="border rounded-md p-3 bg-background/50 space-y-2"
          >
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary">
                {index + 1}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-foreground">
                    {formatToolName(step.tool)}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">
                    {formatAgentName(step.agent)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {step.action}
                  </span>
                </div>
              </div>
            </div>

            {Object.keys(step.props).length > 0 && (
              <div className="ml-8 space-y-1">
                <div className="text-xs font-semibold text-muted-foreground">Arguments:</div>
                <div className="text-xs font-mono bg-muted/50 p-2 rounded border">
                  {JSON.stringify(step.props, null, 2)}
                </div>
              </div>
            )}

            {step.query && (
              <div className="ml-8">
                <div className="text-xs font-semibold text-muted-foreground">Query:</div>
                <div className="text-xs text-foreground mt-1">{step.query}</div>
              </div>
            )}
          </div>
        ))}
      </div>

      {plan.plan_total > 0 && (
        <div className="text-xs text-muted-foreground pt-2 border-t">
          This plan will execute {plan.plan_total} tool{plan.plan_total !== 1 ? 's' : ''} sequentially.
          Review the steps above before approving.
        </div>
      )}
    </div>
  )
}
