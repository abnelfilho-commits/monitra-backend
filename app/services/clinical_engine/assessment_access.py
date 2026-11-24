"""Authorization boundary for legacy assessment HTTP resources only."""
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.avaliacao_clinica import AvaliacaoClinica as Assessment
from app.models.modular import RegistroLongitudinal as Record, FormularioModulo
from app.services.care_lines.access import authorized_patient
from app.services.care_lines.registry import care_line_registry, NEURO


def unavailable():
    return HTTPException(404, 'Avaliação clínica não disponível.')


def authorize(db, user, patient_id, module_id, *, write=False):
    try:
        return authorized_patient(db, user, patient_id, module_id, write=write)
    except HTTPException as exc:
        if exc.status_code in (400, 403, 404):
            raise unavailable() from None
        raise


def record_access(db, user, record_id, *, write=False):
    statement = select(Record.id, Record.paciente_id, Record.modulo_id,
        Record.formulario_id).where(Record.id == record_id,
                                   Record.contexto_assistencial_id.is_(None))
    if write:
        statement = statement.with_for_update()
    row = db.execute(statement).first()
    if row is None:
        raise unavailable()
    authorize(db, user, row.paciente_id, row.modulo_id, write=write)
    return row


def execution_access(db, user, record_id, instrument):
    row = record_access(db, user, record_id, write=True)
    form = db.get(FormularioModulo, row.formulario_id)
    # Match the same persisted form code used by automatic legacy execution.
    code = (form.codigo or form.nome.upper().replace('-', '').replace(' ', '_')) if form else None
    if (form is None or not form.ativo or form.tipo != 'ASSESSMENT'
            or form.modulo_id != row.modulo_id or code.upper() != instrument.upper()
            or instrument.upper() not in ('MCHAT', 'DENVER') or row.modulo_id != NEURO.module_id):
        raise HTTPException(422, 'Formulário e instrumento incompatíveis com o registro legado.')
    return row


def valid_assessments():
    # Positive ancestry: orphans and cross-patient/module rows never qualify.
    return select(Assessment).join(Record, Record.id == Assessment.registro_id).join(
        FormularioModulo, FormularioModulo.id == Record.formulario_id).where(
        FormularioModulo.modulo_id == Record.modulo_id,
        FormularioModulo.tipo == 'ASSESSMENT',
        func.upper(Assessment.instrumento) == func.upper(func.coalesce(
            func.nullif(FormularioModulo.codigo, ''),
            func.replace(func.replace(func.upper(FormularioModulo.nome), '-', ''), ' ', '_'))),
        Record.contexto_assistencial_id.is_(None),
        Assessment.paciente_id == Record.paciente_id,
        Assessment.modulo_id == Record.modulo_id,
        Assessment.formulario_id.is_not_distinct_from(Record.formulario_id))


def assessment_access(db, user, identity):
    # Load only identity metadata until the resource has been authorized.
    row = db.execute(valid_assessments().with_only_columns(
        Assessment.paciente_id, Assessment.modulo_id).where(Assessment.id == identity)).first()
    if row is None:
        raise unavailable()
    authorize(db, user, row.paciente_id, row.modulo_id)
    return db.scalars(valid_assessments().where(Assessment.id == identity)).first()


def permitted_modules(db, user, patient_id):
    modules = []
    for line in care_line_registry.all():
        try:
            authorize(db, user, patient_id, line.module_id)
            modules.append(line.module_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    if not modules:
        raise unavailable()
    return modules
