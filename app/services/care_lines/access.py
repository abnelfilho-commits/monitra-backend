"""Authorization for explicit professional care-line contexts."""
from fastapi import HTTPException
from app.models import Paciente, Profissional, ProfissionalModulo, ModuloClinico
from .registry import care_line_registry
from .resolver import care_line_resolver
from .exceptions import CareLineError


def authorized_line(db, user, requested_line, write=False, registry=None):
    role = (user.perfil or '').strip().upper()
    allowed = {'ADMIN', 'ADMINISTRADOR', 'ADMIN_CLINICA', 'PROFISSIONAL'}
    if not write:
        allowed.add('SUPORTE')
    if role not in allowed:
        raise HTTPException(403, 'Perfil sem acesso assistencial.')
    line = (registry or care_line_registry).get(requested_line)
    if line is None:
        raise HTTPException(400, 'CARE_LINE_NOT_FOUND')
    if not line.active:
        raise HTTPException(400, 'CARE_LINE_INACTIVE')
    if not db.query(ModuloClinico.id).filter_by(id=line.module_id, ativo=True).first():
        raise HTTPException(400, 'CARE_LINE_INACTIVE')
    if role not in {'ADMIN', 'ADMINISTRADOR'} and user.clinica_id is None:
        raise HTTPException(403, 'Usuário sem clínica vinculada.')
    if role == 'PROFISSIONAL':
        link = db.query(ProfissionalModulo.id).join(
            Profissional, Profissional.id == ProfissionalModulo.profissional_id).filter(
                Profissional.id == user.profissional_id,
                Profissional.ativo.is_(True), Profissional.clinica_id == user.clinica_id,
                ProfissionalModulo.modulo_id == line.module_id).first()
        if link is None:
            raise HTTPException(403, 'Profissional sem acesso à linha.')
    return line


def authorized_patient(db, user, patient_id, requested_line, write=False, require_link=True, resolver=None):
    resolver = resolver or care_line_resolver
    line = authorized_line(db, user, requested_line, write, resolver.registry)
    query = db.query(Paciente).filter(Paciente.id == patient_id, Paciente.ativo.is_(True))
    if (user.perfil or '').strip().upper() not in {'ADMIN', 'ADMINISTRADOR'}:
        query = query.filter(Paciente.clinica_id == user.clinica_id)
    patient = query.first()
    if patient is None:
        raise HTTPException(404, 'Paciente não encontrado.')
    if require_link:
        try:
            resolver.resolve(db, patient.id, line.code)
        except CareLineError as exc:
            raise HTTPException(403, exc.code) from exc
    return patient, line
