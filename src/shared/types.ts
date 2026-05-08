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
