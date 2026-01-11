// Type declarations for npm packages

declare module 'axios' {
  export interface AxiosRequestConfig {
    baseURL?: string
    headers?: Record<string, string>
    params?: any
    data?: any
    responseType?: 'json' | 'stream' | 'text' | 'blob' | 'arraybuffer' | 'document'
    signal?: AbortSignal
  }

  export interface AxiosResponse<T = any> {
    data: T
    status: number
    statusText: string
    headers: any
    config: AxiosRequestConfig
  }

  export interface AxiosError<T = any> extends Error {
    config: AxiosRequestConfig
    code?: string
    request?: any
    response?: AxiosResponse<T>
    isAxiosError: boolean
  }

  export interface AxiosInstance {
    request<T = any>(config: AxiosRequestConfig): Promise<AxiosResponse<T>>
    get<T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>
    post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>
    put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>
    patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>
    delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>
    interceptors: {
      request: {
        use(onFulfilled?: (config: AxiosRequestConfig) => AxiosRequestConfig | Promise<AxiosRequestConfig>, onRejected?: (error: any) => any): number
      }
      response: {
        use(onFulfilled?: (response: AxiosResponse) => AxiosResponse | Promise<AxiosResponse>, onRejected?: (error: any) => any): number
      }
    }
  }

  export interface AxiosStatic extends AxiosInstance {
    create(config?: AxiosRequestConfig): AxiosInstance
  }

  const axios: AxiosStatic
  export default axios
}

declare module 'clsx' {
  export type ClassValue = string | number | boolean | undefined | null | Record<string, boolean> | ClassValue[]
  export function clsx(...inputs: ClassValue[]): string
}

declare module 'tailwind-merge' {
  export function twMerge(...inputs: (string | undefined | null | false)[]): string
}

declare module 'class-variance-authority' {
  export type VariantProps<T> = {
    [K in keyof T]?: T[K] extends Record<string, any> ? keyof T[K] : never
  }

  export function cva(
    base: string,
    config?: {
      variants?: Record<string, Record<string, string>>
      defaultVariants?: Record<string, string>
    }
  ): (props?: Record<string, any>) => string
}

// Image imports
declare module '*.png' {
  const value: string
  export default value
}

declare module '*.jpg' {
  const value: string
  export default value
}

declare module '*.jpeg' {
  const value: string
  export default value
}

declare module '*.svg' {
  const value: string
  export default value
}

declare module '*.gif' {
  const value: string
  export default value
}

declare module '*.webp' {
  const value: string
  export default value
}

// React Markdown
declare module 'react-markdown' {
  import { ReactNode } from 'react'
  export interface Components {
    [key: string]: React.ComponentType<any>
  }
  export interface ReactMarkdownProps {
    children: string
    components?: Components
    remarkPlugins?: any[]
    rehypePlugins?: any[]
    className?: string
  }
  const ReactMarkdown: React.FC<ReactMarkdownProps>
  export default ReactMarkdown
}

declare module 'remark-gfm' {
  const remarkGfm: any
  export default remarkGfm
}

declare module 'rehype-highlight' {
  const rehypeHighlight: any
  export default rehypeHighlight
}

// Microlink React JSON View
declare module '@microlink/react-json-view' {
  import { ComponentType } from 'react'
  export interface ReactJsonProps {
    src: any
    theme?: string | object
    collapsed?: number | boolean
    collapseStringsAfterLength?: number
    shouldCollapse?: (field: any) => boolean
    groupArraysAfterLength?: number
    enableClipboard?: boolean
    displayObjectSize?: boolean
    displayDataTypes?: boolean
    name?: string | false
    iconStyle?: string
    indentWidth?: number
    sortKeys?: boolean
    quotesOnKeys?: boolean
    validationMessage?: string
    className?: string
    style?: React.CSSProperties
  }
  const ReactJson: ComponentType<ReactJsonProps>
  export default ReactJson
}

// Lucide React (icons are already typed, but adding for completeness)
declare module 'lucide-react' {
  import { ComponentType, SVGProps } from 'react'
  export interface IconProps extends SVGProps<SVGSVGElement> {
    size?: string | number
    strokeWidth?: string | number
    absoluteStrokeWidth?: boolean
  }
  export const CheckCircle2: ComponentType<IconProps>
  export const XCircle: ComponentType<IconProps>
  export const Loader2: ComponentType<IconProps>
  export const RefreshCw: ComponentType<IconProps>
  export const AlertCircle: ComponentType<IconProps>
  export const ChevronDown: ComponentType<IconProps>
  // Add other icons as needed
}
