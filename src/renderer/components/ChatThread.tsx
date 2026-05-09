import React, { useEffect, useRef, useState } from 'react'
import { Button, Tag, Tooltip, Typography } from 'antd'
import { CopyOutlined, DeleteOutlined, RedoOutlined, RobotOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import type { Message, Reaction, WeatherData, WeatherForecastDay } from '@shared/types'

const { Text } = Typography

const EMOJI_PALETTE = ['👍', '❤️', '😂', '😮', '😢', '😡', '🎉', '🤔', '👀', '🙌', '🔥', '✅']

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const WMO_ICON: Record<string, string> = {
  'Clear sky': '☀️', 'Mainly clear': '🌤️', 'Partly cloudy': '⛅', 'Overcast': '☁️',
  'Fog': '🌫️', 'Icy fog': '🌫️',
  'Light drizzle': '🌦️', 'Moderate drizzle': '🌦️', 'Dense drizzle': '🌧️',
  'Slight rain': '🌧️', 'Moderate rain': '🌧️', 'Heavy rain': '🌧️',
  'Slight snow': '🌨️', 'Moderate snow': '🌨️', 'Heavy snow': '❄️', 'Snow grains': '❄️',
  'Slight rain showers': '🌦️', 'Moderate rain showers': '🌧️', 'Violent rain showers': '⛈️',
  'Slight snow showers': '🌨️', 'Heavy snow showers': '❄️',
  'Thunderstorm': '⛈️', 'Thunderstorm with slight hail': '⛈️', 'Thunderstorm with heavy hail': '⛈️',
}

function weatherIcon(condition: string): string {
  return WMO_ICON[condition] ?? '🌡️'
}

function WeatherCard({ weather }: { weather: WeatherData }): React.ReactElement {
  const { location, current, forecast } = weather
  const locationLabel = location.city
    ? `${location.city}${location.region ? ', ' + location.region : ''}`
    : `${location.lat.toFixed(2)}, ${location.lon.toFixed(2)}`

  const maxPrecip = Math.max(...forecast.map(d => d.precipitation_in), 0.01)

  return (
    <div style={{
      background: 'var(--vscode-surface)',
      border: '1px solid var(--vscode-border)',
      borderRadius: 8,
      padding: '10px 12px',
      marginTop: 6,
      width: '100%',
      maxWidth: 480,
    }}>
      {/* Header — current conditions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <Text style={{ color: 'var(--vscode-text)', fontSize: 12, fontWeight: 600, display: 'block' }}>
            {locationLabel}
          </Text>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>
            {current.condition}
          </Text>
        </div>
        <div style={{ textAlign: 'right' }}>
          <Text style={{ color: 'var(--vscode-text)', fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
            {weatherIcon(current.condition)} {Math.round(current.temp_f)}°F
          </Text>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, display: 'block' }}>
            Feels like {Math.round(current.feels_like_f)}°F · {current.humidity_pct}% humidity
          </Text>
        </div>
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px solid var(--vscode-border)', marginBottom: 8 }} />

      {/* 7-day forecast strip */}
      <div style={{ display: 'flex', gap: 4, overflowX: 'auto' }}>
        {forecast.map((day: WeatherForecastDay) => {
          const date = new Date(day.date + 'T12:00:00')
          const label = date.toLocaleDateString([], { weekday: 'short' })
          const precipPct = Math.round((day.precipitation_in / maxPrecip) * 100)
          return (
            <div key={day.date} style={{
              flex: '1 0 52px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 2,
              padding: '4px 2px',
              borderRadius: 4,
              minWidth: 52,
            }}>
              <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10 }}>{label}</Text>
              <span style={{ fontSize: 16, lineHeight: 1.3 }}>{weatherIcon(day.condition)}</span>
              <Text style={{ color: 'var(--vscode-text)', fontSize: 11, fontWeight: 600 }}>
                {Math.round(day.temp_high_f)}°
              </Text>
              <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10 }}>
                {Math.round(day.temp_low_f)}°
              </Text>
              {/* Precipitation bar */}
              <div style={{ width: '100%', height: 3, background: 'var(--vscode-border)', borderRadius: 2, marginTop: 2 }}>
                {precipPct > 0 && (
                  <div style={{
                    width: `${precipPct}%`,
                    height: '100%',
                    background: 'var(--vscode-accent)',
                    borderRadius: 2,
                    opacity: 0.7,
                  }} />
                )}
              </div>
              {day.precipitation_in > 0 && (
                <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 9 }}>
                  {day.precipitation_in.toFixed(2)}"
                </Text>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer — wind */}
      <div style={{ borderTop: '1px solid var(--vscode-border)', marginTop: 8, paddingTop: 6 }}>
        <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 10 }}>
          Wind {current.wind_speed_mph} mph · Cloud cover {current.cloud_cover_pct}% · Pressure {current.pressure_hpa} hPa
        </Text>
      </div>
    </div>
  )
}

