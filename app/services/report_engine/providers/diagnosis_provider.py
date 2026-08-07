"""
Provider responsável pela coleta do contexto diagnóstico.
"""

from app.services.diagnostico_service import DiagnosticoService

from ..base_provider import (
    BaseProvider,
    ProviderResult,
)
from ..context import ReportContext


class DiagnosisProvider(BaseProvider):
    """
    Coleta o histórico diagnóstico do paciente.
    """

    code = "DIAGNOSIS_PROVIDER"
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

        diagnosis_context = DiagnosticoService.build_report_context(
            db=context.db,
            patient_id=context.subject_id,
        )

        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=diagnosis_context,
            metadata={
                "total_diagnosticos": (
                    diagnosis_context["total_diagnosticos"]
                ),
                "total_ativos": len(
                    diagnosis_context["ativos"]
                ),
            },
        )