"""Translate authorized contextual Check-ins into the shared ClinicalReading."""
from app.services.mental_health_engine import describe_checkins
from ..models import ClinicalReading


def read_mental_health(*, pessoa_id, contexto_assistencial_id, care_line, checkins):
    if any(record.respondente_pessoa_id != pessoa_id for record in checkins):
        raise ValueError("Check-in respondent differs from contextual identity.")
    result = describe_checkins(checkins)
    return ClinicalReading(pessoa_id=pessoa_id, contexto_assistencial_id=contexto_assistencial_id,
                           care_line=care_line, **result)
