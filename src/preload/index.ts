import { contextBridge, ipcRenderer } from 'electron'

const electronAPI = {
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke('get-backend-url')
} as const

contextBridge.exposeInMainWorld('electronAPI', electronAPI)
