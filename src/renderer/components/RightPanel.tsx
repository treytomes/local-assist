import React, { useEffect } from 'react'
import { Badge, Divider, Tag, Typography } from 'antd'
import { useAppStore } from '../store'
import type { HealthStatus } from '@shared/types'

const { Text } = Typography

function fmt(usd: number): string {
  return usd < 0.01 ? `$${(usd * 100).toFixed(3)}¢` : `$${usd.toFixed(4)}`
}

export default function RightPanel(): React.ReactElement {
  const { backendUrl, health, setHealth, activeConvId, usageByConv, setConvUsage } = useAppStore()

  // Fetch health if not already populated (Chat tab opened before Diagnostics tab)
  useEffect(() => {
    if (health) return
    fetch(`${backendUrl}/v1/health`)
      .then((r) => r.json())
      .then((data: HealthStatus) => setHealth(data))
      .catch(console.error)
  }, [backendUrl, health, setHealth])

  useEffect(() => {
    if (!activeConvId) return
    fetch(`${backendUrl}/v1/usage/${activeConvId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data && typeof data.total_cost_usd === 'number') {
          setConvUsage(activeConvId, data)
        }
      })
      .catch(console.error)
  }, [backendUrl, activeConvId, setConvUsage])

  const usage = activeConvId ? usageByConv[activeConvId] : null

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        padding: 12,
        background: 'var(--vscode-surface)',
        borderLeft: '1px solid var(--vscode-border)',
        overflowY: 'auto',
        minWidth: 180
      }}
    >
      {/* Provider status */}
      <Text
        style={{
          color: 'var(--vscode-text-muted)',
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontWeight: 600
        }}
      >
        Providers
      </Text>
      <Divider style={{ borderColor: 'var(--vscode-border)', margin: '6px 0' }} />
      {health ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
          {(['azure', 'ollama'] as const).map((p) => (
            <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Badge status={health[p] ? 'success' : 'error'} />
              <Text style={{ color: 'var(--vscode-text)', fontSize: 12, flex: 1, textTransform: 'capitalize' }}>
                {p}
              </Text>
              {health.active_provider === p && (
                <Tag
                  color="blue"
                  style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
                >
                  active
                </Tag>
              )}
            </div>
          ))}
        </div>
      ) : (
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, marginBottom: 16 }}>
          Checking…
        </Text>
      )}

      {/* Conversation cost */}
      <Text
        style={{
          color: 'var(--vscode-text-muted)',
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontWeight: 600
        }}
      >
        This Conversation
      </Text>
      <Divider style={{ borderColor: 'var(--vscode-border)', margin: '6px 0' }} />
      {!activeConvId ? (
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>No conversation selected</Text>
      ) : !usage ? (
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>Loading…</Text>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>Cost</Text>
            <Text style={{ color: 'var(--vscode-success)', fontSize: 12, fontFamily: 'monospace' }}>
              {fmt(usage.total_cost_usd)}
            </Text>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>Prompt tok.</Text>
            <Text style={{ color: 'var(--vscode-text)', fontSize: 12, fontFamily: 'monospace' }}>
              {usage.prompt_tokens.toLocaleString()}
            </Text>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>Completion tok.</Text>
            <Text style={{ color: 'var(--vscode-text)', fontSize: 12, fontFamily: 'monospace' }}>
              {usage.completion_tokens.toLocaleString()}
            </Text>
          </div>
        </div>
      )}
    </div>
  )
}
