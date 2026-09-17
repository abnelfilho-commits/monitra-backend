"""Structural contracts. Clinical classifications do not belong here."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Union

from app.services.care_lines import CareLineDefinition
from app.services.daily_record.models import ActorRef, ActorType
from app.services.timeline.models import SourceType, CareLineAssociation
from .exceptions import InvalidInterventionPayload


def validate_content(kind, narrative, reference):
    if not isinstance(kind, str):
        raise InvalidInterventionPayload('Tipo deve ser texto.')
    if narrative is not None and not isinstance(narrative, str):
        raise InvalidInterventionPayload('Descrição deve ser texto ou nula.')
    if reference is not None and not isinstance(reference, datetime):
        raise InvalidInterventionPayload('Data clínica deve ser datetime.')


@dataclass(frozen=True)
class InterventionSubmission:
    patient_id: int
    requested_care_line: Optional[Union[str, int]]
    actor: ActorRef
    type: str
    narrative: Optional[str] = None
    reference_datetime: Optional[datetime] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if type(self.patient_id) is not int or self.patient_id <= 0:
            raise InvalidInterventionPayload('Paciente inválido.')
        if not isinstance(self.actor, ActorRef) or self.actor.type != ActorType.PROFESSIONAL or self.actor.id is None:
            raise InvalidInterventionPayload('Executor autenticado é obrigatório.')
        validate_content(self.type, self.narrative, self.reference_datetime)
        if not isinstance(self.payload, dict):
            raise InvalidInterventionPayload('Payload deve ser um mapping.')
        object.__setattr__(self, 'payload', deepcopy(self.payload))


@dataclass(frozen=True)
class InterventionRecord:
    source_type: SourceType
    source_id: int
    patient_id: int
    care_line: CareLineDefinition
    module_id: int
    care_line_association: CareLineAssociation
    actor: Optional[Mapping[str, Any]]
    type: str
    narrative: Optional[str]
    reference_datetime: Optional[datetime]
    created_at: Optional[datetime]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if (not isinstance(self.care_line, CareLineDefinition)
                or self.module_id != self.care_line.module_id
                or self.care_line_association != CareLineAssociation.EXPLICIT):
            raise InvalidInterventionPayload('Intervenção exige linha persistida explícita.')
        object.__setattr__(self, 'metadata', deepcopy(dict(self.metadata)))
        if self.actor is not None:
            object.__setattr__(self, 'actor', deepcopy(dict(self.actor)))


@dataclass(frozen=True)
class InterventionUpdate:
    type: str
    narrative: Optional[str]
    reference_datetime: datetime

    def __post_init__(self):
        validate_content(self.type, self.narrative, self.reference_datetime)
        if self.reference_datetime is None:
            raise InvalidInterventionPayload('Data clínica é obrigatória.')
