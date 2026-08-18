"""
Contrato base para os Engines do Report Engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from .context import ReportContext


@dataclass
class EngineResult:
    """
    Resultado padronizado produzido por um Engine.
    """

    engine_code: str
    engine_version: str
    status: str = "SUCCESS"

    indicators: List[Any] = field(default_factory=list)
    evidences: List[Any] = field(default_factory=list)
    narratives: List[Any] = field(default_factory=list)
    recommendations: List[Any] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    executed_at: datetime = field(default_factory=datetime.utcnow)


class BaseReportEngine(ABC):
    """
    Contrato base para Engines utilizados pelo Report Engine.

    Cada implementação deve consumir o ReportContext e devolver
    um EngineResult estruturado.
    """

    code: str = "BASE_REPORT_ENGINE"
    version: str = "1.0"

    def supports(self, context: ReportContext) -> bool:
        """
        Indica se o Engine suporta o contexto recebido.

        Pode ser sobrescrito por Engines específicos.
        """
        return True

    def validate(self, context: ReportContext) -> None:
        """
        Validação básica antes da execução.
        """
        if not context.report_code:
            raise ValueError("report_code é obrigatório.")

        if not context.subject_id:
            raise ValueError("subject_id é obrigatório.")

        if context.period_start > context.period_end:
            raise ValueError(
                "period_start não pode ser posterior a period_end."
            )

    @abstractmethod
    def execute(self, context: ReportContext) -> EngineResult:
        """
        Executa a lógica do Engine.

        Deve ser implementado pelas classes especializadas.
        """
        raise NotImplementedError