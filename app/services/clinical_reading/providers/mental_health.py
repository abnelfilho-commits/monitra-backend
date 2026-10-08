"""Translate authorized contextual Check-ins into the shared ClinicalReading."""
from copy import deepcopy
from app.services.mental_health_engine import describe_checkins
from ..models import ClinicalReading


def read_mental_health(*, pessoa_id, contexto_assistencial_id, care_line, checkins, assessments=None):
    if any(record.respondente_pessoa_id != pessoa_id for record in checkins):
        raise ValueError("Check-in respondent differs from contextual identity.")
    result = describe_checkins(checkins)
    # Add only after the unchanged Check-in engine has completed its narrative.
    result["evidence"]["assessments"] = deepcopy(assessments) if assessments is not None else {}
    return ClinicalReading(pessoa_id=pessoa_id, contexto_assistencial_id=contexto_assistencial_id,
                           care_line=care_line, **result)
