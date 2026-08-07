"""
Provider responsável pela coleta do contexto do PTS.
"""

from app.services.pts_service import PTSService

from ..base_provider import (
    BaseProvider,
    ProviderResult,
)
from ..context import ReportContext


class PTSProvider(BaseProvider):
    """
    Coleta o PTS, seus objetivos e planejamentos assistenciais.
    """

    code = "PTS_PROVIDER"
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

        pts_context = PTSService.build_report_context(
            db=context.db,
            patient_id=context.subject_id,
        )

        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=pts_context,
            metadata={
                "total_pts": pts_context["total_pts"],
                "has_active_pts": (
                    pts_context["pts_ativo"] is not None
                ),
            },
        )