export interface HealthStatus {
  azure: boolean
  ollama: boolean
  local_tts: boolean
  local_stt: boolean
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

export interface Reaction {
  id: string
  message_id: string
  author: 'user' | 'assistant'
  emoji: string
  created_at: string
}

export interface WeatherForecastDay {
  date: string
  condition: string
  temp_high_f: number
  temp_low_f: number
  precipitation_in: number
  wind_max_mph: number
  sunrise: string
  sunset: string
}

export interface WeatherData {
  location: {
    lat: number
    lon: number
    city?: string
    region?: string
    country?: string
    timezone?: string
  }
  current: {
    condition: string
    temp_f: number
    feels_like_f: number
    humidity_pct: number
    precipitation_in: number
    wind_speed_mph: number
    wind_direction_deg: number
    pressure_hpa: number
    cloud_cover_pct: number
    is_day: boolean
  }
  forecast: WeatherForecastDay[]
}

export interface Message {
  id: string
  conversation_id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  model?: string | null
  provider?: string | null
  timestamp: string
  // frontend-only transient fields
  streaming?: boolean
  reactions?: Reaction[]
  // persisted — returned from GET /v1/conversations/:id
  tools_used?: Array<{
    name: string
    query?: string
    results?: Array<{ title: string; url: string; content: string; score: number }>
    reaction?: Reaction
    weather?: WeatherData
    sound?: { name: string; params: Record<string, unknown> }
  }>
}

export interface ConvUsage {
  total_cost_usd: number
  prompt_tokens: number
  completion_tokens: number
}

export const AVAILABLE_MODELS = ['Mistral-Large-3'] as const
export type ModelId = (typeof AVAILABLE_MODELS)[number]
