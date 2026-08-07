"""
Contexto de execução do Report Engine.
"""
from sqlalchemy.orm import Session
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from .models import ReportSection

@dataclass
class ReportContext:
    """
    Mantém o estado compartilhado durante a geração de um relatório.

    Cada etapa do pipeline deve alterar apenas os campos sob sua
    responsabilidade.
    """

    report_code: str
    subject_id: int
    requested_by: int
    period_start: date
    period_end: date

    module: Optional[str] = None
    output_format: str = "PDF"
    parameters: Dict[str, Any] = field(default_factory=dict)

    execution_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    created_at: datetime = field(
        default_factory=datetime.utcnow
    )

    definition: Optional[Any] = None
    subject: Optional[Any] = None

    collected_data: Dict[str, Any] = field(default_factory=dict)
    official_readings: Dict[str, Any] = field(default_factory=dict)
    indicators: List[Any] = field(default_factory=list)
    evidences: List[Any] = field(default_factory=list)
    narratives: List[Any] = field(default_factory=list)
    recommendations: List[Any] = field(default_factory=list)
    sections: List[ReportSection] = field(default_factory=list)
    canonical_report: Optional[Any] = None
    db: Optional[Session] = None
    
    warnings: List[str] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)

    def add_warning(self, message: str) -> None:
        """Registra um aviso não bloqueante da execução."""
        if message and message not in self.warnings:
            self.warnings.append(message)

    def add_collected_data(self, provider_code: str, data: Any) -> None:
        """Armazena o resultado produzido por um Provider."""
        if not provider_code:
            raise ValueError("provider_code é obrigatório.")

        self.collected_data[provider_code] = data

    def add_official_reading(self, engine_code: str, reading: Any) -> None:
        """Armazena uma Leitura Oficial produzida por um Engine especializado."""
        if not engine_code:
            raise ValueError("engine_code é obrigatório.")

        self.official_readings[engine_code] = reading
        
    def add_section(
        self,
        section: "ReportSection",
    ) -> None:
        """
        Adiciona uma seção produzida pelos
        Knowledge Engines.
        """

        self.sections.append(section)


    def get_sections(self) -> List["ReportSection"]:
        """
        Retorna as seções produzidas durante
        a execução do relatório.
        """

        return list(self.sections)