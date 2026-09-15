"""Institutional Session/Attendance boundary. Clinical content stays in forms.

Existing identity derives from persisted ancestry, never current patient links.
Mutation methods own one commit/rollback and serialize on the session row.
"""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (SessaoAssistencial, RegistroLongitudinal, FormularioModulo,
                        CampoFormulario)
from app.schemas.registros_longitudinais import RegistroLongitudinalCreate, CampoResposta
from app.schemas.sessao_assistencial import SessaoAssistencialResponse
from app.services.care_plan_service import CarePlanService, transaction
from app.services.registros_longitudinais import persistir_registro_longitudinal, obter_registro_longitudinal


class SessionService:
    def __init__(self, care_plans=None):
        self.care_plans = care_plans or CarePlanService()

    def context(self, db: Session, identity: int, user, lock: bool = False, clinical: bool = False):
        session = self.care_plans.row(db, SessaoAssistencial, identity, lock=lock)
        agenda, pts = self.care_plans.agenda(db, session.agenda_cuidado_id, user)
        if session.paciente_id != pts.paciente_id:
            raise HTTPException(409, 'Paciente da sessão incompatível com a ancestralidade do PTS.')
        line = None
        if pts.modulo_id is not None:
            line = self.care_plans.assigned(pts)
        elif clinical:
            raise HTTPException(422, 'UNASSIGNED: sessão sem linha de cuidado definida.')
        if session.registro_longitudinal_id is not None:
            record = db.query(RegistroLongitudinal).filter_by(id=session.registro_longitudinal_id).first()
            form = db.query(FormularioModulo).filter_by(id=record.formulario_id).first() if record else None
            if (record is None or form is None or record.paciente_id != pts.paciente_id
                    or record.modulo_id != pts.modulo_id or form.modulo_id != pts.modulo_id
                    or form.codigo != 'ATENDIMENTO_SESSAO' or form.tipo != 'LONGITUDINAL'):
                raise HTTPException(409, 'Vínculo longitudinal da sessão inconsistente.')
        return session, pts, line

    def patient_sessions(self, db, patient_id, user):
        self.care_plans.patient(db, patient_id, user)
        rows = db.query(SessaoAssistencial).filter_by(paciente_id=patient_id).order_by(
            SessaoAssistencial.data_agendada, SessaoAssistencial.hora_inicio,
            SessaoAssistencial.numero_sessao).all()
        for row in rows:
            self.context(db, row.id, user)
        return rows

    def personal_sessions(self, db, user):
        if user.perfil != 'PROFISSIONAL':
            raise HTTPException(403, 'A Agenda Assistencial é exclusiva do profissional.')
        if not user.profissional_id:
            raise HTTPException(422, 'O usuário autenticado não está vinculado a um profissional.')
        rows = db.query(SessaoAssistencial).filter_by(profissional_id=user.profissional_id).order_by(
            SessaoAssistencial.data_agendada, SessaoAssistencial.hora_inicio).all()
        for row in rows:
            self.context(db, row.id, user)
        return rows

    @transaction
    def transition(self, db, identity, user, action, reason: Optional[str] = None):
        session, _, _ = self.context(db, identity, user, lock=True)
        allowed = {'confirmar': ('AGENDADA',), 'iniciar': ('CONFIRMADA',),
                   'finalizar': ('EM_ANDAMENTO',), 'reagendar': ('AGENDADA', 'CONFIRMADA')}
        if action not in allowed or session.status not in allowed[action]:
            raise HTTPException(422, 'Transição inválida para o estado atual da sessão.')
        now = datetime.now()
        if action == 'confirmar':
            session.status = 'CONFIRMADA'
        elif action == 'iniciar':
            session.status = 'EM_ANDAMENTO'
            session.hora_inicio_real = now.time()
        elif action == 'finalizar':
            session.status = 'REALIZADA'
            session.data_realizacao = now.date()
            session.hora_fim_real = now.time()
        else:
            session.status = 'REAGENDADA'
            session.motivo_reagendamento = reason
        db.flush()
        # Validate/materialize the legacy response before committing.
        return SessaoAssistencialResponse.model_validate(session).model_dump()

    @staticmethod
    def form(db, line):
        forms = db.query(FormularioModulo).filter_by(modulo_id=line.module_id,
            codigo='ATENDIMENTO_SESSAO', ativo=True).all()
        if len(forms) != 1 or forms[0].tipo != 'LONGITUDINAL':
            raise HTTPException(422, 'Configuração ATENDIMENTO_SESSAO ausente, ambígua ou incompatível.')
        fields = db.query(CampoFormulario).filter_by(formulario_id=forms[0].id, ativo=True).all()
        by_name = {}
        for field in fields:
            if field.nome_campo in by_name:
                raise HTTPException(422, 'Configuração de campos de atendimento ambígua.')
            by_name[field.nome_campo] = field
        if 'narrativa_atendimento' not in by_name:
            raise HTTPException(422, 'Campo narrativa_atendimento não configurado.')
        return forms[0], by_name

    @staticmethod
    def validate_answers(fields, answers):
        by_id = {field.id: field for field in fields.values()}
        values = {}
        for answer in answers:
            if answer.campo_id not in by_id or answer.campo_id in values:
                raise HTTPException(422, 'Resposta duplicada ou campo incompatível com atendimento.')
            values[answer.campo_id] = answer.valor
        narrative = values.get(fields['narrativa_atendimento'].id)
        if not isinstance(narrative, str) or not narrative.strip():
            raise HTTPException(422, 'Informe como foi o atendimento.')
        next_field = fields.get('proximos_passos')
        if next_field and next_field.id in values:
            value = values[next_field.id]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise HTTPException(422, 'Próximos passos deve ser uma lista de textos.')
        for field in fields.values():
            if field.obrigatorio and values.get(field.id) in (None, '', []):
                raise HTTPException(422, 'Campo obrigatório de atendimento não informado.')

    @transaction
    def attend(self, db, identity, user, payload, legacy=False):
        session, pts, line = self.context(db, identity, user, lock=True, clinical=True)
        allowed = ('EM_ANDAMENTO', 'REALIZADA') if legacy else ('EM_ANDAMENTO',)
        if session.status not in allowed:
            raise HTTPException(422, 'Somente sessões no estado permitido podem registrar atendimento.')
        if session.registro_longitudinal_id is not None:
            raise HTTPException(409, 'Esta sessão já possui um Registro Longitudinal.')
        form, fields = self.form(db, line)
        if legacy:
            if (payload.paciente_id != pts.paciente_id or payload.modulo_id != line.module_id
                    or payload.formulario_id != form.id or payload.origem != 'PROFISSIONAL'):
                raise HTTPException(422, 'Contexto longitudinal incompatível com a sessão.')
            submission = payload
        else:
            answers = [CampoResposta(campo_id=fields['narrativa_atendimento'].id,
                                      valor=payload.narrativa.strip())]
            if payload.proximos_passos:
                field = fields.get('proximos_passos')
                if field is None:
                    raise HTTPException(422, 'Campo proximos_passos não configurado.')
                answers.append(CampoResposta(campo_id=field.id, valor=payload.proximos_passos))
            submission = RegistroLongitudinalCreate(paciente_id=pts.paciente_id,
                modulo_id=line.module_id, formulario_id=form.id, data_registro=datetime.now().date(),
                origem='PROFISSIONAL', respostas=answers)
        self.validate_answers(fields, submission.respostas)
        record = persistir_registro_longitudinal(db, submission)
        record.criado_por_usuario_id = user.id
        record.criado_por_responsavel_id = None
        db.flush()
        session.registro_longitudinal_id = record.id
        db.flush()
        if legacy:
            return obter_registro_longitudinal(db, record.id)
        return {'success': True, 'sessao_id': session.id, 'registro_id': record.id,
                'mensagem': 'Atendimento registrado com sucesso.'}
