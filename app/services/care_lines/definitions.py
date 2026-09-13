from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


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
    capabilities: Mapping[str, CareLineCapabilityStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.slug.strip() or not self.display_name.strip():
            raise ValueError("Care line names must not be empty.")
        if type(self.module_id) is not int or self.module_id <= 0:
            raise ValueError("module_id must be a positive integer.")
        if type(self.active) is not bool:
            raise TypeError("active must be a boolean.")
        capabilities = dict(self.capabilities)
        if any(not isinstance(key, str) or not key.strip() for key in capabilities):
            raise ValueError("Capability names must not be empty.")
        if any(not isinstance(value, CareLineCapabilityStatus) for value in capabilities.values()):
            raise TypeError("Capabilities must use CareLineCapabilityStatus values.")
        object.__setattr__(self, "capabilities", MappingProxyType(capabilities))

    def capability_status(self, capability: str) -> CareLineCapabilityStatus:
        return self.capabilities.get(
            capability,
            CareLineCapabilityStatus.UNAVAILABLE,
        )

    def supports(self, capability: str) -> bool:
        return self.capability_status(capability) == CareLineCapabilityStatus.ACTIVE