// Group reactions by emoji, collecting all reaction objects per emoji
function groupReactions(reactions: Reaction[]): { emoji: string; reactions: Reaction[] }[] {
  const map = new Map<string, Reaction[]>()
  for (const r of reactions) {
    const list = map.get(r.emoji) ?? []
    list.push(r)
    map.set(r.emoji, list)
  }
  return [...map.entries()].map(([emoji, rs]) => ({ emoji, reactions: rs }))
}

interface EmojiPickerProps {
  onPick: (emoji: string) => void
  onClose: () => void
}

function EmojiPicker({ onPick, onClose }: EmojiPickerProps): React.ReactElement {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [onClose])

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        bottom: '100%',
        left: 0,
        zIndex: 100,
        background: 'var(--vscode-surface)',
        border: '1px solid var(--vscode-border)',
        borderRadius: 6,
        padding: '6px 8px',
        display: 'flex',
        flexWrap: 'wrap',
        gap: 4,
        width: 192,
        boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        marginBottom: 4,
      }}
    >
      {EMOJI_PALETTE.map((emoji) => (
        <button
          key={emoji}
          onClick={() => { onPick(emoji); onClose() }}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: 18,
            lineHeight: 1,
            padding: '2px 3px',
            borderRadius: 4,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--vscode-bg)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
        >
          {emoji}
        </button>
      ))}
    </div>
  )
}

interface MessageBubbleProps {
  msg: Message
  isLastUserMsg: boolean
  onRetry?: () => void
  onDelete?: () => void
  onReact?: (emoji: string) => void
  retryDisabled?: boolean
}

