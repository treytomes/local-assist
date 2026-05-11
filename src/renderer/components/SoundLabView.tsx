import React, { useEffect, useRef, useState } from 'react'
import { Button, Select, Slider, Space, Tag, Tooltip, Typography } from 'antd'
import {
  AudioOutlined,
  CaretDownOutlined,
  CaretRightOutlined,
  LoadingOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RedoOutlined,
  SoundOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useAppStore } from '../store'
import { play as bfxrPlay, DEFAULT_PARAMS, getSharedAudioContext } from '../bfxr'
import type { BfxrParams, WaveType } from '../bfxr'
import { SOUND_PRESETS } from '../soundPresets'

const { Text, Title } = Typography

// ── TTS Panel ──────────────────────────────────────────────────────────────

function TtsPanel({ backendUrl }: { backendUrl: string }): React.ReactElement {
  const ttsVoice = useAppStore((s) => s.ttsVoice)
  const ttsSpeed = useAppStore((s) => s.ttsSpeed)
  const setTtsVoice = useAppStore((s) => s.setTtsVoice)
  const setTtsSpeed = useAppStore((s) => s.setTtsSpeed)
  const speechProvider = useAppStore((s) => s.speechProvider)
  const [voices, setVoices] = useState<string[]>([])
  const [voice, setVoice] = useState(ttsVoice)
  const [speed, setSpeed] = useState(ttsSpeed)
  const [text, setText] = useState('Hello! My name is Mara. How can I help you today?')
  const [loading, setLoading] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const prevUrlRef = useRef<string | null>(null)

  // Speed range differs by provider
  const speedMin = speechProvider === 'local' ? 0.5 : 0.25
  const speedMax = speechProvider === 'local' ? 2.0 : 4.0

  // Re-fetch voices whenever provider changes; reset to first valid voice
  useEffect(() => {
    fetch(`${backendUrl}/v1/audio/voices`)
      .then((r) => r.json())
      .then((d) => {
        const list: string[] = d.voices ?? []
        setVoices(list)
        // If current voice isn't valid for new provider, switch to first available
        setVoice((prev) => {
          const next = list.includes(prev) ? prev : (list[0] ?? prev)
          setTtsVoice(next)
          return next
        })
        // Clamp speed into new range
        setSpeed((prev) => {
          const clamped = Math.max(speechProvider === 'local' ? 0.5 : 0.25,
                                   Math.min(speechProvider === 'local' ? 2.0 : 4.0, prev))
          if (clamped !== prev) setTtsSpeed(clamped)
          return clamped
        })
      })
      .catch(() => {})
  }, [backendUrl, speechProvider, setTtsVoice, setTtsSpeed])

  async function handleSynthesize(): Promise<void> {
    if (!text.trim()) return
    setLoading(true)
    try {
      const res = await fetch(`${backendUrl}/v1/audio/speech`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice, speed }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      setAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return url
      })
      setPlaying(false)
    } catch (e) {
      console.error('TTS error', e)
    } finally {
      setLoading(false)
    }
  }

  // Auto-play when a new URL arrives
  useEffect(() => {
    if (!audioUrl || audioUrl === prevUrlRef.current) return
    prevUrlRef.current = audioUrl
    const el = audioRef.current
    if (!el) return
    el.load()
    el.play().then(() => setPlaying(true)).catch(() => {})
  }, [audioUrl])

  function handleStop(): void {
    const el = audioRef.current
    if (!el) return
    el.pause()
    el.currentTime = 0
    setPlaying(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 580 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Title level={5} style={{ color: 'var(--vscode-text)', margin: 0 }}>Text-to-Speech</Title>
        <Tag color={speechProvider === 'local' ? 'green' : 'blue'} style={{ fontSize: 11, margin: 0 }}>
          {speechProvider === 'local' ? 'Kokoro' : 'Azure'}
        </Tag>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        style={{
          width: '100%',
          fontFamily: 'monospace',
          fontSize: 13,
          padding: '8px 10px',
          background: 'var(--vscode-bg)',
          color: 'var(--vscode-text)',
          border: '1px solid var(--vscode-border)',
          borderRadius: 4,
          resize: 'vertical',
          boxSizing: 'border-box',
        }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>Voice</Text>
          <Select
            value={voice}
            onChange={(v) => { setVoice(v); setTtsVoice(v) }}
            size="small"
            style={{ width: 120 }}
            options={voices.map((v) => ({ label: v, value: v }))}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 160 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11 }}>Speed</Text>
            <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, fontFamily: 'monospace' }}>{speed.toFixed(2)}×</Text>
          </div>
          <Slider
            min={speedMin} max={speedMax} step={0.05}
            value={speed}
            onChange={(v) => { setSpeed(v); setTtsSpeed(v) }}
            style={{ margin: '4px 0 0' }}
            styles={{ track: { background: 'var(--vscode-accent)' } }}
          />
        </div>

        <Space style={{ marginTop: 16 }}>
          <Button
            type="primary"
            icon={loading ? <LoadingOutlined /> : <PlayCircleOutlined />}
            onClick={handleSynthesize}
            loading={loading}
            disabled={!text.trim()}
          >
            Synthesize
          </Button>
          {audioUrl && !playing && (
            <Button icon={<PlayCircleOutlined />} onClick={() => audioRef.current?.play()}>Play</Button>
          )}
          {playing && (
            <Button icon={<StopOutlined />} onClick={handleStop} danger>Stop</Button>
          )}
        </Space>
      </div>

      <audio
        ref={audioRef}
        controls
        src={audioUrl ?? undefined}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        style={{ width: '100%', marginTop: 4, display: audioUrl ? 'block' : 'none' }}
      />
    </div>
  )
}

