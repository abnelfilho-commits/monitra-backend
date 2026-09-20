"""Read-only Timeline V1 contracts. Callers authorize patient access."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Dict, Optional, Union
from app.services.care_lines import CareLineDefinition


class SourceType(str, Enum):
    LONGITUDINAL_RECORD = 'LONGITUDINAL_RECORD'
    GENERIC_INTERVENTION = 'GENERIC_INTERVENTION'
    CARDIO_INTERVENTION = 'CARDIO_INTERVENTION'
    CLINICAL_ASSESSMENT = 'CLINICAL_ASSESSMENT'
    ASSISTENTIAL_SESSION = 'ASSISTENTIAL_SESSION'
    DIAGNOSIS = 'DIAGNOSIS'


class EventType(str, Enum):
    DAILY_RECORD = 'DAILY_RECORD'
    INTERVENTION = 'INTERVENTION'
    ASSESSMENT = 'ASSESSMENT'
    SESSION_COMPLETED = 'SESSION_COMPLETED'
    DIAGNOSIS = 'DIAGNOSIS'


class CareLineAssociation(str, Enum):
    EXPLICIT = 'EXPLICIT'
    DERIVED = 'DERIVED'
    UNASSIGNED = 'UNASSIGNED'
    TRANSVERSAL = 'TRANSVERSAL'


class TemporalPrecision(str, Enum):
    DATE = 'DATE'
    DATETIME = 'DATETIME'


class TimelineScope(str, Enum):
    PATIENT = 'PATIENT'
    CARE_LINE = 'CARE_LINE'


class TimelineReadMode(str, Enum):
    FULL_HISTORY = 'FULL_HISTORY'
    BOUNDED = 'BOUNDED'


@dataclass(frozen=True)
class TimelineQuery:
    patient_id: int
    scope: TimelineScope = TimelineScope.PATIENT
    requested_care_line: Optional[Union[str, int]] = None
    mode: TimelineReadMode = TimelineReadMode.FULL_HISTORY
    limit: Optional[int] = None

    def __post_init__(self):
        object.__setattr__(self, 'scope', TimelineScope(self.scope))
        object.__setattr__(self, 'mode', TimelineReadMode(self.mode))
        if type(self.patient_id) is not int or self.patient_id <= 0:
            raise ValueError('Positive patient identity required.')
        if self.scope == TimelineScope.CARE_LINE and self.requested_care_line is None:
            raise ValueError('CARE_LINE requires an explicit line selection.')
        if self.scope == TimelineScope.PATIENT and self.requested_care_line is not None:
            raise ValueError('PATIENT must not silently filter a requested line.')
        if self.mode == TimelineReadMode.BOUNDED:
            if type(self.limit) is not int or self.limit <= 0:
                raise ValueError('BOUNDED requires a positive limit.')
        elif self.limit is not None:
            raise ValueError('FULL_HISTORY does not accept a limit.')


@dataclass(frozen=True)
class TimelineEvent:
    source_type: SourceType
    source_id: int
    patient_id: int
    care_line: Optional[CareLineDefinition]
    care_line_association: CareLineAssociation
    event_type: EventType
    title: str
    reference_date: Optional[date] = None
    reference_time: Optional[time] = None
    temporal_precision: Optional[TemporalPrecision] = None
    created_at: Optional[datetime] = None
    summary: Optional[str] = None
    origin: Optional[str] = None
    actor: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in (self.source_id, self.patient_id)):
            raise ValueError('Positive source and patient identities required.')
        if self.reference_time is not None and not isinstance(self.reference_time, time):
            raise TypeError('Clinical time must be a time value.')
        if self.created_at is not None and not isinstance(self.created_at, datetime):
            raise TypeError('Creation timestamp must be datetime.')
        for name, enum in (('source_type', SourceType), ('event_type', EventType),
                           ('care_line_association', CareLineAssociation)):
            object.__setattr__(self, name, enum(getattr(self, name)))
        if self.care_line is not None and not isinstance(self.care_line, CareLineDefinition):
            raise TypeError('Care line must be resolved, not a module string.')
        if self.care_line_association == CareLineAssociation.UNASSIGNED and self.care_line is not None:
            raise ValueError('UNASSIGNED cannot carry a care line.')
        if self.reference_date is not None and type(self.reference_date) is not date:
            raise TypeError('Clinical reference must be a date.')
        expected = (TemporalPrecision.DATETIME if self.reference_time is not None
                    else TemporalPrecision.DATE if self.reference_date is not None else None)
        if self.reference_time is not None and self.reference_date is None:
            raise ValueError('Clinical time requires clinical date.')
        if self.temporal_precision is not None:
            object.__setattr__(self, 'temporal_precision', TemporalPrecision(self.temporal_precision))
        if self.temporal_precision != expected:
            raise ValueError('Temporal precision must match factual reference fields.')
        object.__setattr__(self, 'metadata', deepcopy(dict(self.metadata)))
        object.__setattr__(self, 'actor', deepcopy(self.actor))


def event_order_key(event):
    """Calendar order, not invented UTC instants. Ascending key yields newest first."""
    day = event.reference_date or (event.created_at.date() if event.created_at else None)
    clock = event.reference_time
    micros = (clock.hour * 3600 + clock.minute * 60 + clock.second) * 1000000 + clock.microsecond if clock else 0
    return (-(day.toordinal() if day else 0), -int(event.reference_date is not None),
            -int(clock is not None), -micros, event.source_type.value, event.source_id)
