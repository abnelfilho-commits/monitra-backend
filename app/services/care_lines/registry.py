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
        CAP_CLINICAL_READING: CareLineCapabilityStatus.ACTIVE,
        CAP_TIMELINE: CareLineCapabilityStatus.ACTIVE,
        CAP_INTERVENTIONS: CareLineCapabilityStatus.ACTIVE,
        CAP_WHATSAPP: CareLineCapabilityStatus.ACTIVE,
        CAP_REPORT: CareLineCapabilityStatus.PLANNED,
        CAP_COCKPIT: CareLineCapabilityStatus.ACTIVE,
    },
)


class CareLineRegistry:
    def __init__(self, definitions: Optional[Iterable[CareLineDefinition]] = None):
        items = tuple((NEURO, CARDIO) if definitions is None else definitions)
        self._by_alias: Dict[str, CareLineDefinition] = {}
        self._by_module_id: Dict[int, CareLineDefinition] = {}
        for item in items:
            aliases = {item.code.strip().casefold(), item.slug.strip().casefold()}
            if item.module_id in self._by_module_id:
                raise ValueError("Duplicate care line module_id.")
            if any(alias in self._by_alias or alias.isdecimal() for alias in aliases):
                raise ValueError("Duplicate or numeric care line alias.")
            self._by_module_id[item.module_id] = item
            for alias in aliases:
                self._by_alias[alias] = item

    def all(self) -> Iterable[CareLineDefinition]:
        return tuple(self._by_module_id.values())

    def get(self, identifier: Union[str, int]) -> Optional[CareLineDefinition]:
        if type(identifier) is int:
            return self._by_module_id.get(identifier)

        if not isinstance(identifier, str):
            return None
        value = identifier.strip()
        if not value:
            return None

        if value.isdecimal():
            by_id = self._by_module_id.get(int(value))
            if by_id is not None:
                return by_id

        return self._by_alias.get(value.casefold())


care_line_registry = CareLineRegistry()
