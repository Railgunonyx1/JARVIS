import { invoke } from '@tauri-apps/api/core'

export async function checkBackend() {
  try {
    const status = await invoke('check_backend')
    return status
  } catch (err) {
    return { running: false, ok: false, report: '', error: String(err) }
  }
}
