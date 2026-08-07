"""
Classe base para todos os Knowledge Engines do Report Engine.
"""
from .knowledge_result import KnowledgeResult

from abc import ABC, abstractmethod

from ..context import ReportContext


class BaseKnowledgeEngine(ABC):
    """
    Classe base dos motores de conhecimento.

    Recebem um ReportContext totalmente preenchido pelos
    Providers e produzem conhecimento institucional.
    """

    code = "BASE_ENGINE"
    version = "1.0"

    @abstractmethod
    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:
        """
        Produz conhecimento institucional.
        """
        raise NotImplementedError