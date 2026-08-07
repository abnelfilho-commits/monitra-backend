"""
Contrato base para os Providers do Report Engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from .context import ReportContext


@dataclass
class ProviderResult:
    """
    Resultado padronizado produzido por um Provider.
    """

    provider_code: str
    provider_version: str
    status: str = "SUCCESS"

    data: Any = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    collected_at: datetime = field(default_factory=datetime.utcnow)


class BaseProvider(ABC):
    """
    Contrato base dos Providers do Report Engine.

    Cada Provider deve coletar e normalizar dados de um domínio
    específico da plataforma.
    """

    code: str = "BASE_PROVIDER"
    version: str = "1.0"
    required: bool = False

    def supports(self, context: ReportContext) -> bool:
        """
        Indica se o Provider suporta o contexto recebido.
        """
        return True

    def validate(self, context: ReportContext) -> None:
        """
        Valida o contexto mínimo necessário para coleta.
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
    def collect(self, context: ReportContext) -> ProviderResult:
        """
        Coleta e normaliza os dados do domínio.
        """
        raise NotImplementedError