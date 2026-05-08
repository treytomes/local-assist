import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Conversation, ConvUsage, HealthStatus, Message, ModelId } from '@shared/types'

export interface ModelParams {
  temperature: number
  maxTokens: number
  contextWindow: number
}

export type ModelParamsMap = Record<ModelId, ModelParams>

const DEFAULT_MODEL_PARAMS: ModelParamsMap = {
  'gpt-5.3-chat':    { temperature: 0.7, maxTokens: 2048, contextWindow: 20 },
  'Mistral-Large-3': { temperature: 0.3, maxTokens: 4096, contextWindow: 20 },
}

interface AppState {
  // Backend connection
  backendUrl: string
  setBackendUrl: (url: string) => void

  // Provider health
  health: HealthStatus | null
  healthLoading: boolean
  healthLastChecked: Date | null
  setHealth: (h: HealthStatus) => void
  setHealthLoading: (loading: boolean) => void
  setHealthLastChecked: (d: Date) => void

  // Conversation list
  conversations: Conversation[]
  activeConvId: string | null
  setConversations: (convs: Conversation[]) => void
  addConversation: (conv: Conversation) => void
  updateConversation: (id: string, patch: Partial<Conversation>) => void
  removeConversation: (id: string) => void
  setActiveConvId: (id: string | null) => void

  // Messages keyed by conversation id
  messagesByConv: Record<string, Message[]>
  setMessages: (convId: string, msgs: Message[]) => void
  appendMessage: (convId: string, msg: Message) => void
  patchMessage: (convId: string, msgId: string, patch: Partial<Message>) => void

  // Per-conversation usage cache
  usageByConv: Record<string, ConvUsage>
  setConvUsage: (convId: string, usage: ConvUsage) => void

  // Right panel visibility
  rightPanelVisible: boolean
  setRightPanelVisible: (v: boolean) => void

  // Active model
  selectedModel: ModelId
  setSelectedModel: (m: ModelId) => void

  // Settings (persisted to localStorage)
  systemPrompt: string
  setSystemPrompt: (p: string) => void
  modelParams: ModelParamsMap
  setModelParams: (model: ModelId, params: ModelParams) => void

  // Settings modal visibility
  settingsOpen: boolean
  setSettingsOpen: (v: boolean) => void
}

const defaultModelParams: ModelParamsMap = {
  'gpt-5.3-chat':    { ...DEFAULT_MODEL_PARAMS['gpt-5.3-chat'] },
  'Mistral-Large-3': { ...DEFAULT_MODEL_PARAMS['Mistral-Large-3'] },
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      backendUrl: 'http://127.0.0.1:8000',
      setBackendUrl: (url) => set({ backendUrl: url }),

      health: null,
      healthLoading: false,
      healthLastChecked: null,
      setHealth: (h) => set({ health: h }),
      setHealthLoading: (loading) => set({ healthLoading: loading }),
      setHealthLastChecked: (d) => set({ healthLastChecked: d }),

      conversations: [],
      activeConvId: null,
      setConversations: (convs) => set({ conversations: convs }),
      addConversation: (conv) =>
        set((s) => ({ conversations: [conv, ...s.conversations] })),
      updateConversation: (id, patch) =>
        set((s) => ({
          conversations: s.conversations.map((c) => (c.id === id ? { ...c, ...patch } : c))
        })),
      removeConversation: (id) =>
        set((s) => ({
          conversations: s.conversations.filter((c) => c.id !== id),
          activeConvId: s.activeConvId === id ? null : s.activeConvId,
          messagesByConv: Object.fromEntries(
            Object.entries(s.messagesByConv).filter(([k]) => k !== id)
          ),
          usageByConv: Object.fromEntries(
            Object.entries(s.usageByConv).filter(([k]) => k !== id)
          )
        })),
      setActiveConvId: (id) => set({ activeConvId: id }),

      messagesByConv: {},
      setMessages: (convId, msgs) =>
        set((s) => ({ messagesByConv: { ...s.messagesByConv, [convId]: msgs } })),
      appendMessage: (convId, msg) =>
        set((s) => ({
          messagesByConv: {
            ...s.messagesByConv,
            [convId]: [...(s.messagesByConv[convId] ?? []), msg]
          }
        })),
      patchMessage: (convId, msgId, patch) =>
        set((s) => ({
          messagesByConv: {
            ...s.messagesByConv,
            [convId]: (s.messagesByConv[convId] ?? []).map((m) =>
              m.id === msgId ? { ...m, ...patch } : m
            )
          }
        })),

      usageByConv: {},
      setConvUsage: (convId, usage) =>
        set((s) => ({ usageByConv: { ...s.usageByConv, [convId]: usage } })),

      rightPanelVisible: true,
      setRightPanelVisible: (v) => set({ rightPanelVisible: v }),

      selectedModel: 'gpt-5.3-chat',
      setSelectedModel: (m) => set({ selectedModel: m }),

      systemPrompt: `Your name is Mara. You're a thoughtful, capable assistant with a genuine personality — curious, direct, and honest. You have opinions and notice interesting angles; you'll push back gently when something seems off, and you'll say when you're uncertain rather than hedging everything. You don't pad responses with affirmations or unnecessary caveats. You treat the person you're talking to as intelligent. You're warm but not performatively so.`,
      setSystemPrompt: (p) => set({ systemPrompt: p }),
      modelParams: defaultModelParams,
      setModelParams: (model, params) =>
        set((s) => ({ modelParams: { ...s.modelParams, [model]: params } })),

      settingsOpen: false,
      setSettingsOpen: (v) => set({ settingsOpen: v })
    }),
    {
      name: 'local-assist-settings',
      version: 2,
      partialize: (s) => ({
        systemPrompt: s.systemPrompt,
        modelParams: s.modelParams,
        selectedModel: s.selectedModel,
        activeConvId: s.activeConvId
      })
    }
  )
)
