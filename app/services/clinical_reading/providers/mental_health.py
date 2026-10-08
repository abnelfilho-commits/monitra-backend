"""Translate authorized contextual Check-ins into the shared ClinicalReading."""
from copy import deepcopy
from app.services.mental_health_engine import describe_checkins, summarize_sources
from ..models import ClinicalReading


def read_mental_health(*, pessoa_id, contexto_assistencial_id, care_line, checkins, assessments=None, diagnoses=(), interventions=()):
    if any(record.respondente_pessoa_id != pessoa_id for record in checkins):
        raise ValueError("Check-in respondent differs from contextual identity.")
    if any(r.pessoa_id != pessoa_id or r.contexto_assistencial_id != contexto_assistencial_id or r.modulo_id != 3
           for r in (*diagnoses, *interventions)):
        raise ValueError("Professional record differs from contextual identity.")
    result = describe_checkins(checkins)
    # Add only after the unchanged Check-in engine has completed its narrative.
    result["evidence"]["assessments"] = deepcopy(assessments) if assessments is not None else {}
    result['summary'], result['metadata']['summary_sources'] = summarize_sources(result, diagnoses, interventions)
    return ClinicalReading(pessoa_id=pessoa_id, contexto_assistencial_id=contexto_assistencial_id,
                           care_line=care_line, **result)
