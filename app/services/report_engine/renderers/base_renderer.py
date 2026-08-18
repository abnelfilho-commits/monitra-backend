"""
Contrato base dos Renderers do Report Engine.
"""

from abc import ABC, abstractmethod

from ..models import CanonicalReport


class BaseRenderer(ABC):
    """
    Contrato comum para renderização de relatórios.
    """

    code = "BASE_RENDERER"

    @abstractmethod
    def render(
        self,
        report: CanonicalReport,
        output_path: str,
    ) -> str:
        """
        Renderiza o relatório e retorna o caminho gerado.
        """
        raise NotImplementedError