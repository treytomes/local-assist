import { contextBridge, ipcRenderer } from 'electron'

const electronAPI = {
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke('get-backend-url'),
  openExternal: (url: string): Promise<void> => ipcRenderer.invoke('open-external', url),
} as const

contextBridge.exposeInMainWorld('electronAPI', electronAPI)
