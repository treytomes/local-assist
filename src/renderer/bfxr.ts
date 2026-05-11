/**
 * bfxr-inspired procedural sound engine using Web Audio API.
 * Single-oscillator synth with ADSR, frequency modulation, vibrato,
 * arpeggio, duty cycle, flanger, and lo/hi-pass filters.
 */

export type WaveType = 'square' | 'sawtooth' | 'sine' | 'triangle' | 'noise' | 'breaker'

export interface BfxrParams {
  waveType: WaveType

  // Envelope (seconds)
  attackTime: number
  sustainTime: number
  sustainPunch: number   // 0–1, boost at start of sustain
  decayTime: number

  // Frequency (Hz)
  startFrequency: number
  minFrequency: number   // stop slide when freq drops below this
  slide: number          // Hz/s added each second (negative = downslide)
  deltaSlide: number     // acceleration of slide

  // Vibrato
  vibratoDepth: number   // 0–1 fraction of freq
  vibratoSpeed: number   // Hz

  // Arpeggio
  changeAmount: number   // multiplier applied to freq after changeTime
  changeTime: number     // seconds before arpeggio triggers

  // Duty cycle (square wave only)
  squareDuty: number     // 0–1
  dutySweep: number      // change per second

  // Repeat
  repeatSpeed: number    // 0 = no repeat; >0 = retrigger period in seconds

  // Phaser / flanger
  phaserOffset: number   // seconds of delay (0 = off)
  phaserSweep: number    // change per second

  // Filters
  lpFilterCutoff: number     // 0–1 (1 = fully open)
  lpFilterCutoffSweep: number
  lpFilterResonance: number  // 0–1
  hpFilterCutoff: number     // 0–1
  hpFilterCutoffSweep: number

  // Volume
  masterVolume: number   // 0–1
}

export const DEFAULT_PARAMS: BfxrParams = {
  waveType: 'square',
  attackTime: 0,
  sustainTime: 0.1,
  sustainPunch: 0,
  decayTime: 0.1,
  startFrequency: 440,
  minFrequency: 0,
  slide: 0,
  deltaSlide: 0,
  vibratoDepth: 0,
  vibratoSpeed: 0,
  changeAmount: 0,
  changeTime: 0,
  squareDuty: 0.5,
  dutySweep: 0,
  repeatSpeed: 0,
  phaserOffset: 0,
  phaserSweep: 0,
  lpFilterCutoff: 1,
  lpFilterCutoffSweep: 0,
  lpFilterResonance: 0.5,
  hpFilterCutoff: 0,
  hpFilterCutoffSweep: 0,
  masterVolume: 0.5,
}

const SAMPLE_RATE = 44100

