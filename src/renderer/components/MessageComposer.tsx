import React, { useRef, useState } from 'react'
import { Button, Tooltip } from 'antd'
import { AudioOutlined, LoadingOutlined, SendOutlined } from '@ant-design/icons'
import { useAppStore } from '../store'

type MicState = 'idle' | 'recording' | 'transcribing'

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
  const backendUrl = useAppStore((s) => s.backendUrl)
  const [text, setText] = useState('')
  const [micState, setMicState] = useState<MicState>('idle')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

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
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }

  async function startRecording(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setMicState('transcribing')
        try {
          const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
          const form = new FormData()
          form.append('file', blob, 'audio.webm')
          const res = await fetch(`${backendUrl}/v1/audio/transcriptions`, { method: 'POST', body: form })
          if (res.ok) {
            const data = await res.json()
            const transcript = data.text?.trim() ?? ''
            if (transcript) {
              setText((prev) => prev ? `${prev} ${transcript}` : transcript)
              setTimeout(() => {
                const el = textareaRef.current
                if (!el) return
                el.style.height = 'auto'
                el.style.height = `${Math.min(el.scrollHeight, 144)}px`
                el.focus()
              }, 0)
            }
          }
        } finally {
          setMicState('idle')
        }
      }
      recorder.start()
      mediaRef.current = recorder
      setMicState('recording')
    } catch {
      setMicState('idle')
    }
  }

  function stopRecording(): void {
    mediaRef.current?.stop()
  }

  const micBusy = micState !== 'idle'
  const micLabel = micState === 'recording' ? 'Stop recording' : micState === 'transcribing' ? 'Transcribing…' : 'Voice input'

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
        <Tooltip title={micLabel}>
          <Button
            icon={micState === 'transcribing' ? <LoadingOutlined /> : <AudioOutlined />}
            onClick={micState === 'recording' ? stopRecording : startRecording}
            disabled={disabled || streaming || micState === 'transcribing'}
            danger={micState === 'recording'}
            style={{ flexShrink: 0 }}
          />
        </Tooltip>
        <Tooltip title="Send (Enter)">
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={submit}
            loading={streaming}
            disabled={!text.trim() || disabled || micBusy}
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
