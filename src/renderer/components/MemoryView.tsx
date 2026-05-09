import React, { useCallback, useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Space, Switch, Table, Tag, Tooltip, Typography, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, PushpinFilled, PushpinOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { useAppStore } from '../store'

const { Text } = Typography

interface Memory {
  id: string
  subject: string
  predicate: string
  object: string
  source_conv_id: string | null
  pinned: boolean
  expires_at: string | null
  created_at: string
  updated_at: string
}

function ExpiryLabel({ expires_at, pinned }: { expires_at: string | null; pinned: boolean }) {
  if (pinned) return <Tag color="gold" style={{ fontSize: 10, margin: 0 }}>pinned</Tag>
  if (!expires_at) return <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>—</Text>
  const ms = new Date(expires_at).getTime() - Date.now()
  if (ms <= 0) return <Tag color="red" style={{ fontSize: 10, margin: 0 }}>expired</Tag>
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const label = h > 48
    ? `${Math.floor(h / 24)}d`
    : h > 0 ? `${h}h ${m}m` : `${m}m`
  const color = ms < 3600000 ? 'orange' : ms < 86400000 ? 'default' : 'green'
  return <Tag color={color} style={{ fontSize: 10, margin: 0 }}>{label}</Tag>
}

export default function MemoryView(): React.ReactElement {
  const backendUrl = useAppStore((s) => s.backendUrl)

  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Memory | null>(null)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)

  const fetchMemories = useCallback(async (q?: string) => {
    setLoading(true)
    try {
      const url = q?.trim()
        ? `${backendUrl}/v1/memories?q=${encodeURIComponent(q.trim())}`
        : `${backendUrl}/v1/memories`
      const res = await fetch(url)
      setMemories(await res.json())
    } catch {
      message.error('Failed to load memories')
    } finally {
      setLoading(false)
    }
  }, [backendUrl])

  useEffect(() => { fetchMemories() }, [fetchMemories])

  const handleSearch = useCallback(() => fetchMemories(search), [fetchMemories, search])

  const openCreate = useCallback(() => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ ttl_hours: 24, pinned: false })
    setModalOpen(true)
  }, [form])

  const openEdit = useCallback((mem: Memory) => {
    setEditing(mem)
    form.setFieldsValue({
      subject: mem.subject,
      predicate: mem.predicate,
      object: mem.object,
      pinned: mem.pinned,
      ttl_hours: mem.pinned || !mem.expires_at ? null : Math.ceil((new Date(mem.expires_at).getTime() - Date.now()) / 3600000),
    })
    setModalOpen(true)
  }, [form])

  const handleSave = useCallback(async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      if (editing) {
        await fetch(`${backendUrl}/v1/memories/${editing.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(values),
        })
        message.success('Memory updated')
      } else {
        await fetch(`${backendUrl}/v1/memories`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(values),
        })
        message.success('Memory stored')
      }
      setModalOpen(false)
      fetchMemories(search || undefined)
    } catch {
      message.error('Failed to save memory')
    } finally {
      setSaving(false)
    }
  }, [backendUrl, editing, form, fetchMemories, search])

  const handleTogglePin = useCallback(async (mem: Memory) => {
    try {
      const res = await fetch(`${backendUrl}/v1/memories/${mem.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: !mem.pinned }),
      })
      const updated: Memory = await res.json()
      setMemories((prev) => prev.map((m) => m.id === updated.id ? updated : m))
    } catch {
      message.error('Failed to update pin')
    }
  }, [backendUrl])

  const handleDelete = useCallback(async (id: string) => {
    try {
      await fetch(`${backendUrl}/v1/memories/${id}`, { method: 'DELETE' })
      setMemories((prev) => prev.filter((m) => m.id !== id))
      message.success('Memory deleted')
    } catch {
      message.error('Failed to delete memory')
    }
  }, [backendUrl])

  const pinnedWatch = Form.useWatch('pinned', form)

  const columns = [
    {
      title: '',
      key: 'pin',
      width: 28,
      render: (_: unknown, record: Memory) => (
        <Tooltip title={record.pinned ? 'Unpin' : 'Pin permanently'}>
          <Button
            type="text"
            size="small"
            icon={record.pinned
              ? <PushpinFilled style={{ fontSize: 12, color: '#faad14' }} />
              : <PushpinOutlined style={{ fontSize: 12, color: 'var(--vscode-text-muted)' }} />}
            onClick={() => handleTogglePin(record)}
            style={{ padding: '0 2px' }}
          />
        </Tooltip>
      ),
    },
    {
      title: 'Subject',
      dataIndex: 'subject',
      key: 'subject',
      width: 110,
      render: (v: string) => <Tag color="blue" style={{ fontFamily: 'monospace', fontSize: 11 }}>{v}</Tag>,
    },
    {
      title: 'Predicate',
      dataIndex: 'predicate',
      key: 'predicate',
      width: 150,
      render: (v: string) => <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, fontStyle: 'italic' }}>{v}</Text>,
    },
    {
      title: 'Object',
      dataIndex: 'object',
      key: 'object',
      render: (v: string) => <Text style={{ color: 'var(--vscode-text)', fontSize: 12 }}>{v}</Text>,
    },
    {
      title: 'Expires',
      key: 'expires',
      width: 80,
      render: (_: unknown, record: Memory) => <ExpiryLabel expires_at={record.expires_at} pinned={record.pinned} />,
    },
    {
      title: '',
      key: 'actions',
      width: 64,
      render: (_: unknown, record: Memory) => (
        <Space size={2}>
          <Button
            type="text" size="small"
            icon={<EditOutlined style={{ fontSize: 12 }} />}
            onClick={() => openEdit(record)}
            style={{ color: 'var(--vscode-text-muted)', padding: '0 4px' }}
          />
          <Popconfirm
            title="Delete this memory?"
            onConfirm={() => handleDelete(record.id)}
            okText="Delete" okButtonProps={{ danger: true }}
          >
            <Button type="text" size="small" danger
              icon={<DeleteOutlined style={{ fontSize: 12 }} />}
              style={{ padding: '0 4px' }}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const pinned = memories.filter((m) => m.pinned).length
  const expiring = memories.filter((m) => !m.pinned && m.expires_at && new Date(m.expires_at).getTime() - Date.now() < 3600000 * 4).length

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexShrink: 0 }}>
        <Input
          placeholder="Semantic search…"
          prefix={<SearchOutlined style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onPressEnter={handleSearch}
          allowClear
          onClear={() => { setSearch(''); fetchMemories() }}
          style={{ flex: 1, maxWidth: 320 }}
          size="small"
        />
        <Button size="small" icon={<SearchOutlined />} onClick={handleSearch}>Search</Button>
        <Button size="small" icon={<ReloadOutlined />} onClick={() => { setSearch(''); fetchMemories() }}>All</Button>
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={openCreate} style={{ marginLeft: 'auto' }}>
          New Memory
        </Button>
      </div>

      {/* Summary row */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 8, flexShrink: 0, alignItems: 'center' }}>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>
          {memories.length} {memories.length === 1 ? 'memory' : 'memories'}
          {search ? ` matching "${search}"` : ''}
        </Text>
        {pinned > 0 && <Tag color="gold" style={{ fontSize: 11 }}>★ {pinned} pinned</Tag>}
        {expiring > 0 && <Tag color="orange" style={{ fontSize: 11 }}>{expiring} expiring soon</Tag>}
      </div>

      {/* Table */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <Table
          dataSource={memories}
          columns={columns}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={false}
          rowClassName={(record) => record.pinned ? 'memory-row-pinned' : ''}
          locale={{ emptyText: search ? 'No memories match that search.' : 'No memories yet — Mara will add them as she learns.' }}
        />
      </div>

      {/* Create / Edit modal */}
      <Modal
        title={editing ? 'Edit Memory' : 'New Memory'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        okText={editing ? 'Save' : 'Store'}
        width={480}
        styles={{
          content: { background: 'var(--vscode-surface)' },
          header: { background: 'var(--vscode-surface)' },
          footer: { background: 'var(--vscode-surface)' },
        }}
      >
        <Form form={form} layout="vertical" size="small" style={{ marginTop: 12 }}>
          <Form.Item name="subject" label="Subject" rules={[{ required: true, message: 'Required' }]}
            extra={<Text style={{ fontSize: 11, color: 'var(--vscode-text-muted)' }}>e.g. "user", "project", "session"</Text>}>
            <Input placeholder="user" />
          </Form.Item>
          <Form.Item name="predicate" label="Predicate" rules={[{ required: true, message: 'Required' }]}
            extra={<Text style={{ fontSize: 11, color: 'var(--vscode-text-muted)' }}>e.g. "prefers", "is working on", "name"</Text>}>
            <Input placeholder="prefers" />
          </Form.Item>
          <Form.Item name="object" label="Object" rules={[{ required: true, message: 'Required' }]}>
            <Input.TextArea placeholder="concise bullet-point answers" autoSize={{ minRows: 2, maxRows: 5 }} />
          </Form.Item>
          <Form.Item name="pinned" label="Pin permanently" valuePropName="checked">
            <Switch size="small" />
          </Form.Item>
          {!pinnedWatch && (
            <Form.Item name="ttl_hours" label="Expires after (hours)"
              extra={<Text style={{ fontSize: 11, color: 'var(--vscode-text-muted)' }}>Leave blank for no expiry</Text>}>
              <InputNumber min={0.5} max={8760} step={1} placeholder="24" style={{ width: '100%' }} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}
