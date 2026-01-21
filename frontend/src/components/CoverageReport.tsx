/**
 * CoverageReport Component
 *
 * Displays evidence coverage from scouting workflow Node 5.
 * Shows what fields were found vs missing, and confidence level.
 */

import React from 'react'
import { Shield, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'

export interface CoverageReportData {
  found: string[]
  missing: string[]
  confidence: 'low' | 'med' | 'high'
  chunk_count: number
}

interface CoverageReportProps {
  coverage: CoverageReportData
}

export default function CoverageReport({ coverage }: CoverageReportProps) {
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

  const getConfidenceIcon = (confidence: string) => {
    switch (confidence) {
      case 'high':
        return <Shield className="w-4 h-4" />
      case 'med':
        return <AlertTriangle className="w-4 h-4" />
      case 'low':
        return <XCircle className="w-4 h-4" />
      default:
        return null
    }
  }

  const { found, missing, confidence, chunk_count } = coverage

  return (
    <div className="border rounded-lg bg-muted/30 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-foreground">Evidence Coverage</h3>
          <p className="text-sm text-muted-foreground mt-1">
            {chunk_count} chunks retrieved • {confidence} confidence
          </p>
        </div>
        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md ${getConfidenceColor(confidence)}`}>
          {getConfidenceIcon(confidence)}
          <span className="text-sm font-medium capitalize">{confidence}</span>
        </div>
      </div>

      {found.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-semibold text-muted-foreground">
            Fields Found ({found.length})
          </div>
          <div className="border rounded-md p-3 bg-background/50">
            <ul className="space-y-1">
              {found.map((field, idx) => (
                <li key={idx} className="text-sm text-foreground flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                  <span>{field}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {missing.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-semibold text-muted-foreground">
            Fields Missing ({missing.length})
          </div>
          <div className="border rounded-md p-3 bg-background/50">
            <ul className="space-y-1">
              {missing.map((field, idx) => (
                <li key={idx} className="text-sm text-foreground flex items-start gap-2">
                  <XCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                  <span>{field}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {found.length === 0 && missing.length === 0 && (
        <div className="text-sm text-muted-foreground italic">
          No field coverage data available
        </div>
      )}
    </div>
  )
}
