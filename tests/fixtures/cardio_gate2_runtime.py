"""Extend the empty-database Gate 1 fixture with synthetic Cardio form/APP actor.
No observations field is created in form metadata.
"""
import cardio_gate1_runtime
from app.database import engine
from sqlalchemy.orm import Session
from app.models import FormularioModulo, CampoFormulario, Responsavel, ResponsavelPaciente
from app.core.security import hash_senha
from app.services.daily_record.providers.cardio import NUMERIC, TEXT

with Session(engine) as db:
    db.add(Responsavel(id=9,nome='Gate2 Synthetic Responsible',email='gate2@example.invalid',
        senha_hash=hash_senha('synthetic-gate2-only'),telefone='5565999990000',clinica_id=1,ativo=True))
    db.add(FormularioModulo(id=200,modulo_id=2,nome='Cardio synthetic',tipo='REGISTRO_DIARIO',ativo=True))
    db.flush()
    for name in sorted(NUMERIC | TEXT):
        db.add(CampoFormulario(formulario_id=200,nome_campo=name,label=name,
            tipo_campo='numero' if name in NUMERIC else 'texto',ativo=True))
    for patient in (2,3):
        db.add(ResponsavelPaciente(responsavel_id=9,paciente_id=patient,ativo=True))
    db.commit()
print('Synthetic Cardio runtime ready; no observations form metadata created.')