// ── STT Panel ──────────────────────────────────────────────────────────────

type RecordState = 'idle' | 'recording' | 'transcribing'

function SttPanel({ backendUrl }: { backendUrl: string }): React.ReactElement {
  const [state, setState] = useState<RecordState>('idle')
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState('')
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  async function startRecording(): Promise<void> {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        await transcribeBlob(blob)
      }
      recorder.start()
      mediaRef.current = recorder
      setState('recording')
    } catch (e) {
      setError('Microphone access denied or unavailable.')
    }
  }

  function stopRecording(): void {
    mediaRef.current?.stop()
    setState('transcribing')
  }

  async function transcribeBlob(blob: Blob): Promise<void> {
    try {
      const form = new FormData()
      form.append('file', blob, 'audio.webm')
      const res = await fetch(`${backendUrl}/v1/audio/transcriptions`, {
        method: 'POST',
        body: form,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setTranscript(data.text ?? '')
    } catch (e) {
      setError(`Transcription failed: ${e}`)
    } finally {
      setState('idle')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 580 }}>
      <Title level={5} style={{ color: 'var(--vscode-text)', margin: 0 }}>Speech-to-Text</Title>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {state === 'idle' && (
          <Button
            type="primary"
            icon={<AudioOutlined />}
            onClick={startRecording}
          >
            Start Recording
          </Button>
        )}
        {state === 'recording' && (
          <Button
            danger
            icon={<PauseCircleOutlined />}
            onClick={stopRecording}
          >
            Stop Recording
          </Button>
        )}
        {state === 'transcribing' && (
          <Button disabled icon={<LoadingOutlined />}>Transcribing…</Button>
        )}
        {state === 'recording' && (
          <Tag color="red" style={{ fontSize: 11 }}>● Recording</Tag>
        )}
      </div>

      {error && (
        <Text style={{ color: 'var(--vscode-error)', fontSize: 12 }}>{error}</Text>
      )}

      <div style={{
        minHeight: 80,
        padding: '10px 12px',
        background: 'var(--vscode-bg)',
        border: '1px solid var(--vscode-border)',
        borderRadius: 4,
      }}>
        {transcript
          ? <Text style={{ color: 'var(--vscode-text)', fontSize: 13, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>{transcript}</Text>
          : <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12, fontStyle: 'italic' }}>Transcript will appear here…</Text>
        }
      </div>

      {transcript && (
        <Button
          size="small"
          onClick={() => setTranscript('')}
          style={{ alignSelf: 'flex-start' }}
        >
          Clear
        </Button>
      )}
    </div>
  )
}

// ── Sound Library ─────────────────────────────────────────────────────────

