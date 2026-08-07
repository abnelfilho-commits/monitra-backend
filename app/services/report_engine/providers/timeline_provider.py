"""
Provider responsável pela coleta da Timeline Clínica.
"""

from app.services.timeline_service import TimelineService

from ..base_provider import (
    BaseProvider,
    ProviderResult,
)
from ..context import ReportContext


class TimelineProvider(BaseProvider):
    """
    Coleta a Timeline Clínica consolidada do paciente.
    """

    code = "TIMELINE_PROVIDER"
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

        timeline = TimelineService.get_timeline(
            db=context.db,
            patient_id=context.subject_id,
        )

        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=timeline,
            metadata={
                "total_events": len(timeline),
            },
        )