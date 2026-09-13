from dataclasses import dataclass
from datetime import date
from typing import Optional

from .definitions import CareLineDefinition


@dataclass(frozen=True)
class CareContext:
    patient_id: int
    care_line: CareLineDefinition
    clinic_id: Optional[int] = None
    actor_id: Optional[int] = None
    actor_role: Optional[str] = None
    origin: Optional[str] = None
    reference_date: Optional[date] = None