function playParams(params: BfxrParams, onEnd: () => void): () => void {
  const ctx = getSharedAudioContext()
  const stop = bfxrPlay(params, ctx)
  const ms = (params.attackTime + params.sustainTime + params.decayTime + 0.05) * 1000
  const t = setTimeout(onEnd, ms)
  return () => { stop(); clearTimeout(t); onEnd() }
}

// ── Parameter row helpers ──────────────────────────────────────────────────

const LABEL: React.CSSProperties = { color: 'var(--vscode-text-muted)', fontSize: 11, minWidth: 120, flexShrink: 0 }
const VALUE: React.CSSProperties = { color: 'var(--vscode-text-muted)', fontSize: 11, fontFamily: 'monospace', minWidth: 38, textAlign: 'right', flexShrink: 0 }

function ParamSlider({ label, value, min, max, step, fmt, onChange }: {
  label: string; value: number; min: number; max: number; step: number
  fmt?: (v: number) => string; onChange: (v: number) => void
}): React.ReactElement {
  const display = fmt ? fmt(value) : value.toFixed(value < 10 ? 2 : 0)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={LABEL}>{label}</span>
      <Slider min={min} max={max} step={step} value={value} onChange={onChange}
        style={{ flex: 1, margin: 0 }}
        styles={{ track: { background: 'var(--vscode-accent)' } }}
      />
      <span style={VALUE}>{display}</span>
    </div>
  )
}

const WAVE_TYPES: WaveType[] = ['square', 'sawtooth', 'sine', 'triangle', 'noise', 'breaker']

