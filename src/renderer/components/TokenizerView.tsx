import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Tag, Typography } from 'antd'
import { useAppStore } from '../store'

const { Text } = Typography

interface TokenizerInfo {
  model: string
  version: string
  vocab_size: number
  num_special_tokens: number
  bos_id: number
  eos_id: number
}

interface TokenizeResult {
  token_count: number
  token_ids: number[]
  token_strings: string[]
  special_flags: boolean[]
  decoded_text: string
  round_trip_match: boolean
}

// Cycle through a set of muted token colours so adjacent tokens are visually distinct
const TOKEN_COLORS = ['#1f3a5f', '#2d4a1e', '#4a1e2d', '#2d3a4a', '#3a2d1e', '#1e3a3a', '#3a1e3a']

function TokenBox({ text, id, isSpecial, colorIdx }: { text: string; id: number; isSpecial: boolean; colorIdx: number }) {
  const visible = text
    .replace(/ /g, '·')
    .replace(/\n/g, '↵')
    .replace(/\t/g, '→')

  return (
    <span
      title={`id: ${id}  raw: ${JSON.stringify(text)}`}
      style={{
        display: 'inline-block',
        padding: '2px 5px',
        margin: '2px 2px',
        borderRadius: 3,
        fontSize: 12,
        fontFamily: 'monospace',
        lineHeight: '18px',
        background: isSpecial ? '#312e81' : TOKEN_COLORS[colorIdx % TOKEN_COLORS.length],
        border: `1px solid ${isSpecial ? '#6366f1' : 'var(--vscode-border)'}`,
        color: isSpecial ? '#c7d2fe' : 'var(--vscode-text)',
        cursor: 'default',
        userSelect: 'none',
        whiteSpace: 'pre',
      }}
    >
      {visible || '∅'}
    </span>
  )
}

export default function TokenizerView(): React.ReactElement {
  const backendUrl = useAppStore((s) => s.backendUrl)

  const [info, setInfo] = useState<TokenizerInfo | null>(null)
  const [text, setText] = useState('')
  const [result, setResult] = useState<TokenizeResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    fetch(`${backendUrl}/v1/tokenizer/info`)
      .then((r) => r.json())
      .then(setInfo)
      .catch(() => setError('Could not reach backend'))
  }, [backendUrl])

  const tokenize = useCallback(async (input: string) => {
    if (!input.trim()) { setResult(null); return }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${backendUrl}/v1/tokenizer/tokenize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: input }),
      })
      setResult(await res.json())
    } catch {
      setError('Tokenization failed')
    } finally {
      setLoading(false)
    }
  }, [backendUrl])

  // Debounced auto-tokenize on input
  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value
    setText(v)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => tokenize(v), 300)
  }, [tokenize])

  const label = (s: string) => (
    <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, display: 'block', marginBottom: 6 }}>
      {s}
    </Text>
  )

  const panel = (children: React.ReactNode) => (
    <div style={{ background: 'var(--vscode-surface)', border: '1px solid var(--vscode-border)', borderRadius: 4, padding: '10px 12px', marginBottom: 14 }}>
      {children}
    </div>
  )

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 0 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexShrink: 0 }}>
        <Text style={{ color: 'var(--vscode-text)', fontSize: 14, fontWeight: 600 }}>Tokenizer</Text>
        {info && (
          <>
            <Tag color="blue" style={{ fontFamily: 'monospace', fontSize: 11 }}>{info.model}</Tag>
            <Tag color="default" style={{ fontSize: 11 }}>{info.version}</Tag>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>
              vocab {info.vocab_size.toLocaleString()} · {info.num_special_tokens} special tokens
            </Text>
          </>
        )}
        {result && (
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Tag color="green" style={{ fontSize: 12, padding: '0 8px', lineHeight: '22px' }}>
              {result.token_count} token{result.token_count !== 1 ? 's' : ''}
            </Tag>
            <Tag
              color={result.round_trip_match ? 'success' : 'error'}
              style={{ fontSize: 11 }}
            >
              {result.round_trip_match ? 'round-trip ✓' : 'round-trip mismatch'}
            </Tag>
            {loading && <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>…</Text>}
          </div>
        )}
      </div>

      {error && (
        <div style={{ color: 'var(--vscode-error)', fontSize: 12, marginBottom: 12 }}>{error}</div>
      )}

      {/* Input */}
      <div style={{ marginBottom: 14, flexShrink: 0 }}>
        {label('Input')}
        <textarea
          value={text}
          onChange={handleChange}
          placeholder="Type or paste text to tokenize…"
          rows={5}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            resize: 'vertical',
            background: 'var(--vscode-bg)',
            color: 'var(--vscode-text)',
            border: '1px solid var(--vscode-border)',
            borderRadius: 3,
            padding: '8px 10px',
            fontSize: 13,
            fontFamily: 'monospace',
            lineHeight: '1.5',
            outline: 'none',
          }}
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
          <Button size="small" onClick={() => tokenize(text)} loading={loading}>Tokenize</Button>
          <Button size="small" onClick={() => { setText(''); setResult(null) }}>Clear</Button>
        </div>
      </div>

      {result && (
        <>
          {/* Token visualisation */}
          <div style={{ marginBottom: 14, flexShrink: 0 }}>
            {label('Token visualisation  (hover for id + raw)')}
            {panel(
              <div style={{ lineHeight: '28px' }}>
                {result.token_strings.map((s, i) => (
                  <TokenBox
                    key={i}
                    text={s}
                    id={result.token_ids[i]}
                    isSpecial={result.special_flags[i]}
                    colorIdx={i}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Reconstructed text */}
          <div style={{ marginBottom: 14, flexShrink: 0 }}>
            {label('Reconstructed text (decoded)')}
            {panel(
              <pre style={{ margin: 0, color: 'var(--vscode-text)', fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {result.decoded_text}
              </pre>
            )}
          </div>

          {/* Token details table */}
          <div style={{ marginBottom: 14 }}>
            {label(`Token details (${result.token_count})`)}
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12, fontFamily: 'monospace' }}>
                <thead>
                  <tr>
                    {['#', 'ID', 'Piece', 'Special'].map((h) => (
                      <th key={h} style={{ textAlign: 'left', padding: '4px 10px', borderBottom: '1px solid var(--vscode-border)', color: 'var(--vscode-text-muted)', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.token_ids.map((id, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--vscode-border)' }}>
                      <td style={{ padding: '3px 10px', color: 'var(--vscode-text-muted)' }}>{i}</td>
                      <td style={{ padding: '3px 10px', color: 'var(--vscode-accent)' }}>{id}</td>
                      <td style={{ padding: '3px 10px', color: 'var(--vscode-text)' }}>
                        {JSON.stringify(result.token_strings[i])}
                      </td>
                      <td style={{ padding: '3px 10px' }}>
                        {result.special_flags[i] && <Tag color="purple" style={{ fontSize: 10, margin: 0 }}>special</Tag>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
