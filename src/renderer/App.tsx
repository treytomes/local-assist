import React, { useEffect } from 'react'
import { ConfigProvider, theme } from 'antd'
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
      <DiagnosticDashboard />
    </ConfigProvider>
  )
}
