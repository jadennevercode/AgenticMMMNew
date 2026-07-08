"""OpenAI-compatible Whisper ASR client.

Transcribes an uploaded audio file via `POST {base_url}/audio/transcriptions`
(multipart `file` + `model`, Bearer auth). Works against OpenAI or any
compatible/self-hosted Whisper endpoint. Credentials come from the single global
model-service config (`app/store/model_service.py`) the user fills in Settings.
"""
from __future__ import annotations

from typing import Optional

import httpx

from app.config import get_settings


class ASRError(RuntimeError):
    pass


# OpenAI's hosted Whisper rejects files larger than 25 MB. Compatible endpoints
# vary, but we guard at this limit and surface an actionable error rather than
# letting the upstream reject with an opaque 413.
_MAX_ASR_BYTES = 25 * 1024 * 1024


class SpeechClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout: Optional[int] = None,
    ) -> None:
        s = get_settings()
        self._base = (base_url or "").rstrip("/")
        self._model = model or ""
        self._api_key = api_key or ""
        self._timeout = timeout if timeout is not None else s.asr_timeout

    @property
    def available(self) -> bool:
        """True when an api key is resolvable — callers degrade gracefully otherwise."""
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    async def transcribe(self, *, data: bytes, filename: str,
                         language: Optional[str] = None) -> str:
        """Transcribe audio bytes to text. Raises ASRError on misconfig / failure."""
        if not self._api_key:
            raise ASRError(
                "ASR not configured — enter the ASR API key, base URL, and model in Settings."
            )
        if not data:
            raise ASRError("empty audio file")
        if len(data) > _MAX_ASR_BYTES:
            mb = len(data) / 1024 / 1024
            raise ASRError(
                f"audio is {mb:.0f} MB; the Whisper transcription limit is 25 MB. "
                "Split or compress the recording, or upload a text transcript instead."
            )
        url = self._base + "/audio/transcriptions"
        files = {"file": (filename or "audio", data, "application/octet-stream")}
        form: dict[str, str] = {"model": self._model}
        if language:
            form["language"] = language
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, files=files, data=form)
        except httpx.HTTPError as exc:
            raise ASRError(f"ASR request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise ASRError(f"ASR HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            payload = resp.json()
        except ValueError:
            # Some compatible servers return text/plain for response_format=text.
            return resp.text.strip()
        if isinstance(payload, dict):
            return str(payload.get("text", "")).strip()
        return ""


def get_asr() -> SpeechClient:
    """Build a SpeechClient from the global model-service config. An empty ASR key
    yields an unavailable client (callers degrade gracefully)."""
    from app.store.model_service import get_model_service

    creds = get_model_service().asr
    return SpeechClient(base_url=creds.base_url, model=creds.model, api_key=creds.api_key)
