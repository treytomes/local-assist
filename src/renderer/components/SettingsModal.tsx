import React, { useEffect, useState } from 'react'
import { Button, Input, InputNumber, Modal, Slider, Tabs, Typography } from 'antd'
import { CheckCircleOutlined, DisconnectOutlined, GoogleOutlined } from '@ant-design/icons'
import { useAppStore } from '../store'
import type { ModelParams } from '../store'

const { Text } = Typography
const { TextArea } = Input

const MODEL = 'Mistral-Large-3' as const

function ModelParamEditor({
  params,
  onChange
}: {
  params: ModelParams
  onChange: (p: ModelParams) => void
}): React.ReactElement {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 480 }}>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <Text style={{ color: 'var(--vscode-text)', fontSize: 13 }}>Temperature</Text>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, fontFamily: 'monospace' }}>
            {params.temperature.toFixed(2)}
          </Text>
        </div>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, display: 'block', marginBottom: 6 }}>
          Higher = more creative, lower = more deterministic. Range 0.0 – 2.0.
        </Text>
        <Slider
          min={0}
          max={2}
          step={0.05}
          value={params.temperature}
          onChange={(v) => onChange({ ...params, temperature: v })}
          styles={{ track: { background: 'var(--vscode-accent)' } }}
        />
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <Text style={{ color: 'var(--vscode-text)', fontSize: 13 }}>Max output tokens</Text>
          <InputNumber
            size="small"
            min={64}
            max={16384}
            step={256}
            value={params.maxTokens}
            onChange={(v) => v != null && onChange({ ...params, maxTokens: v })}
            style={{ width: 90, fontSize: 12 }}
          />
        </div>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
          Maximum tokens the model will generate per response. Range 64 – 16384.
        </Text>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <Text style={{ color: 'var(--vscode-text)', fontSize: 13 }}>Context window (messages)</Text>
          <InputNumber
            size="small"
            min={1}
            max={200}
            step={1}
            value={params.contextWindow}
            onChange={(v) => v != null && onChange({ ...params, contextWindow: v })}
            style={{ width: 70, fontSize: 12 }}
          />
        </div>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
          How many recent messages are sent to the model. The system message is always preserved.
        </Text>
      </div>
    </div>
  )
}

function GoogleAccountTab({ backendUrl }: { backendUrl: string }): React.ReactElement {
  const [status, setStatus] = useState<{ connected: boolean; email: string | null } | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const [pollCount, setPollCount] = useState(0)

  useEffect(() => {
    fetch(`${backendUrl}/v1/google/auth-status`)
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setStatus({ connected: false, email: null }))
  }, [backendUrl, pollCount])

  // Poll for auth completion after initiating flow
  useEffect(() => {
    if (!connecting) return
    const id = setInterval(() => {
      fetch(`${backendUrl}/v1/google/auth-status`)
        .then((r) => r.json())
        .then((s) => {
          if (s.connected) {
            setStatus(s)
            setConnecting(false)
          }
        })
        .catch(() => {})
    }, 2000)
    return () => clearInterval(id)
  }, [connecting, backendUrl])

  async function handleConnect() {
    setConnecting(true)
    try {
      const res = await fetch(`${backendUrl}/v1/google/auth-start`, { method: 'POST' })
      const data = await res.json()
      if (data.auth_url) {
        await window.electronAPI.openExternal(data.auth_url)
      }
    } catch {
      setConnecting(false)
    }
  }

  async function handleRevoke() {
    setRevoking(true)
    try {
      await fetch(`${backendUrl}/v1/google/revoke`, { method: 'POST' })
      setPollCount((n) => n + 1)
    } finally {
      setRevoking(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 480 }}>
      <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>
        Connect your Google account to give Mara access to Calendar, Tasks, and Drive (read-only).
        Your tokens are stored locally and never leave this machine.
      </Text>

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 14px',
        background: 'var(--vscode-bg)',
        border: '1px solid var(--vscode-border)',
        borderRadius: 6,
      }}>
        {status?.connected ? (
          <>
            <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
            <div style={{ flex: 1 }}>
              <Text style={{ color: 'var(--vscode-text)', fontSize: 13, display: 'block' }}>
                Connected
              </Text>
              {status.email && (
                <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
                  {status.email}
                </Text>
              )}
            </div>
            <Button
              size="small"
              danger
              icon={<DisconnectOutlined />}
              loading={revoking}
              onClick={handleRevoke}
            >
              Disconnect
            </Button>
          </>
        ) : (
          <>
            <GoogleOutlined style={{ color: 'var(--vscode-text-muted)', fontSize: 16 }} />
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 13, flex: 1 }}>
              {connecting ? 'Waiting for browser sign-in…' : 'Not connected'}
            </Text>
            <Button
              size="small"
              type="primary"
              icon={<GoogleOutlined />}
              loading={connecting}
              onClick={handleConnect}
            >
              Connect
            </Button>
          </>
        )}
      </div>

      <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
        Requires <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> in your{' '}
        <code>.env</code> file. See the README for setup instructions.
      </Text>
    </div>
  )
}

export default function SettingsModal(): React.ReactElement {
  const {
    backendUrl,
    settingsOpen,
    setSettingsOpen,
    systemPrompt,
    setSystemPrompt,
    modelParams,
    setModelParams
  } = useAppStore()

  // Local draft state — only committed on OK
  const [draftPrompt, setDraftPrompt] = useState(systemPrompt)
  const [draftParams, setDraftParams] = useState(modelParams)

  function handleOpen(): void {
    setDraftPrompt(systemPrompt)
    setDraftParams(modelParams)
  }

  function handleOk(): void {
    setSystemPrompt(draftPrompt)
    setModelParams(MODEL, draftParams[MODEL])
    setSettingsOpen(false)
  }

  function handleCancel(): void {
    setSettingsOpen(false)
  }

  return (
    <Modal
      title="Settings"
      open={settingsOpen}
      onOk={handleOk}
      onCancel={handleCancel}
      okText="Save"
      width={560}
      afterOpenChange={(open) => open && handleOpen()}
      styles={{
        content: { background: 'var(--vscode-surface)', padding: '20px 24px' },
        header: { background: 'var(--vscode-surface)', borderBottom: '1px solid var(--vscode-border)' },
        footer: { background: 'var(--vscode-surface)', borderTop: '1px solid var(--vscode-border)' },
        mask: { background: 'rgba(0,0,0,0.6)' }
      }}
    >
      <Tabs
        size="small"
        items={[
          {
            key: 'models',
            label: 'Model',
            children: (
              <ModelParamEditor
                params={draftParams[MODEL]}
                onChange={(p) => setDraftParams((prev) => ({ ...prev, [MODEL]: p }))}
              />
            )
          },
          {
            key: 'system-prompt',
            label: 'System Prompt',
            children: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>
                  Applied as the first system message on every request. Leave blank to send no system prompt.
                </Text>
                <TextArea
                  rows={12}
                  value={draftPrompt}
                  onChange={(e) => setDraftPrompt(e.target.value)}
                  placeholder="You are a helpful assistant…"
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
            )
          },
          {
            key: 'google',
            label: 'Google',
            children: <GoogleAccountTab backendUrl={backendUrl} />
          }
        ]}
      />
    </Modal>
  )
}
