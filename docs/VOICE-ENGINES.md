# Voice engines — Dynamic Island

The Dynamic Island voice path is implemented in `dynamic-island/app/voice/` and is coordinated by `VoiceManager`.

**Voice is push-to-talk only.** The microphone is not opened during idle startup, and there is no background wake-word listener.

## Speech to text

1. **Local:** whisper.cpp, invoked through `whisper-cli`.
2. **Cloud fallback:** ElevenLabs Scribe v2, using `ELEVENLABS_API_KEY`.

Configuration:
- `JARVIS_WHISPER_CPP`: path to the whisper.cpp executable (default: `whisper-cli`).
- `JARVIS_WHISPER_MODEL`: model size (default: `base`).
- `JARVIS_WHISPER_MODEL_PATH`: explicit model path. Default: `~/.jarvis/whisper/ggml-base.bin`.
- `ELEVENLABS_API_KEY`: enables cloud transcription fallback.

The local model must be downloaded separately. Recording is capped at 30 seconds. If local transcription is unavailable, the same captured audio is sent to the cloud fallback when a key is configured.

## Text to speech

1. **Local:** Kokoro ONNX, loaded on demand.
2. **Fallback:** edge-tts.

Kokoro model files are expected at:
- `~/.jarvis/kokoro/kokoro-v1.0.onnx`
- `~/.jarvis/kokoro/voices-v1.0.bin`

Environment variables:
- `JARVIS_KOKORO_VOICE`: Kokoro voice ID (default: `af_sarah`).
- `JARVIS_TTS_THREADS`: reserved for model/runtime thread tuning where supported.

Kokoro is preferred when its model files are available. If it cannot initialize or synthesize, the manager falls back to edge-tts. Audio is normalized to WAV where the MP3 decoder is available.

## Dependencies

The runtime requirements include `sounddevice`, `kokoro-onnx`, `edge-tts` and `pydub`. Install `whisper-cli` separately and download the selected whisper.cpp model. Kokoro model files are also downloaded separately; they are not bundled in the repository.

## Privacy and lifecycle

- Audio capture begins only after explicit push-to-talk activation.
- Recording stops when the user releases/cancels the interaction.
- No always-on microphone, wake-word process or automatic camera activation is part of the voice path.
- Voice shutdown must stop recording and speech output threads cleanly.

The current implementation does not expose the legacy browser bridge's HTTP voice routes or its old multi-provider TTS picker. Do not use those retired interfaces in new UI code.
