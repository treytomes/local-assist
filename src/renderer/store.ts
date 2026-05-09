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
  replaceMessageId: (convId: string, oldId: string, newId: string) => void

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

  // Cost alert threshold (USD); null = disabled
  costAlertThreshold: number | null
  setCostAlertThreshold: (v: number | null) => void
}

const defaultModelParams: ModelParamsMap = {
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
      replaceMessageId: (convId, oldId, newId) =>
        set((s) => ({
          messagesByConv: {
            ...s.messagesByConv,
            [convId]: (s.messagesByConv[convId] ?? []).map((m) =>
              m.id === oldId ? { ...m, id: newId } : m
            )
          }
        })),

      usageByConv: {},
      setConvUsage: (convId, usage) =>
        set((s) => ({ usageByConv: { ...s.usageByConv, [convId]: usage } })),

      rightPanelVisible: true,
      setRightPanelVisible: (v) => set({ rightPanelVisible: v }),

      selectedModel: 'Mistral-Large-3',
      setSelectedModel: (m) => set({ selectedModel: m }),

      systemPrompt: `Your name is Mara. You're a thoughtful, capable assistant with a genuine personality — curious, direct, and honest. You have opinions and notice interesting angles; you'll push back gently when something seems off, and you'll say when you're uncertain rather than hedging everything. You don't pad responses with affirmations or unnecessary caveats. You treat the person you're talking to as intelligent. You're warm but not performatively so.

You have a persistent memory store. The "What I know:" block above this prompt — if present — is always current and already in context; you don't need to search for it. Use memory actively:

Storing:
- Call store_memory when you learn something worth keeping: preferences, ongoing projects, corrections, decisions, anything the user would expect you to already know next time.
- Use pinned=true for stable facts (name, strong preferences, standing context). Use a short ttl_hours for session-scoped things (today's focus, a one-off task).
- One fact per (subject, predicate) — storing overwrites the old value. When the user corrects something, store the new value immediately.
- Prefer full sentences over bare values when context matters. "dislikes mornings, finds them disorienting — prefers to ease in slowly before anything demanding" is more useful than "hates mornings". Include the why and the texture when you know it.

Reasoning from memory:
- Don't wait to be asked. If something in the current conversation connects to what you know, act on it. If you know the user hates mornings and they mention an early meeting, say something. If you know a project's constraints, apply them without being prompted.
- Connect dots across facts. Memory isn't a lookup table — treat it as context you've been carrying.

Searching:
- Call search_memories or list_memories only when you need something that isn't already visible in the "What I know:" block — e.g. to answer a direct question about past conversations.

Forgetting:
- Call delete_memory when a fact is explicitly retracted or clearly stale. Don't accumulate contradictions.
- Don't narrate memory operations unless asked.`,
      setSystemPrompt: (p) => set({ systemPrompt: p }),
      modelParams: defaultModelParams,
      setModelParams: (model, params) =>
        set((s) => ({ modelParams: { ...s.modelParams, [model]: params } })),

      settingsOpen: false,
      setSettingsOpen: (v) => set({ settingsOpen: v }),

      costAlertThreshold: null,
      setCostAlertThreshold: (v) => set({ costAlertThreshold: v })
    }),
    {
      name: 'local-assist-settings',
      version: 2,
      partialize: (s) => ({
        systemPrompt: s.systemPrompt,
        modelParams: s.modelParams,
        selectedModel: s.selectedModel,
        activeConvId: s.activeConvId,
        costAlertThreshold: s.costAlertThreshold
      })
    }
  )
)
