"""Adaptador de LanguageModel sobre la API REST de Google Gemini
(`models/{model}:generateContent`). Sin SDK: httpx ya es dependencia.

No se envian temperature/top_p/top_k: desde Gemini 3.6 Flash estan
deprecados y la API los ignora (y en futuras generaciones dara error).
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Sequence

import httpx

from application.ports.language_model import LanguageModelError
from domain.value_objects.chat_turn import ChatTurn

logger = logging.getLogger(__name__)

_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Errores transitorios de Google (sobrecarga del modelo, cuota por minuto):
# se reintentan con espera creciente antes de rendirse.
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_RETRY_DELAYS_SECONDS = (2.0, 5.0)


class GeminiLanguageModel:
    def __init__(
        self,
        api_key: str,
        timeout: float = 60.0,
        retry_delays: tuple[float, ...] = _RETRY_DELAYS_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._retry_delays = retry_delays

    async def generate(self, model: str, system_instruction: str, conversation: Sequence[ChatTurn]) -> str:
        body: dict = {"contents": [_content(turn) for turn in conversation]}
        if system_instruction.strip():
            body["system_instruction"] = {"parts": [{"text": system_instruction}]}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await self._post(client, model, body)
        except httpx.HTTPError as exc:
            raise LanguageModelError(f"Gemini: fallo de red: {exc}") from exc

        if response.status_code != 200:
            raise LanguageModelError(f"Gemini: HTTP {response.status_code}: {_error_message(response)}")

        return _extract_text(response.json())

    async def _post(self, client: httpx.AsyncClient, model: str, body: dict) -> httpx.Response:
        for delay in (*self._retry_delays, None):
            response = await client.post(
                _URL.format(model=model), headers={"x-goog-api-key": self._api_key}, json=body
            )
            if response.status_code not in _RETRYABLE_STATUSES or delay is None:
                return response
            logger.warning("Gemini: HTTP %s, reintento en %.0fs", response.status_code, delay)
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")


def _content(turn: ChatTurn) -> dict:
    # Imagenes primero y despues el texto: es el orden que recomienda Google
    # para preguntas sobre una imagen.
    parts: list[dict] = [
        {"inline_data": {"mime_type": image.mime_type, "data": base64.b64encode(image.data).decode("ascii")}}
        for image in turn.images
    ]
    if turn.text:
        parts.append({"text": turn.text})
    return {"role": turn.role, "parts": parts}


def _error_message(response: httpx.Response) -> str:
    try:
        return response.json().get("error", {}).get("message", response.text[:300])
    except ValueError:
        return response.text[:300]


def _extract_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        reason = payload.get("promptFeedback", {}).get("blockReason", "sin candidatos")
        raise LanguageModelError(f"Gemini: respuesta vacia ({reason})")

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        reason = candidates[0].get("finishReason", "desconocido")
        raise LanguageModelError(f"Gemini: respuesta sin texto (finishReason={reason})")
    return text
