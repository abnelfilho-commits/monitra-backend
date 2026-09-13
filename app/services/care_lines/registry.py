from typing import Dict, Iterable, Optional, Union

from .definitions import CareLineCapabilityStatus, CareLineDefinition


CAP_DAILY_RECORD = "daily_record"
CAP_CLINICAL_ENGINE = "clinical_engine"
CAP_CLINICAL_READING = "clinical_reading"
CAP_TIMELINE = "timeline"
CAP_INTERVENTIONS = "interventions"
CAP_WHATSAPP = "whatsapp"
CAP_REPORT = "report"
CAP_COCKPIT = "cockpit"


NEURO = CareLineDefinition(
    code="NEURO",
    slug="neurodesenvolvimento",
    module_id=1,
    display_name="Neurodesenvolvimento",
    capabilities={
        CAP_DAILY_RECORD: CareLineCapabilityStatus.ACTIVE,
        CAP_CLINICAL_ENGINE: CareLineCapabilityStatus.ACTIVE,
        CAP_CLINICAL_READING: CareLineCapabilityStatus.ACTIVE,
        CAP_TIMELINE: CareLineCapabilityStatus.ACTIVE,
        CAP_INTERVENTIONS: CareLineCapabilityStatus.ACTIVE,
        CAP_WHATSAPP: CareLineCapabilityStatus.ACTIVE,
        CAP_REPORT: CareLineCapabilityStatus.ACTIVE,
        CAP_COCKPIT: CareLineCapabilityStatus.ACTIVE,
    },
)

CARDIO = CareLineDefinition(
    code="CARDIO",
    slug="cardiometabolico",
    module_id=2,
    display_name="Cardiometabólico",
    capabilities={
        CAP_DAILY_RECORD: CareLineCapabilityStatus.ACTIVE,
        CAP_CLINICAL_ENGINE: CareLineCapabilityStatus.ACTIVE,
        CAP_CLINICAL_READING: CareLineCapabilityStatus.PLANNED,
        CAP_TIMELINE: CareLineCapabilityStatus.ACTIVE,
        CAP_INTERVENTIONS: CareLineCapabilityStatus.ACTIVE,
        CAP_WHATSAPP: CareLineCapabilityStatus.PLANNED,
        CAP_REPORT: CareLineCapabilityStatus.PLANNED,
        CAP_COCKPIT: CareLineCapabilityStatus.PLANNED,
    },
)


class CareLineRegistry:
    def __init__(self, definitions: Optional[Iterable[CareLineDefinition]] = None):
        items = tuple(definitions or (NEURO, CARDIO))
        self._by_code: Dict[str, CareLineDefinition] = {
            item.code.upper(): item for item in items
        }
        self._by_slug: Dict[str, CareLineDefinition] = {
            item.slug.lower(): item for item in items
        }
        self._by_module_id: Dict[int, CareLineDefinition] = {
            item.module_id: item for item in items
        }

    def all(self) -> Iterable[CareLineDefinition]:
        return tuple(self._by_code.values())

    def get(self, identifier: Union[str, int]) -> Optional[CareLineDefinition]:
        if isinstance(identifier, int):
            return self._by_module_id.get(identifier)

        value = str(identifier).strip()
        if not value:
            return None

        if value.isdigit():
            by_id = self._by_module_id.get(int(value))
            if by_id is not None:
                return by_id

        return self._by_code.get(value.upper()) or self._by_slug.get(value.lower())


care_line_registry = CareLineRegistry()
