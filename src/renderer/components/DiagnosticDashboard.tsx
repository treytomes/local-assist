import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  Badge,
  Button,
  Col,
  Divider,
  Empty,
  Input,
  InputNumber,
  List,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography
} from 'antd'
import {
  ApiOutlined,
  BellOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SendOutlined,
  WarningOutlined
} from '@ant-design/icons'
import { useAppStore } from '../store'
import type { ApiResponse, HealthStatus, HttpMethod, PresetEndpoint } from '@shared/types'
import CostDashboard from './CostDashboard'

const { Text, Title } = Typography
const { TextArea } = Input

interface PresetGroup {
  label: string
  options: Array<PresetEndpoint & { value: number }>
}

interface PresetWithVars extends PresetEndpoint {
  defaultVars?: Record<string, string>
}

const PRESETS: PresetWithVars[] = [
  // Health
  { label: 'GET /v1/health', method: 'GET', path: '/v1/health' },
  // Conversations
  { label: 'GET /v1/conversations', method: 'GET', path: '/v1/conversations' },
  {
    label: 'POST /v1/conversations',
    method: 'POST',
    path: '/v1/conversations',
    body: JSON.stringify({ title: 'Test conversation', model: 'Mistral-Large-3' }, null, 2)
  },
  { label: 'GET /v1/conversations/{conv_id}', method: 'GET', path: '/v1/conversations/{conv_id}' },
  {
    label: 'PATCH /v1/conversations/{conv_id}',
    method: 'PATCH',
    path: '/v1/conversations/{conv_id}',
    body: JSON.stringify({ title: 'Renamed', model: 'Mistral-Large-3' }, null, 2)
  },
  { label: 'DELETE /v1/conversations/{conv_id}', method: 'DELETE', path: '/v1/conversations/{conv_id}' },
  { label: 'POST /v1/conversations/{conv_id}/embed', method: 'POST', path: '/v1/conversations/{conv_id}/embed' },
  // Chat
  {
    label: 'POST /v1/chat/completions',
    method: 'POST',
    path: '/v1/chat/completions',
    body: JSON.stringify(
      {
        model: 'Mistral-Large-3',
        messages: [{ role: 'user', content: 'Hello' }],
        max_tokens: 2048,
        temperature: 0.7,
        stream: false,
      },
      null,
      2
    )
  },
  {
    label: 'GET /v1/context',
    method: 'GET',
    path: '/v1/context?query=hello'
  },
  // Usage
  { label: 'GET /v1/usage', method: 'GET', path: '/v1/usage?days=30' },
  { label: 'GET /v1/usage/{conv_id}', method: 'GET', path: '/v1/usage/{conv_id}' },
  // Pricing
  { label: 'GET /v1/pricing', method: 'GET', path: '/v1/pricing' },
  {
    label: 'GET /v1/pricing/{provider}/{model}',
    method: 'GET',
    path: '/v1/pricing/{provider}/{model}',
    defaultVars: { provider: 'azure', model: 'Mistral-Large-3' }
  },
  {
    label: 'POST /v1/pricing/{provider}/{model}',
    method: 'POST',
    path: '/v1/pricing/{provider}/{model}',
    body: JSON.stringify({ input_cost_per_1k: 0.002, output_cost_per_1k: 0.008 }, null, 2),
    defaultVars: { provider: 'azure', model: 'Mistral-Large-3' }
  },
  { label: 'GET /v1/search/usage', method: 'GET', path: '/v1/search/usage' },
]

const PRESET_GROUPS: PresetGroup[] = [
  {
    label: 'Health',
    options: [0].map((i) => ({ ...PRESETS[i], value: i }))
  },
  {
    label: 'Conversations',
    options: [1, 2, 3, 4, 5, 6].map((i) => ({ ...PRESETS[i], value: i }))
  },
  {
    label: 'Chat',
    options: [7, 8].map((i) => ({ ...PRESETS[i], value: i }))
  },
  {
    label: 'Usage',
    options: [9, 10].map((i) => ({ ...PRESETS[i], value: i }))
  },
  {
    label: 'Pricing',
    options: [11, 12, 13].map((i) => ({ ...PRESETS[i], value: i }))
  },
  {
    label: 'Search',
    options: [14].map((i) => ({ ...PRESETS[i], value: i }))
  },
]

