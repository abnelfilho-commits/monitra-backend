"""
Registry dos Renderers do Report Engine.
"""

from typing import Dict, Type

from .base_renderer import BaseRenderer
from .pdf_renderer import PDFRenderer


class RendererRegistry:
    """
    Catálogo oficial dos Renderers disponíveis.
    """

    def __init__(self) -> None:
        self._renderers: Dict[str, Type[BaseRenderer]] = {}

    def register(
        self,
        renderer_class: Type[BaseRenderer],
    ) -> None:

        code = renderer_class.code.strip().upper()

        if code in self._renderers:
            raise ValueError(
                f"Renderer já registrado: {code}"
            )

        self._renderers[code] = renderer_class

    def get(
        self,
        renderer_code: str,
    ) -> Type[BaseRenderer]:

        if not renderer_code:
            raise ValueError(
                "renderer_code é obrigatório."
            )

        code = renderer_code.strip().upper()

        renderer_class = self._renderers.get(code)

        if renderer_class is None:
            raise LookupError(
                f"Renderer não encontrado: {code}"
            )

        return renderer_class

    def exists(
        self,
        renderer_code: str,
    ) -> bool:

        if not renderer_code:
            return False

        return (
            renderer_code.strip().upper()
            in self._renderers
        )


renderer_registry = RendererRegistry()

renderer_registry.register(
    PDFRenderer
)