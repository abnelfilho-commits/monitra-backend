"""Canonical applicability: explicit associations precede the legacy fallback."""
from sqlalchemy import select, and_, or_
from app.models.atividade_terapeutica import AtividadeTerapeutica, AtividadeModulo


def applicable_to(module_id):
    links = select(AtividadeModulo.atividade_id).where(
        AtividadeModulo.atividade_id == AtividadeTerapeutica.id).correlate(AtividadeTerapeutica)
    return or_(links.where(AtividadeModulo.modulo_id == module_id).exists(),
               and_(~links.exists(), AtividadeTerapeutica.modulo_id == module_id))


def activity_applies(db, activity_id, module_id):
    return db.scalar(select(AtividadeTerapeutica.id).where(
        AtividadeTerapeutica.id == activity_id, applicable_to(module_id))) is not None
