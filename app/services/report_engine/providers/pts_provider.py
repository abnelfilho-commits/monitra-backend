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
            module_id=context.care_line.module_id,
        )

        # Plan dates identify overlap; statuses/objectives remain CURRENT facts.
        def overlaps(item):
            start, end = item.get('data_inicio'), item.get('data_fim')
            return (not start or start <= context.period_end.isoformat()) and (not end or end >= context.period_start.isoformat())
        history = [p for p in pts_context['historico'] if overlaps(p)]
        for plan in history:
            plan['planejamentos'] = [p for p in plan['planejamentos'] if overlaps(p)]
        pts_context = {'historico': history, 'total_pts': len(history),
                       'pts_ativo': next((p for p in history if p['status'] == 'ATIVO'), None)}
        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=pts_context,
            metadata={
                "total_pts": pts_context["total_pts"],
                "temporal_scope": "CURRENT_CARE_PLAN_CONTEXT_NOT_HISTORICAL_AS_OF",
                "has_active_pts": (
                    pts_context["pts_ativo"] is not None
                ),
            },
        )