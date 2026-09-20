"""Institutional current reading; no historical recalculation."""
from app.services.clinical_reading import ClinicalReadingService
from ..base_provider import BaseProvider, ProviderResult


class ClinicalEngineProvider(BaseProvider):
    code = 'CLINICAL_ENGINE_PROVIDER'
    version = '2.0'
    required = True

    def collect(self, context):
        reading = ClinicalReadingService().get_reading(context.db, context.subject_id, context.module)
        context.clinical_reading = reading
        context.add_official_reading(reading.care_line.code, reading)
        return ProviderResult(provider_code=self.code, provider_version=self.version, data=reading,
            metadata={'scope':'CURRENT', 'reference_date': reading.reference_date})


class NeuroClinicalEngineProvider(ClinicalEngineProvider):
    """Shape adapter for existing Neuro knowledge; values remain line-authored."""
    def collect(self, context):
        result = super().collect(context)
        reading = result.data
        legacy = {**reading.metadata, 'risco_atual': reading.risk, 'tendencia': reading.trend,
            'resumo_clinico': reading.summary, 'momento_clinico': reading.clinical_state,
            'alertas': reading.alerts, 'ultimo_registro': reading.reference_date}
        context.add_official_reading(reading.care_line.code, legacy)
        result.data = legacy
        return result
