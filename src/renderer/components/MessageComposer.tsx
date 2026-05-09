import React, { useRef, useState } from 'react'
import { Button, Tooltip } from 'antd'
import { SendOutlined } from '@ant-design/icons'

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
  streaming?: boolean
}

export default function MessageComposer({
  onSend,
  disabled,
  streaming
}: Props): React.ReactElement {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function submit(): void {
    const trimmed = text.trim()
    if (!trimmed || disabled || streaming) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function onInput(e: React.ChangeEvent<HTMLTextAreaElement>): void {
    setText(e.target.value)
    // Auto-grow up to ~6 lines
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }

  return (
    <div
      style={{
        borderTop: '1px solid var(--vscode-border)',
        background: 'var(--vscode-surface)',
        padding: '8px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        flexShrink: 0
      }}
    >
      {/* Input row */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={onInput}
          onKeyDown={onKeyDown}
          placeholder={streaming ? 'Waiting for response…' : 'Message (Enter to send, Shift+Enter for newline)'}
          disabled={disabled || streaming}
          rows={1}
          style={{
            flex: 1,
            resize: 'none',
            background: 'var(--vscode-bg)',
            color: 'var(--vscode-text)',
            border: '1px solid var(--vscode-border)',
            borderRadius: 2,
            padding: '6px 8px',
            fontSize: 13,
            fontFamily: 'inherit',
            lineHeight: '20px',
            outline: 'none',
            minHeight: 32,
            maxHeight: 144,
            overflowY: 'auto'
          }}
        />
        <Tooltip title="Send (Enter)">
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={submit}
            loading={streaming}
            disabled={!text.trim() || disabled}
            style={{
              background: 'var(--vscode-accent)',
              borderColor: 'var(--vscode-accent)',
              flexShrink: 0
            }}
          />
        </Tooltip>
      </div>
    </div>
  )
}
