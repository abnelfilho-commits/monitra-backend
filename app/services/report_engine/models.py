"""
Modelo Canônico do Report Engine.

Esses objetos representam o relatório de forma independente
de PDF, HTML ou qualquer tecnologia de apresentação.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class ReportComponent:
    """
    Menor unidade de conteúdo apresentada em uma seção.
    """

    type: str
    data: Any

    code: Optional[str] = None
    title: Optional[str] = None
    order: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportSection:
    """
    Representa uma seção lógica do relatório.
    """

    code: str
    title: str
    order: int

    components: List[ReportComponent] = field(default_factory=list)
    required: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_component(self, component: ReportComponent) -> None:
        """
        Adiciona um componente e mantém a ordenação da seção.
        """
        self.components.append(component)
        self.components.sort(key=lambda item: item.order)


@dataclass
class CanonicalReport:
    """
    Representação canônica de um relatório.

    É produzido pelo Report Composer e consumido pelos Renderers.
    """

    report_code: str
    report_name: str
    report_version: str

    subject: Dict[str, Any]
    period_start: str
    period_end: str

    id: str = field(default_factory=lambda: str(uuid4()))
    generated_at: datetime = field(default_factory=datetime.utcnow)

    sections: List[ReportSection] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_section(self, section: ReportSection) -> None:
        """
        Adiciona uma seção e mantém a ordenação do relatório.
        """
        self.sections.append(section)
        self.sections.sort(key=lambda item: item.order)

    def get_section(self, code: str) -> Optional[ReportSection]:
        """
        Localiza uma seção pelo código.
        """
        normalized_code = code.strip().upper()

        for section in self.sections:
            if section.code.strip().upper() == normalized_code:
                return section

        return None