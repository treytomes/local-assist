import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  Badge,
  Button,
  Col,
  Divider,
  Input,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Typography
} from 'antd'
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SendOutlined
} from '@ant-design/icons'
import { useAppStore } from '../store'
import type { ApiResponse, HealthStatus, HttpMethod, PresetEndpoint } from '@shared/types'

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
    body: JSON.stringify({ title: 'Test conversation', model: 'gpt-5.3-chat' }, null, 2)
  },
  { label: 'GET /v1/conversations/{conv_id}', method: 'GET', path: '/v1/conversations/{conv_id}' },
  {
    label: 'PATCH /v1/conversations/{conv_id}',
    method: 'PATCH',
    path: '/v1/conversations/{conv_id}',
    body: JSON.stringify({ title: 'Renamed', model: 'gpt-5.3-chat' }, null, 2)
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
        model: 'gpt-5.3-chat',
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
    defaultVars: { provider: 'azure', model: 'gpt-5.3-chat' }
  },
  {
    label: 'POST /v1/pricing/{provider}/{model}',
    method: 'POST',
    path: '/v1/pricing/{provider}/{model}',
    body: JSON.stringify({ input_cost_per_1k: 0.002, output_cost_per_1k: 0.008 }, null, 2),
    defaultVars: { provider: 'azure', model: 'gpt-5.3-chat' }
  },
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

export default function DiagnosticDashboard(): React.ReactElement {
  const {
    backendUrl,
    health,
    healthLoading,
    healthLastChecked,
    setHealth,
    setHealthLoading,
    setHealthLastChecked,
    setBackendUrl
  } = useAppStore()

  const [autoRefresh, setAutoRefresh] = useState(true)
  const autoRefreshRef = useRef(autoRefresh)
  autoRefreshRef.current = autoRefresh

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
      setHealth({ azure: false, ollama: false, active_provider: 'none' })
      setHealthLastChecked(new Date())
    } finally {
      setHealthLoading(false)
    }
  }, [backendUrl, setHealth, setHealthLoading, setHealthLastChecked])

  useEffect(() => {
    fetchHealth()
    const id = setInterval(() => {
      if (autoRefreshRef.current) fetchHealth()
    }, 30_000)
    return () => clearInterval(id)
  }, [fetchHealth])

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

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={healthLoading}
              onClick={fetchHealth}
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
}
