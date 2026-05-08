import React from 'react'
import { Drawer, Tag, Typography } from 'antd'
import { useAppStore } from '../store'
import { AVAILABLE_MODELS } from '@shared/types'

const { Text } = Typography

// Keep in sync with TOOLS in main.py — frontend mirror for display only
const TOOL_DEFINITIONS = [
  {
    name: 'get_datetime',
    description: 'Get the current date, time, and timezone.',
    parameters: ['timezone (optional IANA name)'],
  },
  {
    name: 'get_system_info',
    description: 'Returns OS, CPU, RAM, swap, GPU details, and system model.',
    parameters: [],
  },
]

function Section({ title, children }: { title: string; children: React.ReactNode }): React.ReactElement {
  return (
    <div style={{ marginBottom: 20 }}>
      <Text
        style={{
          color: 'var(--vscode-text-muted)',
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontWeight: 600,
          display: 'block',
          marginBottom: 8
        }}
      >
        {title}
      </Text>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }): React.ReactElement {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 6 }}>
      <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, flexShrink: 0 }}>{label}</Text>
      <Text style={{ color: 'var(--vscode-text)', fontSize: 12, fontFamily: 'monospace', textAlign: 'right' }}>{value}</Text>
    </div>
  )
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function ContextInspector({ open, onClose }: Props): React.ReactElement {
  const {
    backendUrl,
    selectedModel,
    systemPrompt,
    modelParams,
    activeConvId,
    messagesByConv,
    health,
  } = useAppStore()

  const params = modelParams[selectedModel]
  const allMessages = activeConvId ? (messagesByConv[activeConvId] ?? []) : []
  const history = allMessages.filter((m) => m.role !== 'system' && !m.streaming)

  // Reconstruct the message list that would be sent on next request
  const wouldSend: { role: string; content: string }[] = []
  if (systemPrompt.trim()) {
    wouldSend.push({ role: 'system', content: systemPrompt.trim() })
  }
  wouldSend.push(...history.map((m) => ({ role: m.role, content: m.content })))

  // Apply context window truncation as the backend would
  const window = params.contextWindow
  let windowed = wouldSend
  if (wouldSend.length > window) {
    if (wouldSend[0].role === 'system') {
      windowed = [wouldSend[0], ...wouldSend.slice(-(window - 1))]
    } else {
      windowed = wouldSend.slice(-window)
    }
  }

  return (
    <Drawer
      title="Context Inspector"
      placement="right"
      width={480}
      open={open}
      onClose={onClose}
      styles={{
        body: { background: 'var(--vscode-bg)', padding: 16 },
        header: { background: 'var(--vscode-surface)', borderBottom: '1px solid var(--vscode-border)' },
        wrapper: { boxShadow: 'none' },
        mask: { background: 'rgba(0,0,0,0.4)' },
      }}
    >
      {/* Connection */}
      <Section title="Connection">
        <Row label="Backend URL" value={backendUrl} />
        <Row label="Azure" value={
          health ? <Tag color={health.azure ? 'cyan' : 'default'} style={{ margin: 0 }}>{health.azure ? 'Healthy' : 'Offline'}</Tag> : '—'
        } />
        <Row label="Ollama" value={
          health ? <Tag color={health.ollama ? 'green' : 'default'} style={{ margin: 0 }}>{health.ollama ? 'Healthy' : 'Offline'}</Tag> : '—'
        } />
        <Row label="Active provider" value={health?.active_provider ?? '—'} />
      </Section>

      {/* Model & params */}
      <Section title="Model Parameters">
        <Row label="Model" value={selectedModel} />
        <Row label="Max tokens" value={params.maxTokens.toLocaleString()} />
        <Row label="Temperature" value={
          AVAILABLE_MODELS.includes(selectedModel as typeof AVAILABLE_MODELS[number]) &&
          selectedModel === 'gpt-5.3-chat' ? 'n/a (fixed)' : params.temperature.toFixed(2)
        } />
        <Row label="Context window" value={`${params.contextWindow} messages`} />
      </Section>

      {/* Tools */}
      <Section title="Available Tools">
        {TOOL_DEFINITIONS.map((t) => (
          <div key={t.name} style={{ marginBottom: 8, padding: '6px 8px', background: 'var(--vscode-surface)', borderRadius: 2, border: '1px solid var(--vscode-border)' }}>
            <Text style={{ color: 'var(--vscode-text)', fontSize: 12, fontFamily: 'monospace', display: 'block' }}>{t.name}</Text>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, display: 'block' }}>{t.description}</Text>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>Params: {t.parameters.join(', ')}</Text>
          </div>
        ))}
      </Section>

      {/* Message list that would be sent */}
      <Section title={`Messages to Model (${windowed.length}${wouldSend.length !== windowed.length ? ` of ${wouldSend.length} — truncated by context window` : ''})`}>
        {windowed.length === 0 ? (
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>No messages yet — next message will start a new conversation.</Text>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {windowed.map((m, i) => (
              <div key={i} style={{ padding: '6px 8px', background: 'var(--vscode-surface)', borderRadius: 2, border: '1px solid var(--vscode-border)' }}>
                <Tag
                  color={m.role === 'system' ? 'purple' : m.role === 'user' ? 'blue' : 'default'}
                  style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: '0 0 4px' }}
                >
                  {m.role}
                </Tag>
                <pre style={{
                  margin: 0,
                  color: 'var(--vscode-text)',
                  fontSize: 11,
                  fontFamily: 'monospace',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: 120,
                  overflowY: 'auto'
                }}>
                  {m.content}
                </pre>
              </div>
            ))}
          </div>
        )}
      </Section>
    </Drawer>
  )
}
