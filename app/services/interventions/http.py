"""Legacy HTTP compatibility; never serialize the ORM or institutional record directly."""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.services.care_lines.exceptions import CareLineError, AmbiguousCareLine
from .exceptions import InterventionError, InterventionNotFound, InterventionIdentityConflict, InterventionOperationNotSupported


def call(operation):
    try:
        return operation()
    except (InterventionError, CareLineError) as exc:
        status = 400
        if isinstance(exc, InterventionNotFound):
            status = 404
        elif isinstance(exc, (InterventionIdentityConflict, AmbiguousCareLine)):
            status = 409
        elif isinstance(exc, InterventionOperationNotSupported):
            status = 400
        raise HTTPException(status_code=status, detail=exc.code + ': ' + str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail='Dados inválidos para intervenção.') from exc


def generic_response(record):
    return {'id': record.source_id, 'paciente_id': record.patient_id,
        'profissional_id': record.actor['id'] if record.actor else None,
        'tipo': record.type, 'descricao': record.narrative,
        'data_intervencao': record.reference_datetime, 'created_at': record.created_at}


def cardio_response(record):
    return {'id': record.source_id, 'tipo': record.type, 'descricao': record.narrative,
        'prioridade': record.metadata['priority'],
        'created_at': record.created_at.isoformat() if record.created_at else None}
