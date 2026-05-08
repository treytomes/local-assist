import React, { useState } from 'react'
import { Input, InputNumber, Modal, Slider, Tabs, Typography } from 'antd'
import { useAppStore } from '../store'
import type { ModelParams } from '../store'
import { AVAILABLE_MODELS } from '@shared/types'
import type { ModelId } from '@shared/types'

const { Text, Title } = Typography
const { TextArea } = Input

// Models that don't accept a temperature parameter
const NO_TEMPERATURE_MODELS: ReadonlySet<ModelId> = new Set(['gpt-5.3-chat'])

function ModelParamEditor({
  model,
  params,
  onChange
}: {
  model: ModelId
  params: ModelParams
  onChange: (p: ModelParams) => void
}): React.ReactElement {
  const supportsTemperature = !NO_TEMPERATURE_MODELS.has(model)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 480 }}>
      <Title level={5} style={{ color: 'var(--vscode-text)', margin: 0 }}>
        {model}
      </Title>

      {/* Temperature — hidden for models that don't accept it */}
      {supportsTemperature && (
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
      )}

      {/* Max tokens */}
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

      {/* Context window */}
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
    for (const model of AVAILABLE_MODELS) {
      setModelParams(model, draftParams[model])
    }
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
            label: 'Models',
            children: (
              <Tabs
                tabPosition="left"
                size="small"
                style={{ minHeight: 300 }}
                items={AVAILABLE_MODELS.map((model) => ({
                  key: model,
                  label: (
                    <Text style={{ color: 'var(--vscode-text)', fontSize: 12 }}>{model}</Text>
                  ),
                  children: (
                    <ModelParamEditor
                      model={model}
                      params={draftParams[model]}
                      onChange={(p) => setDraftParams((prev) => ({ ...prev, [model]: p }))}
                    />
                  )
                }))}
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
