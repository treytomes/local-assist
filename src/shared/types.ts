export interface HealthStatus {
  azure: boolean
  ollama: boolean
  active_provider: 'azure' | 'ollama' | 'none'
}

export interface ApiResponse {
  status: number
  statusText: string
  elapsedMs: number
  body: unknown
  error?: string
}

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface PresetEndpoint {
  label: string
  method: HttpMethod
  path: string
  body?: string
}

export interface Conversation {
  id: string
  title: string
  model: string
  provider: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  conversation_id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  model?: string | null
  provider?: string | null
  timestamp: string
  // frontend-only: streamed assistant turns not yet persisted
  streaming?: boolean
}

export interface ConvUsage {
  total_cost_usd: number
  prompt_tokens: number
  completion_tokens: number
}

export const AVAILABLE_MODELS = ['gpt-5.3-chat', 'Mistral-Large-3'] as const
export type ModelId = (typeof AVAILABLE_MODELS)[number]