const HTTP_METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

function statusColor(status: number): string {
  if (status >= 200 && status < 300) return 'var(--vscode-success)'
  if (status >= 400 && status < 500) return 'var(--vscode-warning)'
  return 'var(--vscode-error)'
}

function ProviderBadge({
  healthy,
  label,
  isActive
}: {
  healthy: boolean
  label: string
  isActive: boolean
}): React.ReactElement {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
      <Badge status={healthy ? 'success' : 'error'} />
      <Text style={{ color: 'var(--vscode-text)', minWidth: 56 }}>{label}</Text>
      <Tag
        color={healthy ? 'cyan' : 'default'}
        style={{ fontSize: 11, lineHeight: '16px', padding: '0 6px', margin: 0 }}
      >
        {healthy ? 'Healthy' : 'Offline'}
      </Tag>
      {isActive && (
        <Tag
          color="blue"
          style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
        >
          active
        </Tag>
      )}
    </div>
  )
}

interface Watcher {
  id: string
  name: string
  description: string
  source_type: string
  interval_seconds: number
  enabled: boolean
  one_shot: boolean
  fire_at: string | null
  last_run: string | null
  last_error: string | null
}

// Decompose seconds into a value+unit pair for editing
function secondsToUnit(s: number): { value: number; unit: 's' | 'm' | 'h' } {
  if (s >= 3600 && s % 3600 === 0) return { value: s / 3600, unit: 'h' }
  if (s >= 60 && s % 60 === 0) return { value: s / 60, unit: 'm' }
  return { value: s, unit: 's' }
}
function unitToSeconds(value: number, unit: 's' | 'm' | 'h'): number {
  if (unit === 'h') return value * 3600
  if (unit === 'm') return value * 60
  return value
}

