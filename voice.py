#!/usr/bin/env python3
"""Voice Engine — Speech-to-Text and Text-to-Speech for BlackRoad agents.

STT: Whisper via Ollama or local whisper model
TTS: Piper TTS (local, fast, offline)
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from typing import Optional

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.4.96:11434")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "whisper")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen2.5:1.5b")
PIPER_BIN = os.environ.get("PIPER_BIN", "piper")
PIPER_MODEL = os.environ.get("PIPER_MODEL", "en_US-lessac-medium.onnx")
RECORD_SECONDS = int(os.environ.get("RECORD_SECONDS", "5"))
SAMPLE_RATE = 16000


class VoiceEngine:
    """Voice I/O engine for BlackRoad agents."""

    def __init__(self):
        self.ollama_url = OLLAMA_URL.rstrip("/")

    def listen(self, duration: int = RECORD_SECONDS, device: Optional[str] = None) -> str:
        """Record audio from microphone and transcribe to text.

        Uses arecord (Linux) or sox (cross-platform) for recording,
        then Whisper via Ollama for transcription.
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        try:
            self._record(wav_path, duration, device)
            text = self._transcribe(wav_path)
            return text
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)

    def _record(self, output_path: str, duration: int, device: Optional[str] = None):
        """Record audio from microphone."""
        print(f"[voice] Recording {duration}s...", file=sys.stderr)

        # Try sox first (cross-platform)
        try:
            cmd = ["sox", "-d", "-r", str(SAMPLE_RATE), "-c", "1", "-b", "16", output_path,
                   "trim", "0", str(duration)]
            if device:
                cmd[1] = device
            subprocess.run(cmd, check=True, capture_output=True, timeout=duration + 5)
            print("[voice] Recording complete (sox)", file=sys.stderr)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        # Fall back to arecord (Linux/ALSA)
        try:
            cmd = ["arecord", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1",
                   "-d", str(duration), output_path]
            if device:
                cmd.extend(["-D", device])
            subprocess.run(cmd, check=True, capture_output=True, timeout=duration + 5)
            print("[voice] Recording complete (arecord)", file=sys.stderr)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        # Fall back: generate silent wav for testing
        print("[voice] No recording backend found, generating silence", file=sys.stderr)
        self._generate_silence(output_path, duration)

    def _generate_silence(self, path: str, duration: int):
        """Generate a silent WAV file for testing."""
        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"\x00\x00" * SAMPLE_RATE * duration)

    def _transcribe(self, audio_path: str) -> str:
        """Transcribe audio file using Whisper via Ollama or local."""
        # Try Ollama whisper endpoint
        try:
            with open(audio_path, "rb") as f:
                audio_data = f.read()
            import base64
            b64 = base64.b64encode(audio_data).decode()
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": WHISPER_MODEL,
                    "prompt": "Transcribe this audio.",
                    "images": [b64],
                    "stream": False,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception:
            pass

        # Fall back to local whisper CLI
        try:
            result = subprocess.run(
                ["whisper", audio_path, "--model", "tiny", "--language", "en",
                 "--output_format", "txt", "--output_dir", "/tmp"],
                capture_output=True, text=True, timeout=30
            )
            txt_path = audio_path.replace(".wav", ".txt")
            if os.path.exists(f"/tmp/{os.path.basename(txt_path)}"):
                with open(f"/tmp/{os.path.basename(txt_path)}") as f:
                    return f.read().strip()
            return result.stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        return "(transcription unavailable — install whisper or configure Ollama)"

    def speak(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        """Convert text to speech and play it.

        Uses Piper TTS for fast local synthesis.
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = output_path or f.name

        try:
            # Try Piper TTS
            cmd = [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", wav_path]
            proc = subprocess.run(
                cmd, input=text, capture_output=True, text=True, timeout=15
            )
            if proc.returncode == 0:
                print(f"[voice] Synthesized {len(text)} chars", file=sys.stderr)
            else:
                # Fall back to espeak
                subprocess.run(
                    ["espeak", "-w", wav_path, text],
                    capture_output=True, timeout=10
                )
                print("[voice] Synthesized with espeak fallback", file=sys.stderr)
        except FileNotFoundError:
            # Fall back to macOS say
            try:
                subprocess.run(
                    ["say", "-o", wav_path, "--data-format=LEI16@16000", text],
                    capture_output=True, timeout=10
                )
                print("[voice] Synthesized with macOS say", file=sys.stderr)
            except FileNotFoundError:
                print("[voice] No TTS backend available", file=sys.stderr)
                return None

        # Play the audio
        if not output_path:
            self._play(wav_path)
            os.unlink(wav_path)
            return None
        return wav_path

    def _play(self, wav_path: str):
        """Play a WAV file."""
        for player in ["aplay", "afplay", "sox"]:
            try:
                cmd = [player, wav_path] if player != "sox" else ["sox", wav_path, "-d"]
                subprocess.run(cmd, capture_output=True, timeout=30)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        print("[voice] No audio player found", file=sys.stderr)

    def converse(self, agent_id: str = "road", rounds: int = 0):
        """Voice conversation loop: listen → think → speak.

        Args:
            agent_id: Agent name for context
            rounds: Number of rounds (0 = infinite until Ctrl+C)
        """
        system = f"You are {agent_id}, a BlackRoad OS agent. Keep responses concise and conversational."
        history = []
        count = 0

        print(f"[voice] Starting conversation with {agent_id}. Press Ctrl+C to stop.", file=sys.stderr)
        try:
            while rounds == 0 or count < rounds:
                # Listen
                user_text = self.listen()
                if not user_text or user_text.startswith("("):
                    continue
                print(f"[you] {user_text}")

                # Think
                history.append(f"User: {user_text}")
                context = "\n".join(history[-10:])
                prompt = f"{system}\n\nConversation:\n{context}\n\n{agent_id}:"
                try:
                    response = requests.post(
                        f"{self.ollama_url}/api/generate",
                        json={"model": CHAT_MODEL, "prompt": prompt, "stream": False},
                        timeout=30,
                    ).json().get("response", "I'm here.").strip()
                except Exception:
                    response = "I'm having trouble connecting."

                history.append(f"{agent_id}: {response}")
                print(f"[{agent_id}] {response}")

                # Speak
                self.speak(response)
                count += 1

        except KeyboardInterrupt:
            print("\n[voice] Conversation ended.", file=sys.stderr)


if __name__ == "__main__":
    engine = VoiceEngine()

    if len(sys.argv) < 2:
        print("Usage: python voice.py <command> [args]")
        print("Commands:")
        print("  listen [seconds]       Record and transcribe")
        print("  speak <text>           Text-to-speech")
        print("  converse [agent_id]    Voice conversation loop")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "listen":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else RECORD_SECONDS
        text = engine.listen(duration)
        print(text)
    elif cmd == "speak":
        text = " ".join(sys.argv[2:])
        engine.speak(text)
    elif cmd == "converse":
        agent = sys.argv[2] if len(sys.argv) > 2 else "road"
        engine.converse(agent)
    else:
        print("Unknown command")
