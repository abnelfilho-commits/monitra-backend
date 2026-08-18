"""
Provider responsável pela Leitura Clínica Oficial do paciente.
"""

from app.services.clinical_reading_service import (
    ClinicalReadingService,
)

from ..base_provider import (
    BaseProvider,
    ProviderResult,
)
from ..context import ReportContext


class ClinicalEngineProvider(BaseProvider):
    """
    Consome a Leitura Clínica Oficial produzida
    pelo Engine especializado do módulo.

    Não recalcula inteligência clínica.
    """

    code = "CLINICAL_ENGINE_PROVIDER"
    version = "1.0"
    required = False

    def supports(
        self,
        context: ReportContext,
    ) -> bool:
        return bool(context.module)

    def collect(
        self,
        context: ReportContext,
    ) -> ProviderResult:

        if context.db is None:
            raise ValueError(
                "ReportContext.db não informado."
            )

        if not context.module:
            raise ValueError(
                "ReportContext.module não informado."
            )

        reading = ClinicalReadingService.build_report_context(
            db=context.db,
            patient_id=context.subject_id,
            module=context.module,
        )

        context.add_official_reading(
            context.module.upper(),
            reading,
        )

        return ProviderResult(
            provider_code=self.code,
            provider_version=self.version,
            data=reading,
            metadata={
                "module": context.module.upper(),
                "has_reading": bool(reading),
            },
        )