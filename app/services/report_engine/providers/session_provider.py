"""
Provider responsável pela coleta do contexto de Sessões Assistenciais.
"""

from app.services.assistential_session_service import (
    AssistentialSessionService,
)

from ..base_provider import (
    BaseProvider,
    ProviderResult,
)
from ..context import ReportContext


class SessionProvider(BaseProvider):
    """
    Coleta o histórico e o resumo das Sessões Assistenciais do paciente.
    """

    code = "SESSION_PROVIDER"
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

        session_context = (
            AssistentialSessionService.build_report_context(
                db=context.db,
                patient_id=context.subject_id,
            )
        )

        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=session_context,
            metadata={
                "total_sessoes": session_context["total_sessoes"],
                "realizadas": session_context["realizadas"],
                "agendadas": session_context["agendadas"],
                "canceladas": session_context["canceladas"],
                "faltas": session_context["faltas"],
            },
        )