function IntervalEditor({ watcher, backendUrl, onChange }: {
  watcher: Watcher
  backendUrl: string
  onChange: (id: string, seconds: number) => void
}): React.ReactElement {
  const initial = secondsToUnit(watcher.interval_seconds)
  const [value, setValue] = useState(initial.value)
  const [unit, setUnit] = useState<'s' | 'm' | 'h'>(initial.unit)
  const [saving, setSaving] = useState(false)

  // Reset local state if the watcher interval changes externally
  useEffect(() => {
    const u = secondsToUnit(watcher.interval_seconds)
    setValue(u.value)
    setUnit(u.unit)
  }, [watcher.interval_seconds])

  async function save(): Promise<void> {
    const seconds = unitToSeconds(value, unit)
    if (seconds === watcher.interval_seconds) return
    setSaving(true)
    try {
      await fetch(`${backendUrl}/v1/watchers/${watcher.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval_seconds: seconds }),
      })
      onChange(watcher.id, seconds)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Space.Compact size="small">
      <InputNumber
        min={1}
        max={unit === 'h' ? 24 : unit === 'm' ? 1440 : 86400}
        value={value}
        onChange={(v) => v != null && setValue(v)}
        onBlur={save}
        onPressEnter={save}
        style={{ width: 56, fontSize: 11 }}
        disabled={saving}
      />
      <Select
        size="small"
        value={unit}
        onChange={(u) => setUnit(u)}
        onBlur={save}
        style={{ width: 52, fontSize: 11 }}
        options={[
          { label: 's', value: 's' },
          { label: 'm', value: 'm' },
          { label: 'h', value: 'h' },
        ]}
        disabled={saving}
      />
    </Space.Compact>
  )
}

interface QuietHours {
  enabled: boolean
  start: string
  end: string
}

function QuietHoursEditor({ backendUrl }: { backendUrl: string }): React.ReactElement {
  const [qh, setQh] = useState<QuietHours>({ enabled: true, start: '21:00', end: '07:00' })

  useEffect(() => {
    fetch(`${backendUrl}/v1/quiet-hours`)
      .then((r) => r.json())
      .then(setQh)
      .catch(() => {})
  }, [backendUrl])

  async function save(next: QuietHours): Promise<void> {
    setQh(next)
    await fetch(`${backendUrl}/v1/quiet-hours`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next),
    }).catch(() => {})
  }

  return (
    <div style={{
      padding: '10px 12px',
      marginBottom: 16,
      background: 'var(--vscode-bg)',
      border: '1px solid var(--vscode-border)',
      borderRadius: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, flex: 1 }}>
          Quiet Hours
        </Text>
        <Switch
          size="small"
          checked={qh.enabled}
          onChange={(v) => save({ ...qh, enabled: v })}
          checkedChildren="On"
          unCheckedChildren="Off"
        />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>From</Text>
        <Input
          size="small"
          type="time"
          value={qh.start}
          onChange={(e) => setQh((prev) => ({ ...prev, start: e.target.value }))}
          onBlur={() => save(qh)}
          style={{ width: 100, fontSize: 12, background: 'var(--vscode-surface)', color: 'var(--vscode-text)', borderColor: 'var(--vscode-border)' }}
          disabled={!qh.enabled}
        />
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>to</Text>
        <Input
          size="small"
          type="time"
          value={qh.end}
          onChange={(e) => setQh((prev) => ({ ...prev, end: e.target.value }))}
          onBlur={() => save(qh)}
          style={{ width: 100, fontSize: 12, background: 'var(--vscode-surface)', color: 'var(--vscode-text)', borderColor: 'var(--vscode-border)' }}
          disabled={!qh.enabled}
        />
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
          (notifications suppressed)
        </Text>
      </div>
    </div>
  )
}

function WatchersPanel({ backendUrl }: { backendUrl: string }): React.ReactElement {
  const [watchers, setWatchers] = useState<Watcher[]>([])
  const [loading, setLoading] = useState(false)

  const fetchWatchers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${backendUrl}/v1/watchers`)
      setWatchers(await res.json())
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [backendUrl])

  // Fetch on mount and poll every 10 seconds so newly created/fired alarms appear promptly
  useEffect(() => {
    fetchWatchers()
    const id = setInterval(fetchWatchers, 10_000)
    return () => clearInterval(id)
  }, [fetchWatchers])

  async function toggleEnabled(w: Watcher): Promise<void> {
    await fetch(`${backendUrl}/v1/watchers/${w.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !w.enabled }),
    })
    setWatchers((prev) => prev.map((x) => x.id === w.id ? { ...x, enabled: !w.enabled } : x))
  }

  async function deleteWatcher(w: Watcher): Promise<void> {
    await fetch(`${backendUrl}/v1/watchers/${w.id}`, { method: 'DELETE' })
    setWatchers((prev) => prev.filter((x) => x.id !== w.id))
  }

  function handleIntervalChange(id: string, seconds: number): void {
    setWatchers((prev) => prev.map((x) => x.id === id ? { ...x, interval_seconds: seconds } : x))
  }


  if (!loading && watchers.length === 0) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description={<Text style={{ color: 'var(--vscode-text-muted)' }}>No watchers registered</Text>} />
      </div>
    )
  }

  return (
    <div style={{ padding: 16, overflowY: 'auto', height: '100%' }}>
      <QuietHoursEditor backendUrl={backendUrl} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
          Active Watchers
        </Text>
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={fetchWatchers} style={{ fontSize: 11 }} />
      </div>
      <List
        dataSource={watchers}
        loading={loading}
        renderItem={(w) => (
          <List.Item
            style={{ padding: '8px 0', borderBottom: '1px solid var(--vscode-border)' }}
            actions={[
              <Switch
                key="toggle"
                size="small"
                checked={w.enabled}
                onChange={() => toggleEnabled(w)}
                checkedChildren="On"
                unCheckedChildren="Off"
              />,
              <Popconfirm
                key="delete"
                title="Remove this watcher?"
                onConfirm={() => deleteWatcher(w)}
                okText="Remove"
                cancelText="Cancel"
              >
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <BellOutlined style={{ color: w.enabled ? 'var(--vscode-accent)' : 'var(--vscode-text-muted)', fontSize: 13 }} />
                  <Text style={{ color: 'var(--vscode-text)', fontSize: 13 }}>{w.name}</Text>
                  {w.fire_at
                    ? <Tag color="purple" style={{ fontSize: 10, padding: '0 4px', margin: 0 }}>fires {new Date(w.fire_at).toLocaleTimeString()}</Tag>
                    : <IntervalEditor watcher={w} backendUrl={backendUrl} onChange={handleIntervalChange} />
                  }
                </div>
              }
              description={
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>{w.description}</Text>
                  {w.last_error && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <WarningOutlined style={{ color: 'var(--vscode-error)', fontSize: 11 }} />
                      <Text style={{ color: 'var(--vscode-error)', fontSize: 11 }}>{w.last_error}</Text>
                    </div>
                  )}
                  {w.last_run && !w.last_error && (
                    <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
                      Last run: {new Date(w.last_run).toLocaleTimeString()}
                    </Text>
                  )}
                </div>
              }
            />
          </List.Item>
        )}
      />
    </div>
  )
}

export default function DiagnosticDashboard(): React.ReactElement {
  const {
    backendUrl,
    health,
    healthLoading,
    healthLastChecked,
    setHealth,
    setHealthLoading,
    setHealthLastChecked,
    setBackendUrl,
    speechProvider,
    setSpeechProvider,
  } = useAppStore()

  const [activeTab, setActiveTab] = useState<'status' | 'cost' | 'watchers'>('status')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const autoRefreshRef = useRef(autoRefresh)
  autoRefreshRef.current = autoRefresh

  const [searchUsage, setSearchUsage] = useState<{
    calls_used: number
    limit: number
    calls_remaining: number
    days_until_reset: number
    reset_date: string
  } | null>(null)
  const [searchBaseline, setSearchBaseline] = useState<number>(0)
  const [editingBaseline, setEditingBaseline] = useState(false)

  const [speechProviderLoading, setSpeechProviderLoading] = useState(false)

  const [whisperModel, setWhisperModel] = useState<string>('base.en')
  const [whisperModels, setWhisperModels] = useState<string[]>([])
  const [whisperLoaded, setWhisperLoaded] = useState(false)
  const [whisperLoading, setWhisperLoading] = useState(false)

  const fetchSpeechProvider = useCallback(async () => {
    try {
      const [provRes, modelRes] = await Promise.all([
        fetch(`${backendUrl}/v1/audio/provider`),
        fetch(`${backendUrl}/v1/audio/stt-model`),
      ])
      const prov = await provRes.json()
      const model = await modelRes.json()
      setSpeechProvider(prov.provider === 'local' ? 'local' : 'azure')
      setWhisperModel(model.model ?? 'base.en')
      setWhisperModels(model.models ?? [])
      setWhisperLoaded(model.loaded ?? false)
    } catch {
      // non-fatal
    }
  }, [backendUrl, setSpeechProvider])

  async function toggleSpeechProvider(): Promise<void> {
    const next = speechProvider === 'azure' ? 'local' : 'azure'
    setSpeechProviderLoading(true)
    try {
      await fetch(`${backendUrl}/v1/audio/provider`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: next }),
      })
      setSpeechProvider(next)
    } catch {
      // non-fatal
    } finally {
      setSpeechProviderLoading(false)
    }
  }

  async function changeWhisperModel(size: string): Promise<void> {
    setWhisperModel(size)
    setWhisperLoaded(false)
    await fetch(`${backendUrl}/v1/audio/stt-model`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: size }),
    }).catch(() => {})
  }

  async function loadWhisperModel(): Promise<void> {
    setWhisperLoading(true)
    try {
      const res = await fetch(`${backendUrl}/v1/audio/stt-model/load`, { method: 'POST' })
      if (res.ok) setWhisperLoaded(true)
    } catch {
      // non-fatal
    } finally {
      setWhisperLoading(false)
    }
  }

  const [selectedPresetIdx, setSelectedPresetIdx] = useState(0)
  const [method, setMethod] = useState<HttpMethod>('GET')
  const [path, setPath] = useState('/v1/health')
  const [pathVars, setPathVars] = useState<Record<string, string>>({})
  const [body, setBody] = useState('')
  const [apiResponse, setApiResponse] = useState<ApiResponse | null>(null)
  const [sending, setSending] = useState(false)

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true)
    try {
      const res = await fetch(`${backendUrl}/v1/health`)
      const data: HealthStatus = await res.json()
      setHealth(data)
      setHealthLastChecked(new Date())
    } catch {
      setHealth({ azure: false, ollama: false, local_tts: false, local_stt: false, active_provider: 'none' })
      setHealthLastChecked(new Date())
    } finally {
      setHealthLoading(false)
    }
  }, [backendUrl, setHealth, setHealthLoading, setHealthLastChecked])

  const fetchSearchUsage = useCallback(async () => {
    try {
      const res = await fetch(`${backendUrl}/v1/search/usage`)
      setSearchUsage(await res.json())
    } catch {
      // non-fatal
    }
  }, [backendUrl])

  useEffect(() => {
    fetchHealth()
    fetchSearchUsage()
    fetchSpeechProvider()
    const id = setInterval(() => {
      if (autoRefreshRef.current) {
        fetchHealth()
        fetchSearchUsage()
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [fetchHealth, fetchSearchUsage, fetchSpeechProvider])

  function extractVarNames(p: string): string[] {
    return [...p.matchAll(/\{(\w+)\}/g)].map((m) => m[1])
  }

  function applyPreset(idx: number): void {
    const preset = PRESETS[idx]
    setSelectedPresetIdx(idx)
    setMethod(preset.method)
    setPath(preset.path)
    setBody(preset.body ?? '')
    // Seed default values; preserve existing values for vars that are already set
    const vars: Record<string, string> = {}
    for (const name of extractVarNames(preset.path)) {
      vars[name] = pathVars[name] ?? preset.defaultVars?.[name] ?? ''
    }
    setPathVars(vars)
  }

  function resolvePath(raw: string): string {
    return raw.replace(/\{(\w+)\}/g, (_, name) => pathVars[name] || `{${name}}`)
  }

  async function sendRequest(): Promise<void> {
    setSending(true)
    setApiResponse(null)
    const resolved = resolvePath(path)
    const url = `${backendUrl}${resolved.startsWith('/') ? resolved : '/' + resolved}`
    const start = performance.now()
    try {
      const hasBody = ['POST', 'PUT', 'PATCH'].includes(method) && body.trim()
      const res = await fetch(url, {
        method,
        headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
        body: hasBody ? body : undefined,
      })
      const elapsedMs = Math.round(performance.now() - start)
      const contentType = res.headers.get('content-type') ?? ''
      const parsed: unknown = contentType.includes('application/json')
        ? await res.json()
        : await res.text()
      setApiResponse({ status: res.status, statusText: res.statusText, elapsedMs, body: parsed })
      // Auto-fill conv_id when a conversation is created
      if (
        res.status === 201 &&
        resolved === '/v1/conversations' &&
        typeof parsed === 'object' &&
        parsed !== null &&
        'id' in parsed
      ) {
        setPathVars((prev) => ({ ...prev, conv_id: String((parsed as Record<string, unknown>).id) }))
      }
    } catch (err) {
      const elapsedMs = Math.round(performance.now() - start)
      setApiResponse({
        status: 0,
        statusText: 'Network Error',
        elapsedMs,
        body: null,
        error: err instanceof Error ? err.message : String(err)
      })
    } finally {
      setSending(false)
    }
  }

  const showBody = ['POST', 'PUT', 'PATCH'].includes(method)
  const pathVarNames = extractVarNames(path)
  const lastCheckedStr = healthLastChecked ? healthLastChecked.toLocaleTimeString() : '—'

  const statusContent = (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--vscode-bg)' }}>
      {/* Body */}
      <Row style={{ flex: 1, overflow: 'hidden', height: 0 }}>
        {/* Left: Provider Health */}
        <Col
          span={8}
          style={{
            display: 'flex',
            flexDirection: 'column',
            padding: 16,
            overflowY: 'auto',
            borderRight: '1px solid var(--vscode-border)'
          }}
        >
          <Text
            style={{
              color: 'var(--vscode-text-muted)',
              fontSize: 11,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              fontWeight: 600
            }}
          >
            Provider Health
          </Text>
          <Divider style={{ borderColor: 'var(--vscode-border)', margin: '8px 0' }} />

          {health ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <ProviderBadge
                healthy={health.azure}
                label="Azure"
                isActive={health.active_provider === 'azure'}
              />
              <ProviderBadge
                healthy={health.ollama}
                label="Ollama"
                isActive={health.active_provider === 'ollama'}
              />
            </div>
          ) : (
            <Text style={{ color: 'var(--vscode-text-muted)' }}>
              {healthLoading ? 'Checking…' : 'No data'}
            </Text>
          )}

          <Divider style={{ borderColor: 'var(--vscode-border)', margin: '12px 0 8px' }} />
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, marginBottom: 8, display: 'block' }}>
            Voice (TTS / STT)
          </Text>

          {/* Provider toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, minWidth: 70 }}>Provider:</Text>
            <Switch
              size="small"
              checked={speechProvider === 'local'}
              onChange={toggleSpeechProvider}
              loading={speechProviderLoading}
              checkedChildren="Local"
              unCheckedChildren="Azure"
              style={{ minWidth: 64 }}
            />
            {speechProvider === 'local' && !(health?.local_tts) && (
              <Tooltip title="Kokoro TTS not yet loaded — will load on first synthesis call">
                <WarningOutlined style={{ color: 'var(--vscode-warning)', fontSize: 13 }} />
              </Tooltip>
            )}
          </div>

          {/* Health badges */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
            <ProviderBadge
              healthy={health?.local_tts ?? false}
              label="Kokoro TTS"
              isActive={speechProvider === 'local'}
            />
            <ProviderBadge
              healthy={health?.local_stt ?? false}
              label="Whisper STT"
              isActive={speechProvider === 'local'}
            />
          </div>

          {/* Whisper model selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, minWidth: 70 }}>STT model:</Text>
            <Select
              size="small"
              value={whisperModel}
              onChange={changeWhisperModel}
              style={{ flex: 1, fontSize: 12 }}
              options={(whisperModels.length ? whisperModels : ['base.en']).map((m) => ({ label: m, value: m }))}
              popupMatchSelectWidth={false}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Button
              size="small"
              loading={whisperLoading}
              disabled={whisperLoaded}
              onClick={loadWhisperModel}
              style={{ fontSize: 11, marginLeft: 78 }}
            >
              {whisperLoaded ? 'Loaded' : 'Download / Load'}
            </Button>
            {whisperLoaded && (
              <Tag color="green" style={{ fontSize: 10, padding: '0 4px', margin: 0 }}>in memory</Tag>
            )}
          </div>

          {searchUsage && (() => {
            const adjusted = Math.min(searchUsage.calls_used + searchBaseline, searchUsage.limit)
            const pct = Math.round((adjusted / searchUsage.limit) * 100)
            return (
              <>
                <Divider style={{ borderColor: 'var(--vscode-border)', margin: '12px 0 8px' }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
                    Tavily Search Quota
                  </Text>
                  <Tooltip title="Only calls made through this app are tracked locally. Set a baseline to account for calls made elsewhere.">
                    <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10, cursor: 'default' }}>ⓘ</Text>
                  </Tooltip>
                </div>
                <Progress
                  percent={pct}
                  size="small"
                  strokeColor={
                    pct >= 90 ? 'var(--vscode-error)'
                    : pct >= 70 ? 'var(--vscode-warning)'
                    : 'var(--vscode-accent)'
                  }
                  trailColor="var(--vscode-border)"
                  format={() => (
                    <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
                      {adjusted}/{searchUsage.limit}
                    </Text>
                  )}
                />
                <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, marginTop: 4, display: 'block' }}>
                  Resets in {searchUsage.days_until_reset}d · {searchUsage.reset_date}
                </Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
                  <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, flexShrink: 0 }}>
                    Portal baseline:
                  </Text>
                  {editingBaseline ? (
                    <InputNumber
                      size="small"
                      min={0}
                      max={searchUsage.limit}
                      value={searchBaseline}
                      onChange={(v) => setSearchBaseline(v ?? 0)}
                      onBlur={() => setEditingBaseline(false)}
                      onPressEnter={() => setEditingBaseline(false)}
                      autoFocus
                      style={{ width: 72, fontSize: 11 }}
                    />
                  ) : (
                    <Text
                      onClick={() => setEditingBaseline(true)}
                      style={{ color: 'var(--vscode-accent)', fontSize: 11, cursor: 'pointer', textDecoration: 'underline dotted' }}
                    >
                      {searchBaseline} calls
                    </Text>
                  )}
                </div>
              </>
            )
          })()}

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={healthLoading}
              onClick={() => { fetchHealth(); fetchSearchUsage() }}
              style={{ fontSize: 12 }}
            >
              Refresh
            </Button>
            <Switch
              size="small"
              checked={autoRefresh}
              onChange={setAutoRefresh}
              checkedChildren="Auto"
              unCheckedChildren="Manual"
            />
          </div>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, marginTop: 8 }}>
            Last checked: {lastCheckedStr}
          </Text>
        </Col>

        {/* Right: API Tester */}
        <Col
          span={16}
          style={{ display: 'flex', flexDirection: 'column', padding: 16, overflowY: 'auto' }}
        >
          <Text
            style={{
              color: 'var(--vscode-text-muted)',
              fontSize: 11,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              fontWeight: 600
            }}
          >
            API Tester
          </Text>
          <Divider style={{ borderColor: 'var(--vscode-border)', margin: '8px 0' }} />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
            {/* Preset selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, minWidth: 48 }}>Preset:</Text>
              <Select
                size="small"
                value={selectedPresetIdx}
                onChange={applyPreset}
                options={PRESET_GROUPS.map((g) => ({
                  label: g.label,
                  options: g.options.map((o) => ({ label: o.label, value: o.value }))
                }))}
                style={{ flex: 1, fontSize: 12 }}
                popupMatchSelectWidth={false}
              />
            </div>

            {/* Method + path */}
            <Space.Compact style={{ width: '100%' }}>
              <Select
                size="small"
                value={method}
                onChange={(v) => setMethod(v as HttpMethod)}
                options={HTTP_METHODS.map((m) => ({ label: m, value: m }))}
                style={{ width: 96 }}
              />
              <Input
                size="small"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/v1/health"
                style={{ flex: 1, fontFamily: 'monospace', fontSize: 12 }}
                onPressEnter={sendRequest}
              />
            </Space.Compact>

            {/* Path variable inputs — one row per {variable} found in path */}
            {pathVarNames.map((name) => (
              <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Text
                  style={{
                    color: 'var(--vscode-text-muted)',
                    fontSize: 12,
                    minWidth: 64,
                    fontFamily: 'monospace'
                  }}
                >
                  {`{${name}}`}
                </Text>
                <Input
                  size="small"
                  value={pathVars[name] ?? ''}
                  onChange={(e) =>
                    setPathVars((prev) => ({ ...prev, [name]: e.target.value }))
                  }
                  placeholder={name}
                  style={{ flex: 1, fontFamily: 'monospace', fontSize: 12 }}
                />
              </div>
            ))}
          </div>

          {/* Body textarea */}
          {showBody && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
              <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>Body (JSON):</Text>
              <TextArea
                rows={6}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="{}"
                style={{
                  fontFamily: 'monospace',
                  fontSize: 12,
                  background: 'var(--vscode-bg)',
                  color: 'var(--vscode-text)',
                  borderColor: 'var(--vscode-border)',
                  resize: 'vertical'
                }}
              />
            </div>
          )}

          <Button
            type="primary"
            size="small"
            icon={<SendOutlined />}
            loading={sending}
            onClick={sendRequest}
            style={{
              alignSelf: 'flex-start',
              background: 'var(--vscode-accent)',
              borderColor: 'var(--vscode-accent)'
            }}
          >
            Send
          </Button>

          {/* Response */}
          {apiResponse && (
            <>
              <Divider style={{ borderColor: 'var(--vscode-border)', margin: '12px 0 8px' }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                {apiResponse.status >= 200 && apiResponse.status < 300 ? (
                  <CheckCircleOutlined style={{ color: 'var(--vscode-success)' }} />
                ) : (
                  <CloseCircleOutlined style={{ color: 'var(--vscode-error)' }} />
                )}
                <Text
                  style={{
                    color: statusColor(apiResponse.status),
                    fontFamily: 'monospace',
                    fontSize: 13,
                    fontWeight: 600
                  }}
                >
                  {apiResponse.status} {apiResponse.statusText}
                </Text>
                <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>
                  · {apiResponse.elapsedMs}ms
                </Text>
              </div>
              {apiResponse.error ? (
                <Text
                  style={{
                    color: 'var(--vscode-error)',
                    fontSize: 12,
                    fontFamily: 'monospace'
                  }}
                >
                  {apiResponse.error}
                </Text>
              ) : (
                <pre
                  style={{
                    background: 'var(--vscode-bg)',
                    border: '1px solid var(--vscode-border)',
                    borderRadius: 2,
                    padding: '8px 10px',
                    margin: 0,
                    color: 'var(--vscode-text)',
                    fontSize: 12,
                    fontFamily: 'monospace',
                    overflowX: 'auto',
                    maxHeight: 340,
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word'
                  }}
                >
                  {typeof apiResponse.body === 'string'
                    ? apiResponse.body
                    : JSON.stringify(apiResponse.body, null, 2)}
                </pre>
              )}
            </>
          )}
        </Col>
      </Row>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--vscode-bg)' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 16px',
          background: 'var(--vscode-surface)',
          borderBottom: '1px solid var(--vscode-border)',
          flexShrink: 0
        }}
      >
        <ApiOutlined style={{ color: 'var(--vscode-accent)', fontSize: 16 }} />
        <Title level={5} style={{ margin: 0, color: 'var(--vscode-text)', fontWeight: 500 }}>
          local-assist — Diagnostic Dashboard
        </Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>Backend:</Text>
          <Input
            size="small"
            value={backendUrl}
            onChange={(e) => setBackendUrl(e.target.value)}
            style={{ width: 230, fontSize: 12, fontFamily: 'monospace' }}
          />
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 0, background: 'var(--vscode-surface)', borderBottom: '1px solid var(--vscode-border)', flexShrink: 0, padding: '0 16px' }}>
        {(['status', 'cost', 'watchers'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid var(--vscode-accent)' : '2px solid transparent',
              color: activeTab === tab ? 'var(--vscode-text)' : 'var(--vscode-text-muted)',
              cursor: 'pointer',
              fontSize: 13,
              padding: '6px 12px',
              marginBottom: -1,
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab panes — all mounted, only active one visible */}
      <div style={{ flex: 1, overflow: 'hidden', display: activeTab === 'status' ? 'flex' : 'none', flexDirection: 'column' }}>
        {statusContent}
      </div>
      <div style={{ flex: 1, overflow: 'hidden', display: activeTab === 'cost' ? 'flex' : 'none', flexDirection: 'column' }}>
        <CostDashboard />
      </div>
      <div style={{ flex: 1, overflow: 'hidden', display: activeTab === 'watchers' ? 'flex' : 'none', flexDirection: 'column' }}>
        <WatchersPanel backendUrl={backendUrl} />
      </div>
    </div>
  )
}
