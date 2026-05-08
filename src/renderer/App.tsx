import React, { useEffect } from 'react'
import { ConfigProvider, Tabs, theme } from 'antd'
import { ApiOutlined, MessageOutlined } from '@ant-design/icons'
import ChatView from './components/ChatView'
import DiagnosticDashboard from './components/DiagnosticDashboard'
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

export default function App(): React.ReactElement {
  const setBackendUrl = useAppStore((s) => s.setBackendUrl)

  useEffect(() => {
    window.electronAPI.getBackendUrl().then(setBackendUrl).catch(console.error)
  }, [setBackendUrl])

  return (
    <ConfigProvider theme={antdTheme}>
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
    </ConfigProvider>
  )
}
