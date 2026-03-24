# voice-engine

Voice I/O for BlackRoad agents. Whisper speech-to-text + Piper text-to-speech with a conversation loop.

## Usage

```python
from voice import VoiceEngine

engine = VoiceEngine()

# Record and transcribe
text = engine.listen(duration=5)
print(text)

# Text to speech
engine.speak("Hello from BlackRoad")

# Voice conversation loop (listen → agent → speak)
engine.converse(agent_id="road")
```

## CLI

```bash
python voice.py listen [seconds]        # Record + transcribe
python voice.py speak "Hello world"     # TTS + play
python voice.py converse [agent_id]     # Voice conversation loop
```

## Backends

**STT (Speech-to-Text):**
1. Whisper via Ollama (fleet inference)
2. Local whisper CLI fallback

**TTS (Text-to-Speech):**
1. Piper TTS (fast, offline, high quality)
2. espeak fallback (Linux)
3. macOS `say` fallback

**Recording:**
1. sox (cross-platform)
2. arecord (Linux/ALSA)

## Environment

```bash
OLLAMA_URL=http://192.168.4.96:11434
WHISPER_MODEL=whisper
CHAT_MODEL=qwen2.5:1.5b
PIPER_BIN=piper
PIPER_MODEL=en_US-lessac-medium.onnx
RECORD_SECONDS=5
```

## Part of BlackRoad-Agents

Remember the Road. Pave Tomorrow.

BlackRoad OS, Inc. — Incorporated 2025.
