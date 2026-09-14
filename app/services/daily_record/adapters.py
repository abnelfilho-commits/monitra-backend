"""Legacy HTTP payload translation; not an authorization layer."""
from fastapi import HTTPException
from app.models.modular import CampoFormulario, FormularioModulo, RegistroLongitudinal
from app.services.care_lines import CareOrigin
from app.services.care_lines.exceptions import CareLineError
from . import ActorRef, ActorType, DailyRecordSubmission, DailyRecordService
from .exceptions import DailyRecordError, DailyRecordIdentityConflict
from .providers.common import resolve_form


def call_write(db, submission, record_id=None):
    try:
        service = DailyRecordService()
        return (service.create(db, submission) if record_id is None
                else service.update(db, record_id, submission))
    except (DailyRecordError, CareLineError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def is_daily(db, form_id):
    form = db.query(FormularioModulo).filter(FormularioModulo.id == form_id).first()
    return form is not None and form.tipo == 'REGISTRO_DIARIO'


def write_legacy_longitudinal(db, payload, record_id=None):
    # Existing professional routes provide no authenticated identity. Do not invent one.
    try:
        service = DailyRecordService()
        line = service.resolver.resolve(db, payload.paciente_id, payload.modulo_id, 'daily_record')
        form = resolve_form(db, line)
        if form.id != payload.formulario_id:
            raise DailyRecordIdentityConflict('Payload form does not match resolved Daily Record form.')
        fields = db.query(CampoFormulario).filter(CampoFormulario.formulario_id == form.id,
                                                 CampoFormulario.ativo.is_(True)).all()
        by_id = {item.id: item.nome_campo for item in fields}
        values = {}
        for item in payload.respostas:
            if item.campo_id not in by_id or by_id[item.campo_id] in values:
                raise DailyRecordError('Invalid or duplicate answer field.')
            values[by_id[item.campo_id]] = item.valor
        if payload.origem != 'PROFISSIONAL':
            raise DailyRecordError('This compatibility adapter supports professional submissions only.')
        submission = DailyRecordSubmission(payload.paciente_id, line.code, payload.data_registro,
            CareOrigin.PROFISSIONAL, ActorRef(ActorType.PROFESSIONAL), values)
        return call_write(db, submission, record_id)
    except (DailyRecordError, CareLineError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
