import React, { useEffect, useRef, useState } from 'react'
import { Button, Input, Tooltip, Typography } from 'antd'
import type { InputRef } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SearchOutlined
} from '@ant-design/icons'
import { useAppStore } from '../store'
import type { Conversation } from '@shared/types'

const { Text } = Typography

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

interface Props {
  onNewConversation: () => void
  onSelectConversation: (id: string) => void
}

export default function ConversationList({
  onNewConversation,
  onSelectConversation
}: Props): React.ReactElement {
  const {
    backendUrl,
    conversations,
    activeConvId,
    setConversations,
    updateConversation,
    removeConversation
  } = useAppStore()

  const [search, setSearch] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const renameInputRef = useRef<InputRef>(null)

  useEffect(() => {
    fetch(`${backendUrl}/v1/conversations`)
      .then((r) => r.json())
      .then((data: Conversation[]) => setConversations(data))
      .catch(console.error)
  }, [backendUrl, setConversations])

  useEffect(() => {
    if (renamingId && renameInputRef.current) {
      renameInputRef.current.focus()
      renameInputRef.current.select?.()
    }
  }, [renamingId])

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  )

  function startRename(conv: Conversation, e: React.MouseEvent): void {
    e.stopPropagation()
    setRenamingId(conv.id)
    setRenameValue(conv.title)
  }

  async function commitRename(id: string): Promise<void> {
    const trimmed = renameValue.trim()
    setRenamingId(null)
    if (!trimmed) return
    updateConversation(id, { title: trimmed })
    fetch(`${backendUrl}/v1/conversations/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: trimmed })
    }).catch(console.error)
  }

  async function deleteConv(id: string, e: React.MouseEvent): Promise<void> {
    e.stopPropagation()
    removeConversation(id)
    fetch(`${backendUrl}/v1/conversations/${id}`, { method: 'DELETE' }).catch(console.error)
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        background: 'var(--vscode-sidebar)',
        borderRight: '1px solid var(--vscode-border)'
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '10px 10px 6px',
          flexShrink: 0
        }}
      >
        <Text
          style={{
            color: 'var(--vscode-text-muted)',
            fontSize: 11,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontWeight: 600,
            flex: 1
          }}
        >
          Conversations
        </Text>
        <Tooltip title="New conversation">
          <Button
            type="text"
            size="small"
            icon={<PlusOutlined style={{ fontSize: 13 }} />}
            onClick={onNewConversation}
            style={{ color: 'var(--vscode-text-muted)', padding: '0 4px' }}
          />
        </Tooltip>
      </div>

      {/* Search */}
      <div style={{ padding: '0 8px 8px', flexShrink: 0 }}>
        <Input
          size="small"
          prefix={<SearchOutlined style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }} />}
          placeholder="Filter…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ fontSize: 12 }}
        />
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {filtered.length === 0 && (
          <Text
            style={{
              color: 'var(--vscode-text-muted)',
              fontSize: 12,
              padding: '12px 12px',
              display: 'block'
            }}
          >
            {search ? 'No matches' : 'No conversations yet'}
          </Text>
        )}
        {filtered.map((conv) => {
          const isActive = conv.id === activeConvId
          const isRenaming = conv.id === renamingId
          return (
            <div
              key={conv.id}
              onClick={() => !isRenaming && onSelectConversation(conv.id)}
              style={{
                padding: '6px 10px',
                cursor: 'pointer',
                background: isActive ? 'var(--vscode-surface)' : 'transparent',
                borderLeft: isActive ? '2px solid var(--vscode-accent)' : '2px solid transparent',
                display: 'flex',
                flexDirection: 'column',
                gap: 2,
                userSelect: 'none'
              }}
              className="conv-item"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {isRenaming ? (
                  <Input
                    ref={renameInputRef}
                    size="small"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => commitRename(conv.id)}
                    onPressEnter={() => commitRename(conv.id)}
                    onClick={(e) => e.stopPropagation()}
                    style={{ fontSize: 12, flex: 1 }}
                  />
                ) : (
                  <>
                    <Text
                      ellipsis
                      style={{
                        color: isActive ? 'var(--vscode-text)' : 'var(--vscode-text-muted)',
                        fontSize: 12,
                        flex: 1,
                        lineHeight: '18px'
                      }}
                    >
                      {conv.title}
                    </Text>
                    <div
                      style={{ display: 'flex', gap: 2, flexShrink: 0 }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Tooltip title="Rename">
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined style={{ fontSize: 11 }} />}
                          onClick={(e) => startRename(conv, e)}
                          style={{ color: 'var(--vscode-text-muted)', padding: '0 2px', height: 18 }}
                        />
                      </Tooltip>
                      <Tooltip title="Delete">
                        <Button
                          type="text"
                          size="small"
                          icon={<DeleteOutlined style={{ fontSize: 11 }} />}
                          onClick={(e) => deleteConv(conv.id, e)}
                          style={{ color: 'var(--vscode-text-muted)', padding: '0 2px', height: 18 }}
                          danger
                        />
                      </Tooltip>
                    </div>
                  </>
                )}
              </div>
              <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10 }}>
                {relativeTime(conv.updated_at)}
              </Text>
            </div>
          )
        })}
      </div>
    </div>
  )
}
