import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { join } from 'path'
import { spawn, ChildProcess } from 'child_process'
import { createWriteStream, mkdirSync, WriteStream } from 'fs'

const BACKEND_URL = 'http://127.0.0.1:8000'
let backendProcess: ChildProcess | null = null
let backendLogStream: WriteStream | null = null

function getLogPath(): string {
  const logDir = join(app.getPath('userData'), 'logs')
  mkdirSync(logDir, { recursive: true })
  return join(logDir, 'backend.log')
}

function spawnBackend(): void {
  const appPath = app.getAppPath()
  console.log('[main] Spawning FastAPI backend from', appPath)

  const logPath = getLogPath()
  backendLogStream = createWriteStream(logPath, { flags: 'a' })
  console.log('[main] Backend logs →', logPath)

  backendProcess = spawn(
    join(appPath, '.venv', 'bin', 'python'),
    ['-m', 'uvicorn', 'src.backend.main:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'debug'],
    {
      cwd: appPath,
      stdio: 'pipe',
      env: { ...process.env }
    }
  )

  const write = (prefix: string, d: Buffer) => {
    const line = `${new Date().toISOString()} ${prefix} ${d.toString().trimEnd()}\n`
    backendLogStream?.write(line)
    console.log(line.trimEnd())
  }

  backendProcess.stdout?.on('data', (d: Buffer) => write('[backend]', d))
  backendProcess.stderr?.on('data', (d: Buffer) => write('[backend]', d))
  backendProcess.on('exit', (code: number | null) => {
    console.log('[main] Backend exited with code', code)
    backendLogStream?.end()
  })
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
  ipcMain.handle('open-external', (_event, url: string) => shell.openExternal(url))

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
