"""Volcano Ark LLM client (OpenAI-compatible chat/completions).

The endpoint does NOT support response_format=json_object, so structured output
is obtained by instructing the model to emit JSON and parsing it robustly
(strip code fences, extract the outermost JSON value) with bounded retries.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any, Optional

import httpx

from app.config import get_settings


class LLMError(RuntimeError):
    pass


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# Gateways in front of this endpoint report throttling as an HTTP 400 whose body
# carries the real 429 — so the status code alone cannot be trusted to detect it.
_RATE_LIMITED_RE = re.compile(
    r"\b429\b|too many requests|rate.?limit|请求频率过高|请求过于频繁", re.I)


def is_rate_limited(err: object) -> bool:
    """True when an error is the endpoint refusing us for rate reasons."""
    return bool(_RATE_LIMITED_RE.search(str(err)))


def _backoff_seconds(err: object, attempt: int) -> float:
    """Delay before retry `attempt` (1-based after the first try).

    Retrying a throttled endpoint immediately is worse than not retrying at all:
    this provider answers a burst with a 10-minute penalty lockout, so three
    back-to-back retries convert a transient 429 into ten dead minutes and every
    grounded agent step silently degrades to an empty result. Rate-limit errors
    therefore back off on a much longer curve than transport errors.
    """
    if is_rate_limited(err):
        base = min(60.0 * (2 ** (attempt - 1)), 240.0)
    else:
        base = min(2.0 * (2 ** (attempt - 1)), 20.0)
    return base * random.uniform(0.8, 1.2)  # jitter so parallel callers desynchronise


class _AdaptivePacer:
    """Process-wide minimum spacing between LLM requests, learned from 429s.

    Starts fully out of the way (no delay) so a generous endpoint runs at full
    speed. The first throttle response switches pacing on for the rest of the
    process: a run makes dozens of grounded calls, and without spacing it trips
    the quota again on the very next step, so every agent after the first one
    degrades to an empty result. Backing off *after* the fact is not enough —
    the limit has to stop being hit at all.
    """

    def __init__(self) -> None:
        self._min_interval = 0.0
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def paced(self) -> bool:
        return self._min_interval > 0

    def observe_rate_limit(self) -> None:
        interval = get_settings().llm_paced_interval
        if interval > self._min_interval:
            self._min_interval = float(interval)

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            delay = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self._min_interval
        if delay:
            await asyncio.sleep(delay)


_pacer = _AdaptivePacer()


def _repair_truncated(s: str) -> str:
    """Best-effort repair of JSON truncated mid-output (close open string/brackets)."""
    stack: list[str] = []
    in_str = False
    escaped = False
    for ch in s:
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    out = s
    if in_str:
        out += '"'
    # drop a trailing partial token like  ,"key": or trailing comma
    out = re.sub(r",\s*$", "", out)
    for opener in reversed(stack):
        out += "}" if opener == "{" else "]"
    return out


def _extract_json(text: str) -> Any:
    """Pull the first valid JSON object/array out of a model response, repairing truncation."""
    candidates: list[str] = []
    m = _FENCE_RE.search(text)
    if m:
        candidates.append(m.group(1))
    candidates.append(text)
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    # last resort: repair the largest opening fragment
    for open_c in ("{", "["):
        start = text.find(open_c)
        if start != -1:
            try:
                return json.loads(_repair_truncated(text[start:]))
            except json.JSONDecodeError:
                continue
    raise LLMError(f"No parseable JSON in response: {text[:400]!r}")


class VolcanoClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        s = get_settings()
        if not api_key:
            raise LLMError("LLM api key not configured — set it in Settings.")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._timeout = timeout if timeout is not None else s.llm_timeout
        self._max_retries = max_retries if max_retries is not None else s.llm_max_retries
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: Optional[float] = None,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        last_err: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=timeout if timeout is not None else self._timeout) as client:
            for attempt in range(self._max_retries):
                if attempt:
                    await asyncio.sleep(_backoff_seconds(last_err, attempt))
                await _pacer.wait()
                try:
                    resp = await client.post(self._url, headers=self._headers, json=payload)
                    if resp.status_code >= 400:
                        if is_rate_limited(resp.text):
                            _pacer.observe_rate_limit()
                        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                    try:
                        data = resp.json()
                    except ValueError as e:  # 200 with a non-JSON body (proxy page,
                        # truncated stream, empty response) — must not escape as a raw
                        # JSONDecodeError: every caller degrades on LLMError, and an
                        # unexpected type sails straight through those fallbacks and
                        # kills the run instead of dropping to the computed values.
                        raise LLMError(
                            f"non-JSON response ({resp.status_code}): {resp.text[:200]!r}") from e
                    return data["choices"][0]["message"]["content"] or ""
                except (httpx.HTTPError, LLMError, KeyError, IndexError, TypeError) as e:
                    last_err = e
        # Name the type: httpx timeouts stringify to "", which otherwise reports as
        # "failed after 3 attempts: " and says nothing about what went wrong.
        detail = f"{type(last_err).__name__}: {last_err}" if last_err else "unknown error"
        raise LLMError(f"LLM chat failed after {self._max_retries} attempts — {detail}")

    async def json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 16000,
        timeout: Optional[float] = None,
    ) -> Any:
        """Ask for JSON; retry with a stricter nudge if parsing fails."""
        base_user = (
            user
            + "\n\nReturn ONLY valid JSON. No prose, no markdown fences, no comments."
        )
        last_err: Optional[Exception] = None
        for attempt in range(self._max_retries):
            nudge = "" if attempt == 0 else (
                "\n\nYour previous reply was not valid JSON. Output a single valid "
                "JSON value and nothing else."
            )
            content = await self.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": base_user + nudge},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            try:
                return _extract_json(content)
            except LLMError as e:
                last_err = e
        raise LLMError(f"Could not get JSON after {self._max_retries} attempts: {last_err}")


# ── LLM resolution (global model-service config) ─────────
# The single global GlobalModelConfig supplies the actual key/base-url/model the
# user entered in Settings. Clients are cached by their resolved
# (base_url, model, api_key, timeout, retries) tuple so repeated calls reuse one.
_clients: dict[tuple, VolcanoClient] = {}


def get_llm() -> VolcanoClient:
    """Resolve the LLM client from the global model-service config.

    Raises LLMError (surfaced by the run-gate) until the user fills Settings."""
    from app.store.model_service import get_model_service

    s = get_settings()
    creds = get_model_service().llm
    base_url, model, api_key = creds.base_url, creds.model, creds.api_key
    if not (api_key and base_url and model):
        raise LLMError(
            "LLM not configured — enter the API key, base URL, and model name in Settings."
        )
    cache_key = (base_url, model, api_key, s.llm_timeout, s.llm_max_retries)
    client = _clients.get(cache_key)
    if client is None:
        client = VolcanoClient(base_url=base_url, model=model, api_key=api_key,
                               timeout=s.llm_timeout, max_retries=s.llm_max_retries)
        _clients[cache_key] = client
    return client
