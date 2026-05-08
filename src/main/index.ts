import { app, BrowserWindow, ipcMain } from 'electron'
import { join } from 'path'
import { spawn, ChildProcess } from 'child_process'

const BACKEND_URL = 'http://127.0.0.1:8000'
let backendProcess: ChildProcess | null = null

function spawnBackend(): void {
  const appPath = app.getAppPath()
  console.log('[main] Spawning FastAPI backend from', appPath)

  backendProcess = spawn(
    join(appPath, '.venv', 'bin', 'python'),
    ['-m', 'uvicorn', 'src.backend.main:app', '--host', '127.0.0.1', '--port', '8000'],
    {
      cwd: appPath,
      stdio: 'pipe',
      env: { ...process.env }
    }
  )

  backendProcess.stdout?.on('data', (d: Buffer) => console.log('[backend]', d.toString().trim()))
  backendProcess.stderr?.on('data', (d: Buffer) => console.error('[backend]', d.toString().trim()))
  backendProcess.on('exit', (code: number | null) =>
    console.log('[main] Backend exited with code', code)
  )
}

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: '#1e1e1e',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  if (process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }

  return win
}

app.whenReady().then(() => {
  if (app.isPackaged) {
    spawnBackend()
  } else {
    console.log('[main] Dev mode — backend started separately via concurrently')
  }

  ipcMain.handle('get-backend-url', () => BACKEND_URL)

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
  if (process.platform !== 'darwin') app.quit()
})
