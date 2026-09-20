"""Add only synthetic WhatsApp runtime data to the disposable Gate 2 database."""
import os
import importlib.util
from pathlib import Path
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

if os.environ.get('DATABASE_URL') != 'postgresql+psycopg2://gate1@127.0.0.1/gate1_test':
    raise RuntimeError('Disposable Gate 2 database required.')
from app.database import engine
from app.models import (Responsavel, ResponsavelPaciente, FormularioModulo, CampoFormulario,
                        WhatsAppConversa)
from app.services.daily_record.providers.neuro import FIELDS

with engine.begin() as conn:
    if inspect(conn).has_table('whatsapp_mensagens'):
        raise RuntimeError('WhatsApp fixture already initialized.')
    # This synthetic runtime did not previously include the legacy conversation
    # table. Reconstruct its pre-revision shape before applying the real revision.
    if not inspect(conn).has_table('whatsapp_conversas'):
        WhatsAppConversa.__table__.create(conn)
        conn.execute(text('ALTER TABLE whatsapp_conversas DROP COLUMN care_line'))
    path=Path(__file__).resolve().parents[2]/'alembic/versions/8c01a0d1a004_whatsapp_ingress.py'
    spec=importlib.util.spec_from_file_location('wa_revision',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(conn)):module.upgrade()
with Session(engine) as db:
    db.add(FormularioModulo(id=2,modulo_id=1,nome='Neuro synthetic',tipo='REGISTRO_DIARIO',ativo=True))
    db.flush()
    for name in FIELDS:
        db.add(CampoFormulario(formulario_id=2,nome_campo=name,label=name,tipo_campo='texto',ativo=True))
    for identity,patient in ((10,1),(11,2),(12,3)):
        db.add(Responsavel(id=identity,nome='Synthetic WA',email='wa'+str(identity)+'@example.invalid',
            senha_hash='unused',telefone='55659999900'+str(identity),clinica_id=1,ativo=True))
        db.flush()
        db.add(ResponsavelPaciente(responsavel_id=identity,paciente_id=patient,ativo=True))
    db.commit()
print('Disposable WhatsApp migration and synthetic actors ready.')
