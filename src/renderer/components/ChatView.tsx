import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Typography } from 'antd'
import { BugOutlined, LayoutOutlined, SettingOutlined } from '@ant-design/icons'
import SettingsModal from './SettingsModal'
import ContextInspector from './ContextInspector'
import { v4 as uuidv4 } from 'uuid'
import { useAppStore } from '../store'
import ConversationList from './ConversationList'
import ChatThread from './ChatThread'
import MessageComposer from './MessageComposer'
import RightPanel from './RightPanel'
import type { Conversation, Message, ModelId, Reaction } from '@shared/types'

const { Text } = Typography

export default function ChatView(): React.ReactElement {
  const {
    backendUrl,
    activeConvId,
    setActiveConvId,
    addConversation,
    updateConversation,
    messagesByConv,
    setMessages,
    appendMessage,
    patchMessage,
    replaceMessageId,
    setConvUsage,
    rightPanelVisible,
    setRightPanelVisible,
    selectedModel,
    setSelectedModel,
    setSettingsOpen,
    systemPrompt,
    modelParams
  } = useAppStore()

  const [streaming, setStreaming] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const streamingMsgIdRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Fetch messages (+ reactions) when active conversation changes
  useEffect(() => {
    if (!activeConvId) return
    if (messagesByConv[activeConvId]) return // already loaded
    fetch(`${backendUrl}/v1/conversations/${activeConvId}`)
      .then((r) => r.json())
      .then(async (data: Conversation & { messages: Message[] }) => {
        const msgs = data.messages ?? []
        // Load reactions for all messages in parallel
        const reactionResults = await Promise.all(
          msgs.map((m) =>
            fetch(`${backendUrl}/v1/reactions/${m.id}`)
              .then((r) => r.json() as Promise<Reaction[]>)
              .catch(() => [] as Reaction[])
          )
        )
        const msgsWithReactions = msgs.map((m, i) => ({ ...m, reactions: reactionResults[i] }))
        setMessages(activeConvId, msgsWithReactions)
        if (data.model) setSelectedModel(data.model as ModelId)
      })
      .catch(console.error)
  }, [activeConvId, backendUrl, messagesByConv, setMessages, setSelectedModel])

  const handleNewConversation = useCallback(async () => {
    const res = await fetch(`${backendUrl}/v1/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New conversation', model: selectedModel })
    })
    const conv: Conversation = await res.json()
    addConversation(conv)
    setActiveConvId(conv.id)
    setMessages(conv.id, [])
  }, [backendUrl, selectedModel, addConversation, setActiveConvId, setMessages])

  const handleSelectConversation = useCallback(
    (id: string) => {
      setActiveConvId(id)
    },
    [setActiveConvId]
  )

  const handleSend = useCallback(
    async (text: string, isRetry = false, historyOverride?: Message[]) => {
      // Create conversation on first message if none selected
      let convId = activeConvId
      if (!convId) {
        const res = await fetch(`${backendUrl}/v1/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: text.slice(0, 60), model: selectedModel })
        })
        const conv: Conversation = await res.json()
        addConversation(conv)
        setActiveConvId(conv.id)
        setMessages(conv.id, [])
        convId = conv.id
      }

      const now = new Date().toISOString()

      // Optimistically add user message
      const userMsg: Message = {
        id: uuidv4(),
        conversation_id: convId,
        role: 'user',
        content: text,
        timestamp: now
      }
      appendMessage(convId, userMsg)

      // Placeholder streaming assistant message
      const assistantMsgId = uuidv4()
      const assistantMsg: Message = {
        id: assistantMsgId,
        conversation_id: convId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        streaming: true
      }
      appendMessage(convId, assistantMsg)
      streamingMsgIdRef.current = assistantMsgId
      setStreaming(true)

      // Build message history — use override when provided (retry path avoids stale closure)
      const history = (historyOverride ?? messagesByConv[convId] ?? []).filter((m) => !m.streaming)
      const params = modelParams[selectedModel]

      // Prepend system prompt if set
      const messages: { role: string; content: string }[] = []
      if (systemPrompt.trim()) {
        messages.push({ role: 'system', content: systemPrompt.trim() })
      }
      messages.push(
        ...history.map((m) => ({ role: m.role, content: m.content })),
        { role: 'user', content: text }
      )

      let accumulatedContent = ''
      const abort = new AbortController()
      abortRef.current = abort

      try {
        const res = await fetch(`${backendUrl}/v1/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: convId,
            model: selectedModel,
            messages,
            max_tokens: params.maxTokens,
            temperature: params.temperature,
            context_window: params.contextWindow,
            stream: true,
            is_retry: isRetry
          }),
          signal: abort.signal
        })

        const reader = res.body?.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (reader) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (!raw) continue
            try {
              const evt = JSON.parse(raw) as {
                type: string
                content?: string
                message?: string
                conversation_id?: string
                model?: string
                provider?: string
                user_msg_id?: string
                assistant_msg_id?: string | null
                empty?: boolean
                usage?: { prompt_tokens: number; completion_tokens: number; cost_usd: number }
                tools_used?: Array<{ name: string; query?: string; results?: Array<{ title: string; url: string; content: string; score: number }>; reaction?: Reaction }>
              }
              if (evt.type === 'error') {
                patchMessage(convId!, assistantMsgId, {
                  content: `[Error: ${evt.message ?? 'unknown error'}]`,
                  streaming: false
                })
                return
              } else if (evt.type === 'delta' && evt.content) {
                accumulatedContent += evt.content
                patchMessage(convId!, assistantMsgId, { content: accumulatedContent })
              } else if (evt.type === 'done' && evt.usage) {
                // Sync real user message ID regardless of whether assistant produced text
                if (evt.user_msg_id && evt.user_msg_id !== userMsg.id) {
                  replaceMessageId(convId!, userMsg.id, evt.user_msg_id)
                }
                // Apply any assistant reactions that came back via react_to_message tool calls
                if (evt.tools_used) {
                  for (const t of evt.tools_used) {
                    if (t.name === 'react_to_message' && t.reaction) {
                      const r = t.reaction
                      const live = useAppStore.getState().messagesByConv[convId!] ?? []
                      patchMessage(convId!, r.message_id, {
                        reactions: [
                          ...(live.find((m) => m.id === r.message_id)?.reactions ?? []),
                          r,
                        ]
                      })
                    }
                  }
                }
                // Empty turn — model only reacted, produced no text; drop the placeholder bubble
                if (evt.empty) {
                  const live = useAppStore.getState().messagesByConv[convId!] ?? []
                  setMessages(convId!, live.filter((m) => m.id !== assistantMsgId))
                  return
                }
                const realAssistantId = evt.assistant_msg_id ?? assistantMsgId
                if (evt.assistant_msg_id && evt.assistant_msg_id !== assistantMsgId) {
                  replaceMessageId(convId!, assistantMsgId, evt.assistant_msg_id)
                  streamingMsgIdRef.current = evt.assistant_msg_id
                }
                patchMessage(convId!, realAssistantId, {
                  streaming: false,
                  model: evt.model,
                  provider: evt.provider,
                  tools_used: evt.tools_used ?? []
                })
                fetch(`${backendUrl}/v1/usage/${convId}`)
                  .then((r) => r.json())
                  .then((data) => {
                    if (data && typeof data.total_cost_usd === 'number') {
                      setConvUsage(convId!, data)
                    }
                  })
                  .catch(console.error)
                // Auto-title: use first 60 chars of first user message
                const msgs = messagesByConv[convId!] ?? []
                const firstUser = msgs.find((m) => m.role === 'user')
                if (firstUser && msgs.filter((m) => m.role === 'user').length === 1) {
                  const title = firstUser.content.slice(0, 60)
                  updateConversation(convId!, { title })
                  fetch(`${backendUrl}/v1/conversations/${convId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title })
                  }).catch(console.error)
                }
              }
            } catch {
              // malformed SSE line — skip
            }
          }
        }
      } catch (err: unknown) {
        if ((err as { name?: string }).name !== 'AbortError') {
          patchMessage(convId!, assistantMsgId, {
            content: '[Error: failed to reach backend]',
            streaming: false
          })
        }
      } finally {
        const finalMsgId = streamingMsgIdRef.current ?? assistantMsgId
        patchMessage(convId!, finalMsgId, { streaming: false })
        setStreaming(false)
        streamingMsgIdRef.current = null
        abortRef.current = null
      }
    },
    [
      activeConvId,
      backendUrl,
      selectedModel,
      systemPrompt,
      modelParams,
      addConversation,
      setActiveConvId,
      setMessages,
      appendMessage,
      patchMessage,
      replaceMessageId,
      messagesByConv,
      setConvUsage,
      updateConversation
    ]
  )

  const handleReaction = useCallback(
    async (msgId: string, emoji: string) => {
      if (!activeConvId) return
      const msgs = messagesByConv[activeConvId] ?? []
      const msg = msgs.find((m) => m.id === msgId)
      if (!msg) return
      const existing = (msg.reactions ?? []).find((r) => r.author === 'user' && r.emoji === emoji)
      if (existing) {
        // Toggle off — optimistic remove
        patchMessage(activeConvId, msgId, {
          reactions: (msg.reactions ?? []).filter((r) => r.id !== existing.id)
        })
        fetch(`${backendUrl}/v1/reactions/${existing.id}`, { method: 'DELETE' }).catch(console.error)
      } else {
        // Add — optimistic insert with temp id
        const tempId = `temp-${Date.now()}`
        const optimistic: Reaction = { id: tempId, message_id: msgId, author: 'user', emoji, created_at: new Date().toISOString() }
        patchMessage(activeConvId, msgId, { reactions: [...(msg.reactions ?? []), optimistic] })
        fetch(`${backendUrl}/v1/reactions/${msgId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ author: 'user', emoji })
        })
          .then((r) => r.json() as Promise<Reaction>)
          .then((real) => {
            // Read live state — the optimistic patch has already updated the store
            const live = useAppStore.getState().messagesByConv[activeConvId] ?? []
            const current = live.find((m) => m.id === msgId)
            patchMessage(activeConvId, msgId, {
              reactions: (current?.reactions ?? []).map((r) => r.id === tempId ? real : r)
            })
          })
          .catch(console.error)
      }
    },
    [activeConvId, backendUrl, messagesByConv, patchMessage]
  )

  const handleDeleteMessage = useCallback(
    (msgId: string) => {
      if (!activeConvId) return
      // Remove from in-memory store immediately
      const current = messagesByConv[activeConvId] ?? []
      setMessages(activeConvId, current.filter((m) => m.id !== msgId))
      // Persist to backend
      fetch(`${backendUrl}/v1/conversations/${activeConvId}/messages/${msgId}`, {
        method: 'DELETE'
      }).catch(console.error)
    },
    [activeConvId, backendUrl, messagesByConv, setMessages]
  )

  const handleRetry = useCallback(
    (text: string) => {
      if (!activeConvId) return
      const current = messagesByConv[activeConvId] ?? []
      // Slice off everything from the last user message onwards so handleSend
      // re-appends exactly one user message and sends the correct trimmed history.
      const lastUserIdx = current.reduce<number>(
        (acc, m, i) => (m.role === 'user' ? i : acc),
        -1
      )
      const trimmed = lastUserIdx !== -1 ? current.slice(0, lastUserIdx) : current
      // Update the store so the UI reflects the trim immediately
      setMessages(activeConvId, trimmed)
      // Pass trimmed list directly — avoids reading stale messagesByConv closure in handleSend
      handleSend(text, true, trimmed)
    },
    [activeConvId, messagesByConv, setMessages, handleSend]
  )

  const messages = (activeConvId ? messagesByConv[activeConvId] : null) ?? []

  return (
    <>
    <SettingsModal />
    <ContextInspector open={inspectorOpen} onClose={() => setInspectorOpen(false)} />
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left sidebar */}
      <div style={{ width: 220, flexShrink: 0, height: '100%', overflow: 'hidden' }}>
        <ConversationList
          onNewConversation={handleNewConversation}
          onSelectConversation={handleSelectConversation}
        />
      </div>

      {/* Main panel */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: 'var(--vscode-bg)'
        }}
      >
        {/* Top bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '4px 12px',
            borderBottom: '1px solid var(--vscode-border)',
            background: 'var(--vscode-surface)',
            flexShrink: 0,
            minHeight: 32
          }}
        >
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, flex: 1 }}>
            {activeConvId
              ? useAppStore.getState().conversations.find((c) => c.id === activeConvId)?.title
              : 'No conversation selected'}
          </Text>
          <Button
            type="text"
            size="small"
            icon={<BugOutlined style={{ fontSize: 13 }} />}
            onClick={() => setInspectorOpen(true)}
            style={{ color: 'var(--vscode-text-muted)', padding: '0 4px' }}
            title="Context Inspector"
          />
          <Button
            type="text"
            size="small"
            icon={<SettingOutlined style={{ fontSize: 13 }} />}
            onClick={() => setSettingsOpen(true)}
            style={{ color: 'var(--vscode-text-muted)', padding: '0 4px' }}
            title="Settings"
          />
          <Button
            type="text"
            size="small"
            icon={<LayoutOutlined style={{ fontSize: 13 }} />}
            onClick={() => setRightPanelVisible(!rightPanelVisible)}
            style={{ color: 'var(--vscode-text-muted)', padding: '0 4px' }}
            title="Toggle right panel"
          />
        </div>

        <ChatThread messages={messages} onRetry={handleRetry} onDeleteMessage={handleDeleteMessage} onReact={handleReaction} retryDisabled={streaming} />
        <MessageComposer
          onSend={handleSend}
          streaming={streaming}
        />
      </div>

      {/* Right panel */}
      {rightPanelVisible && (
        <div style={{ width: 200, flexShrink: 0, height: '100%', overflow: 'hidden' }}>
          <RightPanel />
        </div>
      )}
    </div>
    </>
  )
}
