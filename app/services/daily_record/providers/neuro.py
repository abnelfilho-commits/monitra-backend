from pydantic import ValidationError
from app.schemas.registro import RegistroDiarioResponsavelCreate
from datetime import date, timedelta
from app.models.modular import RegistroLongitudinal
from app.services.care_lines import CareOrigin
from .common import PreparedRecord, resolve_form, resolve_fields
from ..exceptions import InvalidDailyRecordPayload, DuplicateDailyRecord

FIELDS = ('sono_qualidade', 'evacuacao', 'consistencia_fezes', 'irritabilidade',
          'crise_sensorial', 'tempo_tela', 'seletividade_alimentar',
          'aceitou_alimento_novo', 'observacao')


class NeuroDailyRecordProvider:
    def prepare(self, db, line, submission, record_id=None):
        form = resolve_form(db, line)
        if set(submission.payload) - set(FIELDS):
            raise InvalidDailyRecordPayload('Unknown Neuro field.')
        # Preserve accepted API values; do not add questionnaire range restrictions.
        # Channels already implement evacuation/Bristol visibility and input coercion.
        try:
            validated = RegistroDiarioResponsavelCreate(data=submission.reference_date, **submission.payload)
        except ValidationError as exc:
            raise InvalidDailyRecordPayload('Invalid Neuro field type.') from exc
        values = {name: getattr(validated, name) for name in FIELDS}
        if submission.origin in (CareOrigin.RESPONSAVEL_APP, CareOrigin.RESPONSAVEL_WHATSAPP):
            today = date.today()
            if submission.reference_date not in (today, today - timedelta(days=1)):
                raise InvalidDailyRecordPayload('A data do registro deve ser hoje ou ontem.')
            query = db.query(RegistroLongitudinal.id).filter(
                RegistroLongitudinal.paciente_id == submission.patient_id,
                RegistroLongitudinal.modulo_id == line.module_id,
                RegistroLongitudinal.formulario_id == form.id,
                RegistroLongitudinal.data_registro == submission.reference_date,
                RegistroLongitudinal.origem.in_(('RESPONSAVEL', 'RESPONSAVEL_APP', 'RESPONSAVEL_WHATSAPP')),
            )
            if record_id is not None:
                query = query.filter(RegistroLongitudinal.id != record_id)
            if query.first() is not None:
                raise DuplicateDailyRecord('Você já enviou um registro para esta data.')
        return PreparedRecord(form.id, resolve_fields(db, form.id, values))

    def persist_projection(self, db, record_id, projection):
        pass  # Neuro interpretation remains patient-level and on demand.
