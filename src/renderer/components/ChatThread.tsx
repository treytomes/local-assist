import React, { useEffect, useRef } from 'react'
import { Button, Tag, Tooltip, Typography } from 'antd'
import { DeleteOutlined, RedoOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons'
import type { Message } from '@shared/types'

const { Text } = Typography

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

interface MessageBubbleProps {
  msg: Message
  isLastUserMsg: boolean
  onRetry?: () => void
  onDelete?: () => void
  retryDisabled?: boolean
}

function MessageBubble({ msg, isLastUserMsg, onRetry, onDelete, retryDisabled }: MessageBubbleProps): React.ReactElement {
  const isUser = msg.role === 'user'

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isUser ? 'flex-end' : 'flex-start',
        gap: 4,
        marginBottom: 16,
        maxWidth: '78%',
        alignSelf: isUser ? 'flex-end' : 'flex-start'
      }}
    >
      {/* Role badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {!isUser && (
          <RobotOutlined style={{ color: 'var(--vscode-accent)', fontSize: 12 }} />
        )}
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
          {isUser ? 'You' : 'Assistant'}
        </Text>
        {!isUser && msg.model && (
          <Tag
            color="default"
            style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
          >
            {msg.model}
          </Tag>
        )}
        {!isUser && msg.provider && (
          <Tag
            color={msg.provider === 'azure' ? 'blue' : 'green'}
            style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
          >
            {msg.provider}
          </Tag>
        )}
        {!isUser && msg.streaming && (
          <Tag
            color="blue"
            style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}
          >
            streaming
          </Tag>
        )}
        {isUser && (
          <UserOutlined style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }} />
        )}
      </div>

      {/* Bubble */}
      <div
        style={{
          background: isUser ? 'var(--vscode-accent)' : 'var(--vscode-surface)',
          border: `1px solid ${isUser ? 'transparent' : 'var(--vscode-border)'}`,
          borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
          padding: '8px 12px',
          maxWidth: '100%'
        }}
      >
        <pre
          style={{
            margin: 0,
            color: isUser ? '#fff' : 'var(--vscode-text)',
            fontSize: 13,
            fontFamily: 'inherit',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            lineHeight: '1.5'
          }}
        >
          {msg.content}
          {msg.streaming && <span className="streaming-cursor" />}
        </pre>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10 }}>
          {formatTime(msg.timestamp)}
        </Text>
        {isLastUserMsg && onRetry && (
          <Tooltip title="Retry — re-send this message">
            <Button
              type="text"
              size="small"
              icon={<RedoOutlined style={{ fontSize: 11 }} />}
              onClick={onRetry}
              disabled={retryDisabled}
              style={{ color: 'var(--vscode-text-muted)', padding: '0 2px', height: 18 }}
            />
          </Tooltip>
        )}
        {onDelete && !msg.streaming && (
          <Tooltip title="Delete message">
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined style={{ fontSize: 11 }} />}
              onClick={onDelete}
              danger
              style={{ padding: '0 2px', height: 18 }}
            />
          </Tooltip>
        )}
      </div>
    </div>
  )
}

interface Props {
  messages: Message[]
  onRetry?: (text: string) => void
  onDeleteMessage?: (msgId: string) => void
  retryDisabled?: boolean
}

export default function ChatThread({ messages, onRetry, onDeleteMessage, retryDisabled }: Props): React.ReactElement {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const visible = messages.filter((m) => m.role !== 'system')
  const lastUserIdx = visible.reduce<number>(
    (acc, m, i) => (m.role === 'user' ? i : acc),
    -1
  )

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px 20px',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0
      }}
    >
      {visible.length === 0 && (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--vscode-text-muted)',
            fontSize: 13
          }}
        >
          Start a conversation…
        </div>
      )}
      {visible.map((msg, i) => (
        <MessageBubble
          key={msg.id}
          msg={msg}
          isLastUserMsg={i === lastUserIdx}
          onRetry={onRetry ? () => onRetry(msg.content) : undefined}
          onDelete={onDeleteMessage ? () => onDeleteMessage(msg.id) : undefined}
          retryDisabled={retryDisabled}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
