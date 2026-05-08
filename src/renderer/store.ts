import { create } from 'zustand'
import type { HealthStatus } from '@shared/types'

interface AppState {
  backendUrl: string
  health: HealthStatus | null
  healthLoading: boolean
  healthLastChecked: Date | null
  setBackendUrl: (url: string) => void
  setHealth: (h: HealthStatus) => void
  setHealthLoading: (loading: boolean) => void
  setHealthLastChecked: (d: Date) => void
}

export const useAppStore = create<AppState>((set) => ({
  backendUrl: 'http://127.0.0.1:8000',
  health: null,
  healthLoading: false,
  healthLastChecked: null,
  setBackendUrl: (url) => set({ backendUrl: url }),
  setHealth: (h) => set({ health: h }),
  setHealthLoading: (loading) => set({ healthLoading: loading }),
  setHealthLastChecked: (d) => set({ healthLastChecked: d })
}))
