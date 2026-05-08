export {}

declare global {
  interface Window {
    electronAPI: {
      getBackendUrl: () => Promise<string>
    }
  }
}
