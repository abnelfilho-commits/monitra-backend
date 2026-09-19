from app.models.modular import RegistroLongitudinal
from app.services.care_lines import CareOrigin
from ..exceptions import DuplicateDailyRecord
from sqlalchemy import text
from ..exceptions import DailyRecordError
from math import isfinite
from app.services import cardiometabolico_engine as engine
from .common import PreparedRecord, resolve_form, resolve_fields
from ..exceptions import InvalidDailyRecordPayload

NUMERIC = {'glicemia_jejum', 'glicemia_pos_prandial', 'pressao_sistolica', 'pressao_diastolica', 'peso', 'altura'}
TEXT = {'atividade_fisica', 'sono', 'humor'}
ENGINE_FIELDS = {'glicemia_jejum', 'pressao_sistolica', 'pressao_diastolica', 'peso'} | TEXT
# Confirmed local compatibility columns only; never dynamic SQL from payload keys.
PROJECTION_FIELDS = {'glicemia_jejum', 'glicemia_pos_prandial', 'pressao_sistolica', 'pressao_diastolica', 'peso'} | TEXT


class CardioDailyRecordProvider:
    def prepare(self, db, line, submission, record_id=None):
        form = resolve_form(db, line)
        if submission.origin in (CareOrigin.RESPONSAVEL_APP, CareOrigin.RESPONSAVEL_WHATSAPP):
            query = db.query(RegistroLongitudinal.id).filter(
                RegistroLongitudinal.paciente_id == submission.patient_id,
                RegistroLongitudinal.modulo_id == line.module_id,
                RegistroLongitudinal.data_registro == submission.reference_date,
                RegistroLongitudinal.criado_por_responsavel_id == submission.actor.id,
                RegistroLongitudinal.origem.in_(('RESPONSAVEL', 'RESPONSAVEL_APP', 'RESPONSAVEL_WHATSAPP')))
            if record_id is not None:
                query = query.filter(RegistroLongitudinal.id != record_id)
            if query.first() is not None:
                raise DuplicateDailyRecord('Você já enviou um registro cardiometabólico para esta data.')
        if set(submission.payload) - (NUMERIC | TEXT | {"observacoes"}):
            raise InvalidDailyRecordPayload('Unsupported Cardio field; no clinical alias is inferred.')
        values = dict(submission.payload)
        for name, value in values.items():
            if value is None:
                continue
            if name in NUMERIC:
                if type(value) not in (int, float) or not isfinite(value):
                    raise InvalidDailyRecordPayload('Cardio measurement must be finite numeric data.')
            elif not isinstance(value, str):
                raise InvalidDailyRecordPayload('Cardio classification must be text.')
        # General narrative has its own approved column, never a questionnaire alias.
        answers = resolve_fields(db, form.id, {k: v for k, v in values.items() if k != "observacoes"})
        usable = {key: value for key, value in values.items()
                  if key in ENGINE_FIELDS and value is not None
                  and (not isinstance(value, str) or value.strip())}
        projection = {key: values.get(key) for key in PROJECTION_FIELDS}
        if "observacoes" in values:
            projection["observacoes"] = values["observacoes"]
        projection.update(modulo=line.slug, score_clinico=None, risco=None,
                          protocolo=None, leitura_clinica=None)
        if usable:
            score = engine.calcular_score(usable)
            projection.update(score_clinico=score, risco=engine.classificar_risco(score),
                              protocolo=engine.definir_protocolo(score),
                              leitura_clinica=engine.gerar_leitura_clinica(usable, score))
        return PreparedRecord(form.id, answers, projection)

    @staticmethod
    def persist_projection(db, record_id, projection):
        if projection:
            # Projection keys are private provider output, never request SQL identifiers.
            allowed = {'modulo', 'glicemia_jejum', 'glicemia_pos_prandial', 'pressao_sistolica',
                       'pressao_diastolica', 'peso', 'atividade_fisica', 'sono', 'humor',
                       'score_clinico', 'risco', 'protocolo', 'leitura_clinica', 'observacoes'}
            if not set(projection) <= allowed:
                raise DailyRecordError('Unsupported projection column.')
            assignments = ', '.join(key + ' = :' + key for key in sorted(projection))
            db.execute(text('UPDATE registros_longitudinais SET ' + assignments + ' WHERE id = :record_id'),
                       dict(projection, record_id=record_id))
