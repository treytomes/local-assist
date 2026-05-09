import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, InputNumber, Table, Tag, Typography } from 'antd'
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useAppStore } from '../store'

const { Text } = Typography

interface DailyRow {
  day: string
  provider: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_cost: number
}

interface ModelRow {
  provider: string
  model: string
  conversations: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cost: number
  avg_cost_per_call: number
}

function fmt(usd: number): string {
  if (usd === 0) return '$0.00'
  if (usd < 0.0001) return `$${usd.toFixed(6)}`
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(3)}`
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

const SECTION_LABEL: React.CSSProperties = {
  color: 'var(--vscode-text-muted)',
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  fontWeight: 600,
  display: 'block',
  marginBottom: 8,
}

function toDailyChart(rows: DailyRow[]): { day: string; cost: number }[] {
  const byDay: Record<string, number> = {}
  for (const r of rows) {
    byDay[r.day] = (byDay[r.day] ?? 0) + r.total_cost
  }
  return Object.entries(byDay)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, cost]) => ({ day: day.slice(5), cost: +cost.toFixed(6) }))
}

function exportCsv(models: ModelRow[], daily: DailyRow[]): void {
  const modelHeader = 'provider,model,conversations,prompt_tokens,completion_tokens,total_cost_usd,avg_cost_per_call_usd'
  const modelRows = models.map((r) =>
    [r.provider, r.model, r.conversations, r.total_prompt_tokens, r.total_completion_tokens,
      r.total_cost.toFixed(6), r.avg_cost_per_call.toFixed(6)].join(',')
  )
  const dailyHeader = 'day,provider,model,prompt_tokens,completion_tokens,total_cost_usd'
  const dailyRows = daily.map((r) =>
    [r.day, r.provider, r.model, r.prompt_tokens, r.completion_tokens, r.total_cost.toFixed(6)].join(',')
  )
  const csv = [
    '# By model (all time)', modelHeader, ...modelRows,
    '', '# Daily (selected window)', dailyHeader, ...dailyRows,
  ].join('\n')

  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `local-assist-usage-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function CostDashboard(): React.ReactElement {
  const backendUrl = useAppStore((s) => s.backendUrl)
  const costAlertThreshold = useAppStore((s) => s.costAlertThreshold)
  const setCostAlertThreshold = useAppStore((s) => s.setCostAlertThreshold)

  const [daily, setDaily] = useState<DailyRow[]>([])
  const [models, setModels] = useState<ModelRow[]>([])
  const [loading, setLoading] = useState(false)
  const [days, setDays] = useState(30)
  const [editingThreshold, setEditingThreshold] = useState(false)
  const [thresholdDraft, setThresholdDraft] = useState<number | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${backendUrl}/v1/usage?days=${days}`)
      const data = await res.json()
      setDaily(data.daily ?? [])
      setModels(data.by_model ?? [])
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [backendUrl, days])

  useEffect(() => { fetchData() }, [fetchData])

  const chartData = toDailyChart(daily)
  const totalCost = models.reduce((s, r) => s + r.total_cost, 0)
  const totalTokens = models.reduce((s, r) => s + r.total_prompt_tokens + r.total_completion_tokens, 0)
  const overThreshold = costAlertThreshold !== null && totalCost >= costAlertThreshold

  const modelColumns = [
    {
      title: 'Model',
      dataIndex: 'model',
      key: 'model',
      render: (v: string, row: ModelRow) => (
        <span>
          <Tag color={row.provider === 'azure' ? 'blue' : 'green'} style={{ fontSize: 10, margin: '0 4px 0 0' }}>
            {row.provider}
          </Tag>
          <Text style={{ color: 'var(--vscode-text)', fontSize: 12, fontFamily: 'monospace' }}>{v}</Text>
        </span>
      ),
    },
    {
      title: 'Convs',
      dataIndex: 'conversations',
      key: 'conversations',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>{v}</Text>,
    },
    {
      title: 'Tokens in',
      dataIndex: 'total_prompt_tokens',
      key: 'prompt',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>{fmtTokens(v)}</Text>,
    },
    {
      title: 'Tokens out',
      dataIndex: 'total_completion_tokens',
      key: 'completion',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>{fmtTokens(v)}</Text>,
    },
    {
      title: 'Total cost',
      dataIndex: 'total_cost',
      key: 'total_cost',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: 'var(--vscode-text)', fontSize: 12, fontFamily: 'monospace' }}>{fmt(v)}</Text>,
    },
    {
      title: 'Avg / call',
      dataIndex: 'avg_cost_per_call',
      key: 'avg',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, fontFamily: 'monospace' }}>{fmt(v)}</Text>,
    },
  ]

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Alert banner */}
      {overThreshold && (
        <Alert
          type="warning"
          showIcon
          message={`Spend threshold reached: ${fmt(totalCost)} of ${fmt(costAlertThreshold!)} limit (all time)`}
          style={{ flexShrink: 0 }}
        />
      )}

      {/* Summary strip */}
      <div style={{ display: 'flex', gap: 24, flexShrink: 0, flexWrap: 'wrap', alignItems: 'center' }}>
        {[
          { label: 'Total spend', value: fmt(totalCost) },
          { label: 'Total tokens', value: fmtTokens(totalTokens) },
          { label: 'Models used', value: String(models.length) },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: 'var(--vscode-surface)', border: '1px solid var(--vscode-border)', borderRadius: 4, padding: '8px 16px', minWidth: 110 }}>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block' }}>{label}</Text>
            <Text style={{ color: 'var(--vscode-text)', fontSize: 18, fontFamily: 'monospace', fontWeight: 600 }}>{value}</Text>
          </div>
        ))}

        {/* Alert threshold config */}
        <div style={{ background: 'var(--vscode-surface)', border: `1px solid ${overThreshold ? 'var(--vscode-warning)' : 'var(--vscode-border)'}`, borderRadius: 4, padding: '8px 16px', minWidth: 110 }}>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block' }}>Alert at</Text>
          {editingThreshold ? (
            <InputNumber
              size="small"
              min={0}
              step={0.01}
              precision={2}
              value={thresholdDraft ?? undefined}
              placeholder="disabled"
              prefix="$"
              autoFocus
              style={{ width: 90, fontSize: 13 }}
              onChange={(v) => setThresholdDraft(v)}
              onBlur={() => {
                setCostAlertThreshold(thresholdDraft)
                setEditingThreshold(false)
              }}
              onPressEnter={() => {
                setCostAlertThreshold(thresholdDraft)
                setEditingThreshold(false)
              }}
            />
          ) : (
            <Text
              onClick={() => { setThresholdDraft(costAlertThreshold); setEditingThreshold(true) }}
              style={{ color: costAlertThreshold !== null ? 'var(--vscode-text)' : 'var(--vscode-text-muted)', fontSize: 18, fontFamily: 'monospace', fontWeight: 600, cursor: 'pointer', textDecoration: 'underline dotted' }}
            >
              {costAlertThreshold !== null ? fmt(costAlertThreshold) : '—'}
            </Text>
          )}
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {[7, 30, 90].map(d => (
            <Button
              key={d}
              size="small"
              type={days === d ? 'primary' : 'default'}
              onClick={() => setDays(d)}
              style={{ fontSize: 11, padding: '0 8px' }}
            >
              {d}d
            </Button>
          ))}
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={fetchData} />
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => exportCsv(models, daily)}
            disabled={models.length === 0}
            title="Export as CSV"
          />
        </div>
      </div>

      {/* Daily spend chart */}
      <div style={{ flexShrink: 0 }}>
        <Text style={SECTION_LABEL}>Daily spend — last {days} days</Text>
        {chartData.length === 0 ? (
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>No usage data yet.</Text>
        ) : (
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--vscode-accent)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--vscode-accent)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--vscode-border)" vertical={false} />
              <XAxis
                dataKey="day"
                tick={{ fill: 'var(--vscode-text-muted)', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: 'var(--vscode-text-muted)', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => v === 0 ? '$0' : `$${v.toFixed(3)}`}
                width={52}
              />
              <Tooltip
                contentStyle={{ background: 'var(--vscode-surface)', border: '1px solid var(--vscode-border)', borderRadius: 4, fontSize: 12 }}
                labelStyle={{ color: 'var(--vscode-text-muted)' }}
                formatter={(v: number) => [fmt(v), 'Cost']}
              />
              <Area
                type="monotone"
                dataKey="cost"
                stroke="var(--vscode-accent)"
                strokeWidth={2}
                fill="url(#costGrad)"
                dot={false}
                activeDot={{ r: 3, fill: 'var(--vscode-accent)' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Model breakdown table */}
      <div>
        <Text style={SECTION_LABEL}>By model (all time)</Text>
        <Table
          dataSource={models}
          columns={modelColumns}
          rowKey={(r) => `${r.provider}/${r.model}`}
          size="small"
          pagination={false}
          locale={{ emptyText: <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>No usage recorded yet.</Text> }}
          style={{ fontSize: 12 }}
        />
      </div>
    </div>
  )
}
