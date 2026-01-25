import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import type { ApiError } from "./api"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Extract error message from unknown error type.
 * Handles API errors, Error instances, and other error types.
 */
export function getErrorMessage(error: unknown, defaultMessage: string): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const apiError = error as ApiError
    return apiError.response?.data?.error || 
           apiError.response?.data?.message || 
           defaultMessage
  }
  if (error instanceof Error) {
    return error.message
  }
  return defaultMessage
}
