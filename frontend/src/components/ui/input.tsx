import React, { forwardRef } from 'react'

export interface InputProps {
  className?: string
  type?: string
  placeholder?: string
  value?: string | number | readonly string[]
  defaultValue?: string | number | readonly string[]
  onChange?: React.ChangeEventHandler<HTMLInputElement>
  onFocus?: React.FocusEventHandler<HTMLInputElement>
  onBlur?: React.FocusEventHandler<HTMLInputElement>
  onKeyDown?: React.KeyboardEventHandler<HTMLInputElement>
  disabled?: boolean
  readOnly?: boolean
  required?: boolean
  name?: string
  id?: string
  autoFocus?: boolean
  autoComplete?: string
  maxLength?: number
  minLength?: number
  pattern?: string
  min?: string | number
  max?: string | number
  step?: string | number
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = '', type = 'text', ...props }, ref) => {
    const defaultClassName = 'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'
    return (
      <input
        type={type}
        className={`${defaultClassName} ${className}`}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
