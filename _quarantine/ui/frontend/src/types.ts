export interface TelemetryState {
  cpu: number; ram: number; gpu: number; disk: number
  cpuTemp: number; gpuTemp: number; processes: number
  uptime: number; tokensPerSec: number; latencyMs: number
  update: (data: Partial<TelemetryState>) => void
}

export interface ChatMessage {
  id: string; role: 'user' | 'ai' | 'system'; text: string
}

export interface TimingInfo {
  intent_ms?: number; ttft_ms?: number; tokens_per_sec?: number
  total_ms?: number; provider?: string
}

export interface ChatState {
  messages: ChatMessage[]; streaming: boolean; streamText: string
  timing: TimingInfo | null
  addMessage: (role: ChatMessage['role'], text: string) => void
  startStream: () => void; appendStream: (token: string) => void
  endStream: () => void; setTiming: (t: TimingInfo) => void
}

export interface HealthCheck {
  name: string; ok: boolean; message?: string
}

export interface HealthData {
  ok: boolean; report?: string; checks?: HealthCheck[]
}

export interface MicResult {
  ok: boolean; text?: string; response?: string
}

export interface WSStatusEvent {
  state: string; cpu?: number; performance_mode?: string
}

export interface WSVoiceEvent {
  state: string; text?: string
}

export interface WSLLMEvent {
  token?: string; timing?: TimingInfo; done?: boolean; response?: string
}

export type WSEvent =
  | { type: 'status'; payload: WSStatusEvent }
  | { type: 'voice'; payload: WSVoiceEvent }
  | { type: 'llm'; payload: WSLLMEvent }
  | { type: 'memory'; payload: unknown }
