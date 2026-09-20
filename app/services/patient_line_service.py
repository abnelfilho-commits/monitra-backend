"""Membership is independent of clinical observations."""
from sqlalchemy.orm import joinedload
from app.models import Paciente, PacienteModulo
from app.services.care_lines.access import authorized_line, authorized_patient


def list_patients(db, user, care_line):
    line = authorized_line(db, user, care_line)
    linked = db.query(PacienteModulo.id).filter(
        PacienteModulo.paciente_id == Paciente.id,
        PacienteModulo.modulo_id == line.module_id,
        PacienteModulo.ativo.is_(True)).exists()
    query = db.query(Paciente).options(joinedload(Paciente.clinica), joinedload(Paciente.profissional)).filter(Paciente.ativo.is_(True), linked)
    if (user.perfil or '').strip().upper() not in {'ADMIN', 'ADMINISTRADOR'}:
        query = query.filter(Paciente.clinica_id == user.clinica_id)
    return query.order_by(Paciente.nome, Paciente.id).all()


def link_patient(db, user, patient_id, care_line):
    patient, line = authorized_patient(db, user, patient_id, care_line, True, require_link=False)
    try:
        # Serialize association requests, without changing historical inactive links.
        db.query(Paciente).filter_by(id=patient.id).with_for_update().one()
        link = db.query(PacienteModulo).filter_by(
            paciente_id=patient.id, modulo_id=line.module_id, ativo=True).first()
        if link is None:
            link = PacienteModulo(paciente_id=patient.id, modulo_id=line.module_id, ativo=True)
            db.add(link)
            db.flush()
        result = {'patient_id': patient.id, 'care_line': line.code, 'link_id': link.id}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
