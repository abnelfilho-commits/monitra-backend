"""
Registro institucional dos relatórios disponíveis no Report Engine.
"""
from .sections.base_section import BaseSectionBuilder
from .base_provider import BaseProvider

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type

from .base_engine import BaseReportEngine
from .constants import REPORT_STATUS_ACTIVE


@dataclass(frozen=True)
class ReportDefinition:
    """
    Definição declarativa de um relatório.

    Informa ao Report Engine quais componentes participam
    do pipeline de geração.
    """

    code: str
    name: str
    version: str
    domain: str

    slug: Optional[str] = None
    status: str = REPORT_STATUS_ACTIVE

    providers: List[Type[BaseProvider]] = field(default_factory=list)
    engines: List[Type[BaseReportEngine]] = field(default_factory=list)
    sections: List[Type[BaseSectionBuilder]] = field(default_factory=list)

    template: Optional[str] = None
    renderer: Optional[str] = None
    required_parameters: List[str] = field(default_factory=list)


class ReportRegistry:
    """
    Catálogo oficial das definições de relatórios.
    """

    def __init__(self) -> None:
        self._definitions: Dict[str, ReportDefinition] = {}

    def register(self, definition: ReportDefinition) -> None:
        """
        Registra uma definição.

        Não permite sobrescrever um código já registrado.
        """
        if not definition.code:
            raise ValueError("O código do relatório é obrigatório.")

        normalized_code = definition.code.strip().upper()

        if normalized_code in self._definitions:
            raise ValueError(
                f"Relatório já registrado: {normalized_code}"
            )

        self._definitions[normalized_code] = definition

    def get(self, report_code: str) -> ReportDefinition:
        """
        Retorna a definição de um relatório pelo código.
        """
        if not report_code:
            raise ValueError("report_code é obrigatório.")

        normalized_code = report_code.strip().upper()
        definition = self._definitions.get(normalized_code)

        if definition is None:
            raise LookupError(
                f"Relatório não encontrado no Registry: {normalized_code}"
            )

        return definition

    def exists(self, report_code: str) -> bool:
        """
        Verifica se o relatório está registrado.
        """
        if not report_code:
            return False

        return report_code.strip().upper() in self._definitions

    def list_all(self) -> List[ReportDefinition]:
        """
        Lista todas as definições registradas.
        """
        return list(self._definitions.values())


report_registry = ReportRegistry()