/** Render params to a Float32Array of mono PCM samples. */
export function render(p: BfxrParams): Float32Array {
  const totalTime = p.attackTime + p.sustainTime + p.decayTime + 0.05
  const numSamples = Math.ceil(totalTime * SAMPLE_RATE)
  const buf = new Float32Array(numSamples)

  let freq = p.startFrequency
  let slide = p.slide
  let duty = p.squareDuty
  let phase = 0
  let phaserPos = 0
  let phaserBuf = new Float32Array(1024)
  let phaserIdx = 0
  let lpFilterPos = 0
  let lpFilterPosOld = 0
  let lpFilterVelocity = 0
  let hpFilterPos = 0
  let repeatTimer = 0
  let arpeggioTriggered = false

  const lpCutoff = () => Math.min(1, p.lpFilterCutoff + p.lpFilterCutoffSweep * (t / totalTime))
  const hpCutoff = () => Math.min(1, p.hpFilterCutoff + p.hpFilterCutoffSweep * (t / totalTime))

  let t = 0
  for (let i = 0; i < numSamples; i++) {
    t = i / SAMPLE_RATE

    // Repeat
    if (p.repeatSpeed > 0) {
      repeatTimer += 1 / SAMPLE_RATE
      if (repeatTimer >= p.repeatSpeed) {
        repeatTimer = 0
        freq = p.startFrequency
        slide = p.slide
        duty = p.squareDuty
        arpeggioTriggered = false
      }
    }

    // Arpeggio
    if (!arpeggioTriggered && p.changeTime > 0 && t >= p.changeTime) {
      arpeggioTriggered = true
      if (p.changeAmount !== 0) freq *= p.changeAmount
    }

    // Frequency slide
    slide += p.deltaSlide / SAMPLE_RATE
    freq += slide / SAMPLE_RATE
    if (p.minFrequency > 0 && freq < p.minFrequency) freq = p.minFrequency

    // Vibrato
    const vibratoMod = p.vibratoDepth > 0
      ? 1 + p.vibratoDepth * Math.sin(2 * Math.PI * p.vibratoSpeed * t)
      : 1
    const effectiveFreq = Math.max(1, freq * vibratoMod)

    // Duty sweep
    duty = Math.max(0, Math.min(1, duty + p.dutySweep / SAMPLE_RATE))

    // Oscillator
    phase += effectiveFreq / SAMPLE_RATE
    if (phase >= 1) phase -= 1

    let sample = 0
    switch (p.waveType) {
      case 'square':
        sample = phase < duty ? 0.5 : -0.5
        break
      case 'sawtooth':
        sample = phase - 0.5
        break
      case 'sine':
        sample = Math.sin(2 * Math.PI * phase)
        break
      case 'triangle':
        sample = phase < 0.5 ? 4 * phase - 1 : 3 - 4 * phase
        break
      case 'noise':
        sample = Math.random() * 2 - 1
        break
      case 'breaker':
        sample = Math.sqrt(Math.abs(Math.sin(Math.PI * phase * phase))) * (phase < 0.5 ? 1 : -1)
        break
    }

    // LP filter
    if (p.lpFilterCutoff < 1) {
      const cut = Math.pow(lpCutoff(), 3) * 0.1
      const res = 1 - Math.max(0, Math.min(1, p.lpFilterResonance))
      lpFilterVelocity += (sample - lpFilterPos) * cut
      lpFilterVelocity *= res
      lpFilterPos += lpFilterVelocity
      sample = lpFilterPos
    }

    // HP filter
    if (p.hpFilterCutoff > 0) {
      const cut = Math.pow(hpCutoff(), 3) * 0.1
      hpFilterPos += (lpFilterPos - hpFilterPos) * cut
      // unused here but keeps position for next iteration
      sample = sample - hpFilterPos
    }

    // Phaser
    if (p.phaserOffset !== 0 || p.phaserSweep !== 0) {
      phaserPos += p.phaserSweep / SAMPLE_RATE
      const delay = Math.floor(Math.abs(p.phaserOffset + phaserPos) * SAMPLE_RATE) & 1023
      phaserBuf[phaserIdx & 1023] = sample
      sample = (sample + (phaserBuf[(phaserIdx - delay + 1024) & 1023] ?? 0)) * 0.5
      phaserIdx++
    }

    // Envelope
    let env = 0
    const at = p.attackTime, su = p.sustainTime, de = p.decayTime
    if (t < at) {
      env = t / at
    } else if (t < at + su) {
      env = 1 + p.sustainPunch * (1 - (t - at) / su)
    } else if (t < at + su + de) {
      env = 1 - (t - at - su) / de
    }

    buf[i] = sample * env * p.masterVolume
  }

  return buf
}

let _sharedCtx: AudioContext | null = null

/** Returns the shared AudioContext, creating it on first call. */
export function getSharedAudioContext(): AudioContext {
  if (!_sharedCtx) _sharedCtx = new AudioContext()
  return _sharedCtx
}

/** Play a BfxrParams through the Web Audio API. Returns a function to stop early. */
export function play(params: BfxrParams, ctx?: AudioContext): () => void {
  const ac = ctx ?? getSharedAudioContext()
  const pcm = render(params)
  const buffer = ac.createBuffer(1, pcm.length, SAMPLE_RATE)
  buffer.copyToChannel(pcm, 0)
  const source = ac.createBufferSource()
  source.buffer = buffer
  source.connect(ac.destination)
  // Resume in case context was created before a user gesture (suspended state)
  if (ac.state === 'suspended') {
    ac.resume().then(() => source.start()).catch(() => {})
  } else {
    source.start()
  }
  return () => { try { source.stop() } catch { /* already ended */ } }
}
