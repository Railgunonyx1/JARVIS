# Performance and resource policy

## Design targets

- Keep the compact island responsive while model and tool work runs off the Qt main thread.
- Avoid loading voice models, camera pipelines or the 3D workspace until explicitly requested.
- Bound queues, tool timeouts and retained conversation context.
- Prefer cloud inference when local hardware cannot run a suitable model efficiently; retain optional Ollama support.
- Keep the desktop shell functional when all model providers are unavailable.

## Measurement protocol

Record cold startup, warm startup, idle memory, UI interaction latency, first-token latency, total response time and shutdown time separately. Measure on the target machine and record CPU, GPU, RAM, Plasma/Qt versions, provider/model and network conditions.

For voice, measure microphone start/stop latency, STT duration, TTS first-audio latency and cancellation. For gestures, measure camera initialization, steady-state CPU/RAM and shutdown. For the 3D workspace, measure load time, frame pacing and memory on the target GPU.

Do not compare measurements taken with different providers, model versions, hardware, display scaling or network conditions as if they were equivalent. Keep hardware-dependent checks out of claims based solely on CI.
