"""
Provider responsável pela coleta dos dados básicos do paciente.
"""

from app.services.patient_service import PatientService

from ..base_provider import (
    BaseProvider,
    ProviderResult,
)
from ..context import ReportContext


class PatientProvider(BaseProvider):
    """
    Coleta o contexto básico do paciente.
    """

    code = "PATIENT_PROVIDER"
    version = "1.0"
    required = True

    def collect(
        self,
        context: ReportContext,
    ) -> ProviderResult:

        if context.db is None:
            raise ValueError(
                "ReportContext.db não informado."
            )

        patient = PatientService.build_report_context(
            db=context.db,
            patient_id=context.subject_id,
        )

        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=patient,
        )