function ParamEditor({ params, onChange }: { params: BfxrParams; onChange: (p: BfxrParams) => void }): React.ReactElement {
  function set<K extends keyof BfxrParams>(key: K, val: BfxrParams[K]): void {
    onChange({ ...params, [key]: val })
  }

  const sectionStyle: React.CSSProperties = {
    display: 'flex', flexDirection: 'column', gap: 6,
    padding: '10px 12px',
    background: 'var(--vscode-bg)',
    border: '1px solid var(--vscode-border)',
    borderRadius: 4,
  }
  const sectionLabel: React.CSSProperties = {
    color: 'var(--vscode-text-muted)', fontSize: 10, fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 0 4px' }}>

      {/* Wave type */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Wave</span>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {WAVE_TYPES.map((wt) => (
            <button key={wt} onClick={() => set('waveType', wt)} style={{
              padding: '2px 8px', borderRadius: 3, fontSize: 11, cursor: 'pointer',
              background: params.waveType === wt ? 'var(--vscode-accent)' : 'var(--vscode-surface)',
              color: params.waveType === wt ? '#fff' : 'var(--vscode-text-muted)',
              border: `1px solid ${params.waveType === wt ? 'var(--vscode-accent)' : 'var(--vscode-border)'}`,
            }}>{wt}</button>
          ))}
        </div>
      </div>

      {/* Envelope */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Envelope</span>
        <ParamSlider label="Attack" value={params.attackTime} min={0} max={1} step={0.01} fmt={(v) => `${v.toFixed(2)}s`} onChange={(v) => set('attackTime', v)} />
        <ParamSlider label="Sustain" value={params.sustainTime} min={0} max={1} step={0.01} fmt={(v) => `${v.toFixed(2)}s`} onChange={(v) => set('sustainTime', v)} />
        <ParamSlider label="Punch" value={params.sustainPunch} min={0} max={1} step={0.01} onChange={(v) => set('sustainPunch', v)} />
        <ParamSlider label="Decay" value={params.decayTime} min={0} max={1} step={0.01} fmt={(v) => `${v.toFixed(2)}s`} onChange={(v) => set('decayTime', v)} />
      </div>

      {/* Frequency */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Frequency</span>
        <ParamSlider label="Start freq" value={params.startFrequency} min={20} max={2000} step={1} fmt={(v) => `${v.toFixed(0)}Hz`} onChange={(v) => set('startFrequency', v)} />
        <ParamSlider label="Min freq" value={params.minFrequency} min={0} max={2000} step={1} fmt={(v) => `${v.toFixed(0)}Hz`} onChange={(v) => set('minFrequency', v)} />
        <ParamSlider label="Slide" value={params.slide} min={-2000} max={2000} step={10} fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}`} onChange={(v) => set('slide', v)} />
        <ParamSlider label="Δ Slide" value={params.deltaSlide} min={-500} max={500} step={5} fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}`} onChange={(v) => set('deltaSlide', v)} />
      </div>

      {/* Vibrato */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Vibrato</span>
        <ParamSlider label="Depth" value={params.vibratoDepth} min={0} max={1} step={0.01} onChange={(v) => set('vibratoDepth', v)} />
        <ParamSlider label="Speed" value={params.vibratoSpeed} min={0} max={40} step={0.5} fmt={(v) => `${v.toFixed(1)}Hz`} onChange={(v) => set('vibratoSpeed', v)} />
      </div>

      {/* Arpeggio */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Arpeggio</span>
        <ParamSlider label="Change ×" value={params.changeAmount} min={0} max={4} step={0.05} fmt={(v) => `${v.toFixed(2)}×`} onChange={(v) => set('changeAmount', v)} />
        <ParamSlider label="Change at" value={params.changeTime} min={0} max={1} step={0.01} fmt={(v) => `${v.toFixed(2)}s`} onChange={(v) => set('changeTime', v)} />
      </div>

      {/* Duty cycle — only relevant for square */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Duty Cycle</span>
        <ParamSlider label="Duty" value={params.squareDuty} min={0} max={1} step={0.01} onChange={(v) => set('squareDuty', v)} />
        <ParamSlider label="Sweep" value={params.dutySweep} min={-1} max={1} step={0.01} fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`} onChange={(v) => set('dutySweep', v)} />
      </div>

      {/* Retrigger */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Retrigger</span>
        <ParamSlider label="Repeat speed" value={params.repeatSpeed} min={0} max={1} step={0.01} fmt={(v) => v === 0 ? 'off' : `${v.toFixed(2)}s`} onChange={(v) => set('repeatSpeed', v)} />
      </div>

      {/* Phaser */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Phaser</span>
        <ParamSlider label="Offset" value={params.phaserOffset} min={-0.05} max={0.05} step={0.001} fmt={(v) => v === 0 ? 'off' : `${v.toFixed(3)}`} onChange={(v) => set('phaserOffset', v)} />
        <ParamSlider label="Sweep" value={params.phaserSweep} min={-1} max={1} step={0.01} fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`} onChange={(v) => set('phaserSweep', v)} />
      </div>

      {/* Filters */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Filters</span>
        <ParamSlider label="LP cutoff" value={params.lpFilterCutoff} min={0} max={1} step={0.01} onChange={(v) => set('lpFilterCutoff', v)} />
        <ParamSlider label="LP sweep" value={params.lpFilterCutoffSweep} min={-1} max={1} step={0.01} fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`} onChange={(v) => set('lpFilterCutoffSweep', v)} />
        <ParamSlider label="LP resonance" value={params.lpFilterResonance} min={0} max={1} step={0.01} onChange={(v) => set('lpFilterResonance', v)} />
        <ParamSlider label="HP cutoff" value={params.hpFilterCutoff} min={0} max={1} step={0.01} onChange={(v) => set('hpFilterCutoff', v)} />
        <ParamSlider label="HP sweep" value={params.hpFilterCutoffSweep} min={-1} max={1} step={0.01} fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`} onChange={(v) => set('hpFilterCutoffSweep', v)} />
      </div>

      {/* Volume */}
      <div style={sectionStyle}>
        <span style={sectionLabel}>Volume</span>
        <ParamSlider label="Master volume" value={params.masterVolume} min={0} max={1} step={0.01} onChange={(v) => set('masterVolume', v)} />
      </div>

    </div>
  )
}

// ── Sound preset row ───────────────────────────────────────────────────────

function PresetRow({ preset, playing, onPlay }: {
  preset: typeof SOUND_PRESETS[number]
  playing: boolean
  onPlay: (params: BfxrParams) => void
}): React.ReactElement {
  const [expanded, setExpanded] = useState(false)
  const [params, setParams] = useState<BfxrParams>({ ...DEFAULT_PARAMS, ...preset.params })
  const isDirty = JSON.stringify(params) !== JSON.stringify({ ...DEFAULT_PARAMS, ...preset.params })

  function handleReset(): void {
    setParams({ ...DEFAULT_PARAMS, ...preset.params })
  }

  return (
    <div style={{
      border: `1px solid ${playing ? 'var(--vscode-accent)' : 'var(--vscode-border)'}`,
      borderRadius: 4,
      overflow: 'hidden',
    }}>
      {/* Header row */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 12px',
        background: 'var(--vscode-surface)',
        cursor: 'pointer',
      }}
        onClick={() => setExpanded((v) => !v)}
      >
        <span style={{ color: 'var(--vscode-text-muted)', fontSize: 10, width: 10, flexShrink: 0 }}>
          {expanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
        </span>
        <Tooltip title={playing ? 'Stop' : 'Preview'}>
          <Button
            type="text" size="small"
            icon={playing
              ? <StopOutlined style={{ color: 'var(--vscode-accent)' }} />
              : <SoundOutlined style={{ color: 'var(--vscode-text-muted)' }} />
            }
            onClick={(e) => { e.stopPropagation(); onPlay(params) }}
            style={{ flexShrink: 0, padding: '0 4px' }}
          />
        </Tooltip>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Text style={{ color: 'var(--vscode-text)', fontSize: 13, fontFamily: 'monospace', display: 'block' }}>
            {preset.name}{isDirty && <span style={{ color: 'var(--vscode-accent)', marginLeft: 4, fontSize: 11 }}>*</span>}
          </Text>
          <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 11, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {preset.description}
          </Text>
        </div>
        <Tag style={{ fontSize: 10, flexShrink: 0, color: 'var(--vscode-text-muted)', borderColor: 'var(--vscode-border)' }}>
          {params.waveType}
        </Tag>
        {isDirty && (
          <Tooltip title="Reset to preset defaults">
            <Button type="text" size="small" icon={<RedoOutlined style={{ fontSize: 10 }} />}
              onClick={(e) => { e.stopPropagation(); handleReset() }}
              style={{ color: 'var(--vscode-text-muted)', padding: '0 2px', flexShrink: 0 }}
            />
          </Tooltip>
        )}
      </div>

      {/* Collapsible editor */}
      {expanded && (
        <div style={{ padding: '0 12px 12px', background: 'var(--vscode-bg)' }}>
          <ParamEditor params={params} onChange={(p) => { setParams(p); onPlay(p) }} />
        </div>
      )}
    </div>
  )
}

function SoundLibrary(): React.ReactElement {
  const [playingName, setPlayingName] = useState<string | null>(null)
  const stopRef = useRef<(() => void) | null>(null)

  function handlePlay(name: string, params: BfxrParams): void {
    stopRef.current?.()
    stopRef.current = null
    if (playingName === name) {
      setPlayingName(null)
      return
    }
    setPlayingName(name)
    stopRef.current = playParams(params, () => setPlayingName((cur) => cur === name ? null : cur))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 620 }}>
      <Title level={5} style={{ color: 'var(--vscode-text)', margin: 0 }}>Sound Library</Title>
      <Text style={{ color: 'var(--vscode-text-muted)', fontSize: 12 }}>
        Procedural sounds generated in-browser via the bfxr engine — no audio files. Click a row to edit parameters.
      </Text>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
        {SOUND_PRESETS.map((preset) => (
          <PresetRow
            key={preset.name}
            preset={preset}
            playing={playingName === preset.name}
            onPlay={(params) => handlePlay(preset.name, params)}
          />
        ))}
      </div>
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────

export default function SoundLabView(): React.ReactElement {
  const backendUrl = useAppStore((s) => s.backendUrl)

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'auto',
      padding: '24px 32px',
      gap: 40,
      background: 'var(--vscode-bg)',
    }}>
      <TtsPanel backendUrl={backendUrl} />
      <div style={{ borderTop: '1px solid var(--vscode-border)', paddingTop: 32 }}>
        <SttPanel backendUrl={backendUrl} />
      </div>
      <div style={{ borderTop: '1px solid var(--vscode-border)', paddingTop: 32 }}>
        <SoundLibrary />
      </div>
    </div>
  )
}
