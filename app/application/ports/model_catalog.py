"""Puerto de salida: lista los modelos de lenguaje que la clave configurada
puede usar para generar texto (alimenta el desplegable del panel)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display_name: str


class ModelCatalogError(Exception):
    """No se pudo obtener la lista de modelos del proveedor."""


class ModelCatalog(Protocol):
    async def list_models(self) -> tuple[ModelInfo, ...]: ...
