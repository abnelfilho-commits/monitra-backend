"""Authorized channel boundary shared by line-owned questionnaires."""
from datetime import date, timedelta
from app.services.daily_record.concurrency import lock_context
from app.models.paciente import Paciente
from app.models.responsavel import Responsavel
from app.models.responsavel_paciente import ResponsavelPaciente
from app.models.modular import RegistroLongitudinal
from app.services.care_lines import care_line_resolver, care_line_registry, CareOrigin
from app.services.care_lines.exceptions import CareLineError
from app.services.daily_record import DailyRecordService, DailyRecordSubmission, ActorRef, ActorType
from app.services.daily_record.exceptions import DailyRecordError
from app.services.daily_record.providers.common import resolve_form

RESPONSIBLE_ORIGINS = ('RESPONSAVEL', 'RESPONSAVEL_APP', 'RESPONSAVEL_WHATSAPP')


def authorized_lines(db, responsible_id, patient_id):
    lock_context(db, patient_id, responsible_id)
    responsible = db.query(Responsavel).filter_by(id=responsible_id, ativo=True).populate_existing().first()
    patient = db.query(Paciente).filter_by(id=patient_id, ativo=True).populate_existing().first()
    link = db.query(ResponsavelPaciente).filter_by(responsavel_id=responsible_id,
        paciente_id=patient_id, ativo=True).populate_existing().with_for_update(key_share=True).first()
    if responsible is None or patient is None or link is None:
        raise ValueError('Vínculo assistencial indisponível.')
    if responsible.clinica_id is not None and responsible.clinica_id != patient.clinica_id:
        raise ValueError('Vínculo assistencial indisponível.')
    lines = []
    for line in care_line_registry.all():
        try:
            resolved = care_line_resolver.resolve(db, patient_id, line.code, 'daily_record')
            if resolved.supports('whatsapp'):
                lines.append(resolved)
        except CareLineError:
            continue
    return lines


def record_exists(db, patient_id, line, reference_date, responsible_id=None):
    query = db.query(RegistroLongitudinal.id).filter(
        RegistroLongitudinal.paciente_id == patient_id,
        RegistroLongitudinal.modulo_id == line.module_id,
        RegistroLongitudinal.data_registro == reference_date,
        RegistroLongitudinal.origem.in_(RESPONSIBLE_ORIGINS))
    # Preserve Cardio APP's per-responsible duplicate policy; Neuro is per patient.
    if line.code == 'CARDIO':
        query = query.filter(RegistroLongitudinal.criado_por_responsavel_id == responsible_id)
    else:
        query = query.filter(RegistroLongitudinal.formulario_id == resolve_form(db, line).id)
    return query.first() is not None


def create_record(db, responsible_id, patient_id, line_code, reference_date, values):
    lines = authorized_lines(db, responsible_id, patient_id)
    line = next((line for line in lines if line.code == line_code), None)
    if line is None:
        raise ValueError('Linha de Cuidado indisponível.')
    if reference_date not in (date.today(), date.today() - timedelta(days=1)):
        raise ValueError('A data do registro deve ser hoje ou ontem.')
    if record_exists(db, patient_id, line, reference_date, responsible_id):
        raise ValueError('Já existe um acompanhamento enviado para esta data.')
    try:
        return DailyRecordService().create(db, DailyRecordSubmission(
            patient_id, line.code, reference_date, CareOrigin.RESPONSAVEL_WHATSAPP,
            ActorRef(ActorType.RESPONSIBLE, responsible_id), values), commit=False)
    except (DailyRecordError, CareLineError):
        raise ValueError('Não foi possível validar o registro nesta Linha.') from None
