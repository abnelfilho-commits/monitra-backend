from types import SimpleNamespace
from app.models.modular import RegistroLongitudinal, RespostaRegistro
from app.services.care_lines import care_line_resolver, CareOrigin
from app.services.registros_longitudinais import persistir_registro_longitudinal, preencher_resposta
from .models import ActorType, DailyRecordResult
from .exceptions import DailyRecordIdentityConflict, DailyRecordNotFound, DailyRecordError
from .providers import PROVIDERS


class DailyRecordService:
    def __init__(self, resolver=None, providers=None):
        self.resolver = resolver or care_line_resolver
        self.providers = dict(PROVIDERS if providers is None else providers)

    def create(self, db, submission, commit=True):
        return self._write(db, submission, commit=commit)

    def update(self, db, record_id, submission):
        return self._write(db, submission, record_id)

    def _write(self, db, submission, record_id=None, commit=True):
        try:
            line = self.resolver.resolve(db, submission.patient_id,
                                         submission.requested_care_line, 'daily_record')
            provider = self.providers.get(line.code)
            if provider is None:
                raise DailyRecordError('Daily Record provider unavailable.')
            record = None
            if record_id is not None:
                record = db.query(RegistroLongitudinal).filter(
                    RegistroLongitudinal.id == record_id).with_for_update().first()
                if record is None:
                    raise DailyRecordNotFound('Daily Record not found.')
                if (record.paciente_id, record.modulo_id) != (submission.patient_id, line.module_id):
                    raise DailyRecordIdentityConflict('Patient and care line are immutable.')
            prepared = provider.prepare(db, line, submission, record_id)
            stored_origin = submission.origin.value
            if record is None:
                payload = SimpleNamespace(paciente_id=submission.patient_id, modulo_id=line.module_id,
                    formulario_id=prepared.form_id, data_registro=submission.reference_date,
                    origem=stored_origin, respostas=[SimpleNamespace(campo_id=k, valor=v)
                                                    for k, v in prepared.answers.items()])
                record = persistir_registro_longitudinal(db, payload)
                if submission.actor.type == ActorType.PROFESSIONAL:
                    record.criado_por_usuario_id = submission.actor.id
                elif submission.actor.type == ActorType.RESPONSIBLE:
                    record.criado_por_responsavel_id = submission.actor.id
            else:
                if record.formulario_id != prepared.form_id:
                    raise DailyRecordIdentityConflict('Form identity is immutable.')
                record.origem = stored_origin
                record.data_registro = submission.reference_date
                db.query(RespostaRegistro).filter(RespostaRegistro.registro_id == record.id).delete()
                db.flush()
                for field_id, value in prepared.answers.items():
                    answer = RespostaRegistro(registro_id=record.id, campo_id=field_id)
                    preencher_resposta(answer, value)
                    db.add(answer)
            db.flush()
            provider.persist_projection(db, record.id, prepared.projection)
            db.flush()
            # Materialize result before commit: no refresh/query can fail after persistence.
            result = DailyRecordResult(record.id, submission.patient_id, line,
                record.data_registro, submission.origin, record.criado_em)
            if commit:
                db.commit()
            return result
        except Exception:
            if commit:
                db.rollback()
            raise
