from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from .definitions import CareLineDefinition


class CareOrigin(str, Enum):
    PROFISSIONAL = "PROFISSIONAL"
    RESPONSAVEL_APP = "RESPONSAVEL_APP"
    RESPONSAVEL_WHATSAPP = "RESPONSAVEL_WHATSAPP"
    SISTEMA = "SISTEMA"


@dataclass(frozen=True)
class CareContext:
    patient_id: int
    care_line: CareLineDefinition
    clinic_id: Optional[int] = None
    actor_id: Optional[int] = None
    actor_role: Optional[str] = None
    origin: Optional[CareOrigin] = None
    reference_date: Optional[date] = None

    def __post_init__(self) -> None:
        if not isinstance(self.care_line, CareLineDefinition):
            raise TypeError("care_line must be a resolved CareLineDefinition.")
        if self.origin is not None:
            object.__setattr__(self, "origin", CareOrigin(self.origin))
