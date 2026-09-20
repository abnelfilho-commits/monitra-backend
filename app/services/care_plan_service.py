"""Care Plan writes own commit/rollback; ancestry helpers never commit.

Patient locks serialize active-plan changes. Agenda locks serialize planning
mutation with scheduling confirmation. Legacy reads never infer historical lines.
"""
from datetime import date
from functools import wraps

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.acl import assert_clinica_access
from app.models import (Paciente, PTS, PTSObjetivo, AgendaCuidado, Profissional,
                        AtividadeTerapeutica, OcupacaoProfissional, AtividadeOcupacao,
                        SessaoAssistencial)
from app.services.care_lines import CareLineResolver
from app.services.care_lines.exceptions import CareLineError, AmbiguousCareLine


def transaction(method):
    @wraps(method)
    def run(self, db, *args, **kwargs):
        try:
            result = method(self, db, *args, **kwargs)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
    return run


def call(operation):
    """HTTP compatibility for institutional care-line errors."""
    try:
        return operation()
    except CareLineError as exc:
        raise HTTPException(409 if isinstance(exc, AmbiguousCareLine) else 400,
                            exc.code + ': ' + str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(400, 'Dados inválidos para o plano de cuidado.') from exc


class CarePlanService:
    def __init__(self, resolver=None):
        self.resolver = resolver or CareLineResolver()

    @staticmethod
    def patient(db, identity, user, lock=False):
        query = db.query(Paciente).filter(Paciente.id == identity)
        if lock:
            query = query.populate_existing().with_for_update()
        patient = query.first()
        if patient is None:
            raise HTTPException(404, 'Paciente não encontrado.')
        assert_clinica_access(user, patient.clinica_id)
        return patient

    @staticmethod
    def row(db, model, identity, lock=False):
        query = db.query(model).filter(model.id == identity)
        if lock:
            query = query.populate_existing().with_for_update()
        row = query.first()
        if row is None:
            raise HTTPException(404, 'Recurso de plano de cuidado não encontrado.')
        return row

    def assigned(self, pts):
        # Registry only: current patient links must not redefine history.
        if pts.modulo_id is None:
            raise HTTPException(400, 'UNASSIGNED: PTS legado sem linha de cuidado.')
        line = self.resolver.registry.get(pts.modulo_id)
        if line is None:
            raise HTTPException(400, 'CARE_LINE_NOT_FOUND: linha persistida não suportada.')
        return line

    def plan(self, db, identity, user, write=False):
        pts = self.row(db, PTS, identity)
        self.patient(db, pts.paciente_id, user)
        if write:
            self.assigned(pts)
        return pts

    def objective(self, db, identity, user, write=False):
        obj = self.row(db, PTSObjetivo, identity)
        pts = self.plan(db, obj.pts_id, user, write)
        return obj, pts

    def agenda(self, db, identity, user, write=False, lock=False):
        agenda = self.row(db, AgendaCuidado, identity, lock)
        _, pts = self.objective(db, agenda.objetivo_id, user, write)
        if agenda.pts_id != pts.id:
            raise HTTPException(400, 'Agenda e objetivo não pertencem ao mesmo PTS.')
        if write and db.query(SessaoAssistencial.id).filter(
                SessaoAssistencial.agenda_cuidado_id == identity,
                SessaoAssistencial.paciente_id != pts.paciente_id).first():
            raise HTTPException(409, 'Sessão com paciente incompatível com o PTS.')
        return agenda, pts

    @staticmethod
    def conflict(db, patient_id, module_id, exclude=None):
        query = db.query(PTS.id).filter(PTS.paciente_id == patient_id,
            PTS.modulo_id == module_id, PTS.status == 'ATIVO')
        if exclude is not None:
            query = query.filter(PTS.id != exclude)
        if query.first():
            raise HTTPException(400, 'Já existe um PTS ativo para este paciente.')

    @transaction
    def create(self, db, payload, user):
        patient = self.patient(db, payload.paciente_id, user, lock=True)
        line = self.resolver.resolve(db, patient.id, payload.modulo_id)
        self.conflict(db, patient.id, line.module_id)
        pts = PTS(paciente_id=patient.id, modulo_id=line.module_id,
                  data_inicio=payload.data_inicio, objetivo_geral=payload.objetivo_geral,
                  observacoes=payload.observacoes, criado_por_usuario_id=user.id)
        db.add(pts)
        db.flush()
        return pts

    def list_scoped(self, db, patient_id, user, requested_line=None):
        self.patient(db, patient_id, user)
        line = self.resolver.resolve(db, patient_id, requested_line)
        return db.query(PTS).filter(PTS.paciente_id == patient_id,
            PTS.modulo_id == line.module_id).order_by(PTS.id.desc()).all()

    def list_plans(self, db, patient_id, user, requested_line=None):
        if requested_line is not None:
            return self.list_scoped(db, patient_id, user, requested_line)
        # Explicit compatibility path; never chooses an active plan across lines.
        self.patient(db, patient_id, user)
        return db.query(PTS).filter(PTS.paciente_id == patient_id).order_by(PTS.id.desc()).all()

    @transaction
    def set_closed(self, db, identity, user, closed):
        pts = self.plan(db, identity, user)
        # One lock order for close/reopen/create: patient first, then PTS.
        self.patient(db, pts.paciente_id, user, lock=True)
        pts = self.row(db, PTS, identity, lock=True)
        if not closed:
            self.assigned(pts)
            self.conflict(db, pts.paciente_id, pts.modulo_id, pts.id)
        pts.status = 'ENCERRADO' if closed else 'ATIVO'
        pts.data_fim = date.today() if closed else None
        db.flush()
        return pts

    def list_objectives(self, db, identity, user):
        self.plan(db, identity, user)
        return db.query(PTSObjetivo).filter(PTSObjetivo.pts_id == identity).order_by(PTSObjetivo.id).all()

    @transaction
    def create_objective(self, db, identity, payload, user):
        self.plan(db, identity, user, write=True)
        obj = PTSObjetivo(pts_id=identity, descricao=payload.descricao, prioridade=payload.prioridade)
        db.add(obj)
        db.flush()
        return obj

    @transaction
    def update_objective(self, db, identity, payload, user):
        obj, _ = self.objective(db, identity, user, write=True)
        for field in ('descricao', 'prioridade', 'status'):
            value = getattr(payload, field)
            if value is not None:
                setattr(obj, field, value)
        db.flush()
        return obj

    def catalog(self, db, pts, activity_id, occupation_id, professional_id):
        line = self.assigned(pts)
        activity = self.row(db, AtividadeTerapeutica, activity_id)
        occupation = self.row(db, OcupacaoProfissional, occupation_id)
        if not activity.ativo or activity.modulo_id != line.module_id:
            raise HTTPException(400, 'Atividade inativa ou incompatível com a linha do PTS.')
        if not occupation.ativo or not db.query(AtividadeOcupacao.id).filter(
                AtividadeOcupacao.atividade_id == activity_id,
                AtividadeOcupacao.ocupacao_id == occupation_id).first():
            raise HTTPException(400, 'Ocupação inativa ou incompatível com a atividade.')
        professional = self.row(db, Profissional, professional_id)
        patient = self.row(db, Paciente, pts.paciente_id)
        if (not professional.ativo or professional.clinica_id != patient.clinica_id
                or professional.ocupacao_id != occupation_id):
            raise HTTPException(400, 'Profissional incompatível com a clínica ou ocupação.')

    def list_agendas(self, db, objective_id, user):
        self.objective(db, objective_id, user)
        rows = db.query(AgendaCuidado).filter(AgendaCuidado.objetivo_id == objective_id).order_by(
            AgendaCuidado.created_at.desc()).all()
        for row in rows:
            self.agenda(db, row.id, user)
        return rows

    @transaction
    def create_agenda(self, db, payload, user):
        _, pts = self.objective(db, payload.objetivo_id, user, write=True)
        if pts.id != payload.pts_id:
            raise HTTPException(400, 'O objetivo informado não pertence ao PTS.')
        self.catalog(db, pts, payload.atividade_id, payload.ocupacao_id, payload.profissional_id)
        row = AgendaCuidado(**payload.model_dump(), status='PLANEJADO')
        db.add(row)
        db.flush()
        return row

    @transaction
    def update_agenda(self, db, identity, payload, user):
        row, pts = self.agenda(db, identity, user, write=True, lock=True)
        changes = payload.model_dump(exclude_unset=True)
        professional = changes.get('profissional_id', row.profissional_id)
        self.catalog(db, pts, row.atividade_id, row.ocupacao_id, professional)
        # Old sessions with no stored professional use an agenda fallback in reads.
        # Changing that fallback would silently reattribute their history.
        if professional != row.profissional_id and db.query(SessaoAssistencial.id).filter(
                SessaoAssistencial.agenda_cuidado_id == identity,
                SessaoAssistencial.profissional_id.is_(None)).first():
            raise HTTPException(409, 'Sessão sem profissional próprio impede troca no planejamento.')
        for field, value in changes.items():
            setattr(row, field, value)
        db.flush()
        return row

    @transaction
    def delete_agenda(self, db, identity, user):
        row, _ = self.agenda(db, identity, user, write=True, lock=True)
        if db.query(SessaoAssistencial.id).filter(SessaoAssistencial.agenda_cuidado_id == identity).first():
            raise HTTPException(409, 'Agenda com sessões geradas não pode ser excluída.')
        db.delete(row)
        db.flush()

    def scheduling_agenda(self, db, identity, user):
        row, pts = self.agenda(db, identity, user, write=True, lock=True)
        self.catalog(db, pts, row.atividade_id, row.ocupacao_id, row.profissional_id)
        return row
