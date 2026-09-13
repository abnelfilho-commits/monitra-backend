from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class CareLineCapabilityStatus(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class CareLineDefinition:
    code: str
    slug: str
    module_id: int
    display_name: str
    active: bool = True
    capabilities: Dict[str, CareLineCapabilityStatus] = field(default_factory=dict)

    def capability_status(self, capability: str) -> CareLineCapabilityStatus:
        return self.capabilities.get(
            capability,
            CareLineCapabilityStatus.UNAVAILABLE,
        )

    def supports(self, capability: str) -> bool:
        return self.capability_status(capability) == CareLineCapabilityStatus.ACTIVE
