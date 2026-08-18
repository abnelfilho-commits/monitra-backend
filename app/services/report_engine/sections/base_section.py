"""
Contrato base para os Builders de Sections do Report Engine.
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..context import ReportContext
from ..models import ReportSection


class BaseSectionBuilder(ABC):
    """
    Contrato base para construção de Sections.

    Cada implementação deve conhecer apenas a responsabilidade
    da seção que constrói.
    """

    code: str = "BASE_SECTION"
    title: str = "Base Section"
    order: int = 0
    required: bool = False

    def supports(self, context: ReportContext) -> bool:
        """
        Indica se a seção deve ser incluída no relatório.
        """
        return True

    @abstractmethod
    def build(
        self,
        context: ReportContext,
    ) -> Optional[ReportSection]:
        """
        Constrói a Section.

        Pode retornar None quando a seção for opcional
        e não houver dados disponíveis.
        """
        raise NotImplementedError