import React, { useEffect, useRef } from 'react'
import { App as AntApp, ConfigProvider, Tabs, notification, theme } from 'antd'
import { ApiOutlined, DatabaseOutlined, MessageOutlined, ExperimentOutlined } from '@ant-design/icons'
import ChatView from './components/ChatView'
import DiagnosticDashboard from './components/DiagnosticDashboard'
import MemoryView from './components/MemoryView'
import TokenizerView from './components/TokenizerView'
import { useAppStore } from './store'
import './styles/index.css'

const antdTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorBgBase: '#1e1e1e',
    colorBgContainer: '#252526',
    colorBgElevated: '#2d2d2d',
    colorBorder: '#3c3c3c',
    colorText: '#d4d4d4',
    colorTextSecondary: '#858585',
    colorPrimary: '#007acc',
    colorSuccess: '#4ec9b0',
    colorWarning: '#dcdcaa',
    colorError: '#f44747',
    borderRadius: 2,
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif",
    fontSize: 13,
    controlHeight: 28,
    lineWidth: 1
  },
  components: {
    Input: {
      colorBgContainer: '#3c3c3c',
      colorBorder: '#555555'
    },
    Select: {
      colorBgContainer: '#3c3c3c',
      colorBgElevated: '#252526',
      colorBorder: '#555555'
    },
    Button: {
      colorBgContainer: '#3c3c3c',
      colorBorder: '#555555'
    },
    Card: {
      colorBgContainer: '#252526',
      colorBorderSecondary: '#3c3c3c'
    }
  }
}

function NotificationListener(): React.ReactElement {
  const backendUrl = useAppStore((s) => s.backendUrl)
  const activeConvId = useAppStore((s) => s.activeConvId)
  const appendMessage = useAppStore((s) => s.appendMessage)
  const addConversation = useAppStore((s) => s.addConversation)
  const setActiveConvId = useAppStore((s) => s.setActiveConvId)
  const setMessages = useAppStore((s) => s.setMessages)
  const selectedModel = useAppStore((s) => s.selectedModel)
  const [api, contextHolder] = notification.useNotification()
  const esRef = useRef<EventSource | null>(null)
  // Refs so the onmessage closure always sees latest values without reconnecting
  const activeConvIdRef = useRef(activeConvId)
  const selectedModelRef = useRef(selectedModel)
  activeConvIdRef.current = activeConvId
  selectedModelRef.current = selectedModel

  useEffect(() => {
    if (!backendUrl) return
    if (esRef.current) esRef.current.close()
    const es = new EventSource(`${backendUrl}/v1/notifications`)
    esRef.current = es

    es.onmessage = async (evt) => {
      try {
        const data = JSON.parse(evt.data)
        if (data.type !== 'event') return

        // Resolve or create the target conversation
        let convId = activeConvIdRef.current
        if (!convId) {
          try {
            const res = await fetch(`${backendUrl}/v1/conversations`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ title: data.title, model: selectedModelRef.current }),
            })
            const conv = await res.json()
            addConversation(conv)
            setActiveConvId(conv.id)
            setMessages(conv.id, [])
            convId = conv.id
          } catch {
            return
          }
        }

        let result: { assistant_message: { id: string; role: string; content: string; conversation_id: string; model: string } }
        try {
          const res = await fetch(`${backendUrl}/v1/events/handle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              conversation_id: convId,
              watcher_name: data.watcher_name,
              title: data.title,
              body: data.body,
            }),
          })
          if (!res.ok) return
          result = await res.json()
        } catch {
          return
        }

        appendMessage(convId!, {
          id: result.assistant_message.id,
          conversation_id: convId!,
          role: 'assistant',
          content: result.assistant_message.content,
          model: result.assistant_message.model,
          timestamp: new Date().toISOString(),
          reactions: [],
        })

        api.info({
          message: data.title,
          description: result.assistant_message.content.slice(0, 200),
          placement: 'bottomRight',
          duration: 10,
        })
      } catch {
        // malformed payload — ignore
      }
    }

    return () => { es.close(); esRef.current = null }
  }, [backendUrl, api, appendMessage, addConversation, setActiveConvId, setMessages])

  return <>{contextHolder}</>
}

export default function App(): React.ReactElement {
  const setBackendUrl = useAppStore((s) => s.setBackendUrl)

  useEffect(() => {
    window.electronAPI.getBackendUrl().then(setBackendUrl).catch(console.error)
  }, [setBackendUrl])

  return (
    <ConfigProvider theme={antdTheme}>
      <AntApp>
      <NotificationListener />
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden', background: 'var(--vscode-bg)' }}>
        <Tabs
          defaultActiveKey="chat"
          type="card"
          size="small"
          style={{ flex: 1, minHeight: 0 }}
          tabBarStyle={{
            margin: 0,
            padding: '4px 8px 0',
            background: 'var(--vscode-titlebar)',
            borderBottom: '1px solid var(--vscode-border)',
            flexShrink: 0
          }}
          items={[
            {
              key: 'chat',
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <MessageOutlined style={{ fontSize: 13 }} />
                  Chat
                </span>
              ),
              children: <ChatView />
            },
            {
              key: 'memory',
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <DatabaseOutlined style={{ fontSize: 13 }} />
                  Memory
                </span>
              ),
              children: <MemoryView />
            },
            {
              key: 'tokenizer',
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <ExperimentOutlined style={{ fontSize: 13 }} />
                  Tokenizer
                </span>
              ),
              children: <TokenizerView />
            },
            {
              key: 'diagnostics',
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <ApiOutlined style={{ fontSize: 13 }} />
                  Diagnostics
                </span>
              ),
              children: <DiagnosticDashboard />
            }
          ]}
        />
      </div>
      </AntApp>
    </ConfigProvider>
  )
}
