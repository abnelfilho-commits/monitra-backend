"""
Knowledge Engine responsável pelo Resumo Executivo.
"""

from ..context import ReportContext
from ..models import ReportSection
from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import ExecutiveSummaryModel

class ExecutiveSummaryEngine(BaseKnowledgeEngine):
    """
    Produz o Resumo Executivo oficial do relatório.
    """

    code = "EXECUTIVE_SUMMARY_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        patient = (
            context.collected_data
            .get("PATIENT_PROVIDER", {})
        )

        patient_name = (
            patient.get("name")
            or "Paciente"
        )

        text = (
            f"O paciente {patient_name} possui informações "
            "clínicas suficientes para geração do relatório "
            "longitudinal institucional."
        )

        model = ExecutiveSummaryModel(
            clinical_status="AVAILABLE",
            summary=text,
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )