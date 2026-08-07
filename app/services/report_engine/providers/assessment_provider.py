"""
Provider responsável pela coleta das Avaliações Clínicas.
"""

from app.services.timeline_service import TimelineService

from ..base_provider import (
    BaseProvider,
    ProviderResult,
)
from ..context import ReportContext


class AssessmentProvider(BaseProvider):
    """
    Coleta as avaliações clínicas do paciente.
    """

    code = "ASSESSMENT_PROVIDER"
    version = "1.0"
    required = False

    def collect(
        self,
        context: ReportContext,
    ) -> ProviderResult:

        if context.db is None:
            raise ValueError(
                "ReportContext.db não informado."
            )

        assessments = TimelineService.get_assessments(
            db=context.db,
            patient_id=context.subject_id,
        )

        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=assessments,
            metadata={
                "total_assessments": len(assessments),
            },
        )