import type { BfxrParams } from './bfxr'
import { DEFAULT_PARAMS } from './bfxr'

export interface SoundPreset {
  name: string
  description: string
  params: BfxrParams
}

function p(overrides: Partial<BfxrParams>): BfxrParams {
  return { ...DEFAULT_PARAMS, ...overrides }
}

export const SOUND_PRESETS: SoundPreset[] = [
  {
    name: 'coin',
    description: 'Retro coin pickup — bright, short, upward chirp with a punchy sustain.',
    params: p({
      waveType: 'square',
      startFrequency: 660,
      slide: 200,
      attackTime: 0,
      sustainTime: 0.06,
      sustainPunch: 0.5,
      decayTime: 0.12,
      squareDuty: 0.5,
      masterVolume: 0.5,
    }),
  },
  {
    name: 'laser',
    description: 'Sci-fi laser shot — sharp downward frequency slide on a sawtooth wave.',
    params: p({
      waveType: 'sawtooth',
      startFrequency: 880,
      slide: -600,
      attackTime: 0,
      sustainTime: 0.08,
      sustainPunch: 0.2,
      decayTime: 0.15,
      masterVolume: 0.45,
    }),
  },
  {
    name: 'powerup',
    description: 'Power-up jingle — rising arpeggio with a warm square tone and long sustain.',
    params: p({
      waveType: 'square',
      startFrequency: 330,
      slide: 120,
      changeAmount: 1.5,
      changeTime: 0.12,
      attackTime: 0.01,
      sustainTime: 0.25,
      sustainPunch: 0.3,
      decayTime: 0.2,
      squareDuty: 0.4,
      masterVolume: 0.5,
    }),
  },
  {
    name: 'blip',
    description: 'Short UI blip — quick neutral click, useful for confirmations or selections.',
    params: p({
      waveType: 'square',
      startFrequency: 520,
      slide: 0,
      attackTime: 0,
      sustainTime: 0.02,
      sustainPunch: 0,
      decayTime: 0.05,
      squareDuty: 0.5,
      masterVolume: 0.4,
    }),
  },
  {
    name: 'explosion',
    description: 'Rumbling explosion — low noise burst with heavy low-pass filter and slow decay.',
    params: p({
      waveType: 'noise',
      startFrequency: 120,
      attackTime: 0,
      sustainTime: 0.15,
      sustainPunch: 0.6,
      decayTime: 0.45,
      lpFilterCutoff: 0.35,
      lpFilterResonance: 0.3,
      masterVolume: 0.6,
    }),
  },
  {
    name: 'dial-up',
    description: 'Dial-up modem handshake — rapid multi-tone chirp sequence with vibrato.',
    params: p({
      waveType: 'sine',
      startFrequency: 1200,
      slide: -80,
      changeAmount: 0.75,
      changeTime: 0.08,
      vibratoDepth: 0.15,
      vibratoSpeed: 18,
      attackTime: 0,
      sustainTime: 0.35,
      sustainPunch: 0,
      decayTime: 0.1,
      repeatSpeed: 0.12,
      masterVolume: 0.4,
    }),
  },
  {
    name: 'startup',
    description: 'Warm startup chime — gentle sine sweep rising to a bright resolving tone.',
    params: p({
      waveType: 'sine',
      startFrequency: 280,
      slide: 180,
      changeAmount: 1.25,
      changeTime: 0.18,
      attackTime: 0.04,
      sustainTime: 0.3,
      sustainPunch: 0.1,
      decayTime: 0.35,
      masterVolume: 0.45,
    }),
  },
]
