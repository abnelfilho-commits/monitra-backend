"""
Knowledge Engine responsável pela síntese
das Avaliações Clínicas.
"""

from ..context import ReportContext

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import AssessmentSummaryModel


class AssessmentSummaryEngine(BaseKnowledgeEngine):
    """
    Consolida as avaliações clínicas disponíveis
    durante o acompanhamento longitudinal.
    """

    code = "ASSESSMENT_SUMMARY_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        assessments = context.collected_data.get(
            "ASSESSMENT_PROVIDER",
            [],
        )

        normalized = []

        for assessment in assessments:

            normalized.append(
                {
                    "id": assessment.get("id"),
                    "date": assessment.get("data"),
                    "instrument": assessment.get("instrumento"),
                    "score": (
                        float(assessment.get("score"))
                        if assessment.get("score") is not None
                        else None
                    ),
                    "classification": assessment.get(
                        "classificacao"
                    ),
                    "description": assessment.get(
                        "descricao"
                    ),
                    "source": assessment.get(
                        "origem"
                    ),
                }
            )

        model = AssessmentSummaryModel(
            total_assessments=len(normalized),
            assessments=normalized,
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )