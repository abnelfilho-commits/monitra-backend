from typing import Callable, Mapping, Optional, Union

from sqlalchemy.orm import Session

from app.services.care_lines import (
    CareLineCapabilityNotSupported, CareLineDefinition, CareLineResolver,
)
from app.services.care_lines.registry import CAP_CLINICAL_READING
from .models import ClinicalReading
from .providers import READING_PROVIDERS
from .compatibility import build_report_context, get_neuro_reading

ReadingProvider = Callable[[Session, int, CareLineDefinition], ClinicalReading]


class ClinicalReadingService:
    """Resolve context and dispatch. Callers retain patient/clinic authorization."""

    def __init__(self, resolver: Optional[CareLineResolver] = None,
                 providers: Optional[Mapping[str, ReadingProvider]] = None):
        self.resolver = resolver if resolver is not None else CareLineResolver()
        self.providers = dict(READING_PROVIDERS if providers is None else providers)

    def get_reading(self, db: Session, patient_id: int,
                    requested_line: Optional[Union[str, int]] = None) -> ClinicalReading:
        line = self.resolver.resolve(db, patient_id, requested_line, CAP_CLINICAL_READING)
        provider = self.providers.get(line.code)
        if provider is None:
            raise CareLineCapabilityNotSupported("Linha de cuidado sem provider de leitura clínica.")
        return provider(db, patient_id, line)

    # Compatibility only: existing Neuro report callers retain the raw dictionary.
    get_neuro_reading = staticmethod(get_neuro_reading)
    build_report_context = staticmethod(build_report_context)
