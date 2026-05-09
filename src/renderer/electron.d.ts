export {}

declare global {
  interface Window {
    electronAPI: {
      getBackendUrl: () => Promise<string>
      openExternal: (url: string) => Promise<void>
    }
  }
}
