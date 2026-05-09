import React, { useState } from 'react'
import { Input, InputNumber, Modal, Slider, Tabs, Typography } from 'antd'
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

export default function SettingsModal(): React.ReactElement {
  const {
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
          }
        ]}
      />
    </Modal>
  )
}
