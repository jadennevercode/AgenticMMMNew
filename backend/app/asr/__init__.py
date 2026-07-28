"""Automatic speech recognition (ASR) for interview audio.

OpenAI-compatible Whisper transcription (`POST {base}/audio/transcriptions`),
resolved from the single global model-service config (key + base-url + model the
user fills in Settings). See `whisper.py`.
"""
from app.asr.whisper import ASRError, SpeechClient, get_asr

__all__ = ["ASRError", "SpeechClient", "get_asr"]