function MessageBubble({ msg, isLastUserMsg, onRetry, onDelete, onReact, retryDisabled }: MessageBubbleProps): React.ReactElement {
  const isUser = msg.role === 'user'
  const [pickerOpen, setPickerOpen] = useState(false)
  const groups = groupReactions(msg.reactions ?? [])

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

      {/* Tool use indicators */}
      {!isUser && msg.tools_used && msg.tools_used.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 2 }}>
          {msg.tools_used.map((t, i) => (
            <Tag
              key={i}
              icon={t.name === 'web_search' ? <SearchOutlined style={{ fontSize: 10 }} /> : undefined}
              color="default"
              style={{ fontSize: 10, lineHeight: '16px', padding: '0 6px', margin: 0, color: 'var(--vscode-text-muted)', borderColor: 'var(--vscode-border)' }}
            >
              {t.name === 'web_search'
                ? `Searched: ${t.query}`
                : t.name === 'react_to_message'
                  ? `Reacted ${t.reaction?.emoji ?? ''}`
                  : t.name === 'get_calendar_events' ? '📅 Checked calendar'
                  : t.name === 'create_calendar_event' ? '📅 Created event'
                  : t.name === 'update_calendar_event' ? '📅 Updated event'
                  : t.name === 'delete_calendar_event' ? '📅 Deleted event'
                  : t.name === 'list_calendars' ? '📅 Listed calendars'
                  : t.name === 'get_tasks' ? '✅ Checked tasks'
                  : t.name === 'create_task' ? '✅ Created task'
                  : t.name === 'complete_task' ? '✅ Completed task'
                  : t.name === 'update_task' ? '✅ Updated task'
                  : t.name === 'delete_task' ? '✅ Deleted task'
                  : t.name === 'list_task_lists' ? '✅ Listed task lists'
                  : t.name === 'search_drive' ? '📁 Searched Drive'
                  : t.name === 'get_drive_file' ? '📁 Read file'
                  : t.name}
            </Tag>
          ))}
        </div>
      )}

      {/* Bubble */}
      <div
        style={{
          background: isUser ? 'var(--vscode-accent)' : 'var(--vscode-surface)',
          border: `1px solid ${isUser ? 'transparent' : 'var(--vscode-border)'}`,
          borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
          padding: '8px 12px',
          maxWidth: '100%',
          color: isUser ? '#fff' : 'var(--vscode-text)',
        }}
      >
        <div className={`md-body${isUser ? ' md-body-user' : ''}`}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
          >
            {msg.content}
          </ReactMarkdown>
          {msg.streaming && <span className="streaming-cursor" />}
        </div>
      </div>

      {/* Citation cards */}
      {!isUser && msg.tools_used?.map((t, ti) =>
        t.name === 'web_search' && t.results && t.results.length > 0 ? (
          <div key={ti} style={{ width: '100%', marginTop: 4 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {t.results.map((r, ri) => (
                <a
                  key={ri}
                  href={r.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ textDecoration: 'none', display: 'block', flex: '1 1 200px', maxWidth: 280 }}
                >
                  <div style={{
                    background: 'var(--vscode-surface)',
                    border: '1px solid var(--vscode-border)',
                    borderRadius: 4,
                    padding: '6px 8px',
                    cursor: 'pointer',
                    transition: 'border-color 0.15s',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--vscode-accent)')}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--vscode-border)')}
                  >
                    <Text style={{
                      color: 'var(--vscode-accent)',
                      fontSize: 11,
                      fontWeight: 600,
                      display: 'block',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {r.title || r.url}
                    </Text>
                    <Text style={{
                      color: 'var(--vscode-text-muted)',
                      fontSize: 10,
                      display: 'block',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {(() => { try { return new URL(r.url).hostname.replace(/^www\./, '') } catch { return r.url } })()}
                    </Text>
                  </div>
                </a>
              ))}
            </div>
          </div>
        ) : null
      )}

      {/* Weather card */}
      {!isUser && msg.tools_used?.map((t, ti) =>
        t.name === 'get_weather' && t.weather ? (
          <WeatherCard key={ti} weather={t.weather} />
        ) : null
      )}

      {/* Reaction pills — only shown when there are existing reactions */}
      {groups.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {groups.map(({ emoji, reactions: rs }) => {
            const userReacted = rs.some((r) => r.author === 'user')
            return (
              <button
                key={emoji}
                onClick={() => onReact?.(emoji)}
                style={{
                  background: userReacted ? 'color-mix(in srgb, var(--vscode-accent) 20%, transparent)' : 'var(--vscode-surface)',
                  border: `1px solid ${userReacted ? 'var(--vscode-accent)' : 'var(--vscode-border)'}`,
                  borderRadius: 12,
                  padding: '1px 7px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 13,
                  lineHeight: '20px',
                }}
              >
                <span>{emoji}</span>
                {rs.length > 1 && (
                  <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>{rs.length}</Text>
                )}
              </button>
            )
          })}
        </div>
      )}

      {/* Timestamp + action buttons */}
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
        {!msg.streaming && (
          <Tooltip title="Copy">
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined style={{ fontSize: 11 }} />}
              onClick={() => navigator.clipboard.writeText(msg.content)}
              style={{ color: 'var(--vscode-text-muted)', padding: '0 2px', height: 18 }}
            />
          </Tooltip>
        )}
        {/* React button — inline with other actions, picker opens upward */}
        {onReact && !msg.streaming && (
          <div style={{ position: 'relative' }}>
            {pickerOpen && (
              <EmojiPicker onPick={(e) => { onReact(e); setPickerOpen(false) }} onClose={() => setPickerOpen(false)} />
            )}
            <Tooltip title="Add reaction">
              <Button
                type="text"
                size="small"
                onClick={() => setPickerOpen((v) => !v)}
                style={{ color: 'var(--vscode-text-muted)', padding: '0 2px', height: 18, fontSize: 11 }}
              >
                ☺
              </Button>
            </Tooltip>
          </div>
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
  onReact?: (msgId: string, emoji: string) => void
  retryDisabled?: boolean
}

export default function ChatThread({ messages, onRetry, onDeleteMessage, onReact, retryDisabled }: Props): React.ReactElement {
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
          onReact={onReact ? (emoji) => onReact(msg.id, emoji) : undefined}
          retryDisabled={retryDisabled}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
