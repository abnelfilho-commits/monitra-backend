"""Institutional structure; classification values remain care-line authored."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.services.care_lines import CareLineDefinition


@dataclass(frozen=True)
class ClinicalReading:
    patient_id: Optional[int] = None
    care_line: Optional[CareLineDefinition] = None
    reference_date: Optional[date] = None
    risk: Optional[str] = None
    trend: Optional[str] = None
    summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    clinical_state: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    alerts: Optional[List[str]] = None

    pessoa_id: Optional[int] = None
    contexto_assistencial_id: Optional[int] = None

    def __post_init__(self) -> None:
        contextual = self.pessoa_id is not None or self.contexto_assistencial_id is not None
        ids = (self.pessoa_id, self.contexto_assistencial_id) if contextual else (self.patient_id,)
        if (contextual and self.patient_id is not None) or any(type(i) is not int or i <= 0 for i in ids):
            raise ValueError("Use either a positive patient_id or positive pessoa_id and contexto_assistencial_id.")
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
