"""Institutional write contracts; clinical values belong to providers."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
from app.services.care_lines import CareLineDefinition, CareOrigin


class ActorType(str, Enum):
    PROFESSIONAL = 'PROFESSIONAL'
    RESPONSIBLE = 'RESPONSIBLE'
    SYSTEM = 'SYSTEM'


@dataclass(frozen=True)
class ActorRef:
    type: ActorType
    id: Optional[int] = None

    def __post_init__(self):
        object.__setattr__(self, 'type', ActorType(self.type))
        if self.id is not None and (type(self.id) is not int or self.id <= 0):
            raise ValueError('Actor id must be a positive integer.')
        if self.type == ActorType.RESPONSIBLE and self.id is None:
            raise ValueError('Responsible actor requires an id.')
        if self.type == ActorType.SYSTEM and self.id is not None:
            raise ValueError('System has no user/responsible database identity.')


@dataclass(frozen=True)
class DailyRecordSubmission:
    patient_id: int
    requested_care_line: Optional[Union[str, int]]
    reference_date: date
    origin: CareOrigin
    actor: ActorRef
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if type(self.patient_id) is not int or self.patient_id <= 0:
            raise ValueError('Patient id must be a positive integer.')
        if type(self.reference_date) is not date:
            raise ValueError('Explicit clinical date is required.')
        if not isinstance(self.actor, ActorRef):
            raise TypeError('Typed actor is required.')
        object.__setattr__(self, 'origin', CareOrigin(self.origin))
        object.__setattr__(self, 'payload', deepcopy(dict(self.payload)))
        expected = {
            CareOrigin.PROFISSIONAL: ActorType.PROFESSIONAL,
            CareOrigin.RESPONSAVEL_APP: ActorType.RESPONSIBLE,
            CareOrigin.RESPONSAVEL_WHATSAPP: ActorType.RESPONSIBLE,
            CareOrigin.SISTEMA: ActorType.SYSTEM,
        }
        if self.actor.type != expected[self.origin]:
            raise ValueError('Actor type is incompatible with origin.')


@dataclass(frozen=True)
class DailyRecordResult:
    record_id: int
    patient_id: int
    care_line: CareLineDefinition
    reference_date: date
    origin: CareOrigin
    created_at: Optional[datetime]
