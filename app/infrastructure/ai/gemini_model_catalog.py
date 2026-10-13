"""Adaptador de ModelCatalog sobre la API de Gemini (`GET v1beta/models`).

Solo devuelve modelos de texto que admiten `generateContent`: se descartan
los de voz (tts/audio/transcribe), imagen (image/nano-banana), embeddings y tiempo real, que no sirven para
responder en el chat. Cachea la lista en memoria (por defecto 1 hora) para no
llamar a Google en cada carga del panel.

Ojo: la lista puede incluir modelos retirados "para usuarios nuevos" (p. ej.
gemini-2.5-flash da 404 al usarlo); eso solo se detecta probandolo.
"""
from __future__ import annotations

import time
from typing import Callable

import httpx

from application.ports.model_catalog import ModelCatalogError, ModelInfo

_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_EXCLUDED_MARKERS = (
    "tts", "audio", "transcribe", "image", "banana", "embedding", "live", "robotics", "computer-use", "aqa",
)


class GeminiModelCatalog:
    def __init__(
        self,
        api_key: str,
        ttl_seconds: float = 3600.0,
        timeout: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_key = api_key
        self._ttl = ttl_seconds
        self._timeout = timeout
        self._monotonic = monotonic
        self._cached: tuple[ModelInfo, ...] | None = None
        self._fetched_at = 0.0

    async def list_models(self) -> tuple[ModelInfo, ...]:
        if self._cached is not None and self._monotonic() - self._fetched_at < self._ttl:
            return self._cached
        self._cached = await self._fetch()
        self._fetched_at = self._monotonic()
        return self._cached

    async def _fetch(self) -> tuple[ModelInfo, ...]:
        models: list[ModelInfo] = []
        page_token = ""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                while True:
                    params = {"pageSize": 1000, **({"pageToken": page_token} if page_token else {})}
                    response = await client.get(_URL, params=params, headers={"x-goog-api-key": self._api_key})
                    if response.status_code != 200:
                        raise ModelCatalogError(f"Gemini: HTTP {response.status_code} al listar modelos")
                    payload = response.json()
                    models.extend(_text_models(payload.get("models") or []))
                    page_token = payload.get("nextPageToken") or ""
                    if not page_token:
                        break
        except httpx.HTTPError as exc:
            raise ModelCatalogError(f"Gemini: fallo de red al listar modelos: {exc}") from exc
        return tuple(sorted(models, key=lambda m: m.id))


def _text_models(raw_models: list[dict]) -> list[ModelInfo]:
    result = []
    for raw in raw_models:
        model_id = str(raw.get("name", "")).removeprefix("models/")
        if not model_id.startswith("gemini"):
            continue
        if "generateContent" not in raw.get("supportedGenerationMethods", []):
            continue
        if any(marker in model_id for marker in _EXCLUDED_MARKERS):
            continue
        result.append(ModelInfo(id=model_id, display_name=raw.get("displayName") or model_id))
    return result
