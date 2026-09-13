"""Institutional structure; classification values remain care-line authored."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.services.care_lines import CareLineDefinition


@dataclass(frozen=True)
class ClinicalReading:
    patient_id: int
    care_line: CareLineDefinition
    reference_date: Optional[date]
    risk: Optional[str]
    trend: Optional[str]
    summary: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    clinical_state: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    alerts: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if type(self.patient_id) is not int or self.patient_id <= 0:
            raise ValueError("patient_id must be a positive integer.")
        if not isinstance(self.care_line, CareLineDefinition):
            raise TypeError("care_line must be a resolved CareLineDefinition.")
        if self.reference_date is not None and type(self.reference_date) is not date:
            raise TypeError("reference_date must be a clinical date, not a timestamp.")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping.")
        object.__setattr__(self, "metadata", dict(self.metadata))
        # Defensive copies also isolate nested provider data from consumers.
        for name in ("metadata", "clinical_state", "evidence", "alerts"):
            object.__setattr__(self, name, deepcopy(getattr(self, name)))
