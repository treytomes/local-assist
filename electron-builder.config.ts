import type { Configuration } from 'electron-builder'

const config: Configuration = {
  appId: 'com.local-assist.app',
  productName: 'local-assist',
  directories: {
    buildResources: 'build',
    output: 'dist'
  },
  files: [
    'out/**/*',
    '!out/**/*.map'
  ],
  extraResources: [
    {
      from: 'src/backend',
      to: 'backend'
    }
  ],
  linux: {
    target: [{ target: 'AppImage', arch: ['x64'] }],
    category: 'Utility'
  },
  win: {
    target: [{ target: 'nsis', arch: ['x64'] }]
  },
  mac: {
    target: [{ target: 'dmg', arch: ['x64', 'arm64'] }],
    category: 'public.app-category.productivity'
  }
}

export default config
