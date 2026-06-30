from abc import ABC, abstractmethod

from app.services.clinical_engine.context import AssessmentContext


class BaseAssessmentEngine(ABC):
    instrumento = None
    versao = None

    @abstractmethod
    def executar(self, context: AssessmentContext) -> dict:
        pass