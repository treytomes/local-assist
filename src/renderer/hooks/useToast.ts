import { App } from 'antd'

export function useToast() {
  const { message, notification } = App.useApp()

  return {
    success: (content: string) => message.success(content, 2),
    error: (content: string) => message.error(content, 4),
    info: (content: string) => message.info(content, 3),
    warning: (content: string) => message.warning(content, 3),
    notify: (title: string, description: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') =>
      notification[type]({
        message: title,
        description,
        placement: 'bottomRight',
        duration: 6,
      }),
  }
}
