"""Create synthetic UI integration data ONLY in the disposable Gate 1 database.

Includes only the five historical snapshot/narrative columns confirmed in HML.
Structured Cardio observations are stored exclusively as answer rows.
"""
from cardio_intervention_schema import create_cardio_intervention_table
import os
import importlib.util
from datetime import date
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

URL = 'postgresql+psycopg2://gate1@127.0.0.1/gate1_test'
if os.environ.get('DATABASE_URL') != URL:
    raise RuntimeError('Disposable Gate 1 database required.')
from app.database import Base, engine
import app.models
from app.models import (Clinica, Profissional, Usuario, Paciente, ModuloClinico,
                        ProfissionalModulo, PacienteModulo)
from app.core.security import hash_senha

with engine.begin() as conn:
    if conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar():
        raise RuntimeError('Fixture requires an empty disposable database.')
    Base.metadata.create_all(conn)
    # Reconstruct only the known pre-Wave-1 columns for migration validation.
    conn.execute(text('ALTER TABLE diagnosticos DROP COLUMN modulo_id'))
    conn.execute(text('ALTER TABLE intervencoes DROP COLUMN modulo_id'))
    create_cardio_intervention_table(conn, pre_line=True)
    for name, kind in {'score_clinico':'NUMERIC', 'risco':'VARCHAR', 'protocolo':'VARCHAR',
                'leitura_clinica':'TEXT', 'observacoes':'TEXT'}.items():
        conn.execute(text('ALTER TABLE registros_longitudinais ADD COLUMN '+name+' '+kind))
    conn.execute(text("INSERT INTO modulos_clinicos(id,nome,slug,ativo) VALUES (1,'Neurodesenvolvimento','neurodesenvolvimento',true),(2,'Cardiometabólico','cardiometabolico',true)"))
    for revision in ('5a01c7e2d903','8c01a0d1a001','8c01a0d1a002','8c01a0d1a003'):
        path = next((Path(__file__).resolve().parents[2]/'alembic/versions').glob(revision+'_*.py'))
        spec = importlib.util.spec_from_file_location(revision,path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

with Session(engine) as db:
    db.add_all([Clinica(id=i,nome='Gate1 synthetic clinic '+str(i)) for i in (1,2)])
    db.flush()
    db.add(Profissional(id=1,nome='Gate1 Synthetic Professional',clinica_id=1,ativo=True))
    db.flush()
    db.add(Usuario(id=1,nome='Gate1 Synthetic Professional',email='gate1@example.invalid',
                   senha_hash=hash_senha('synthetic-gate1-only'),perfil='PROFISSIONAL',
                   clinica_id=1,profissional_id=1,ativo=True))
    for line in (1,2):
        db.add(ProfissionalModulo(profissional_id=1,modulo_id=line))
    for identity,name in ((1,'Gate1 Neuro'),(2,'Gate1 Cardio'),(3,'Gate1 Multi'),(4,'Gate1 Other Clinic')):
        db.add(Paciente(id=identity,nome=name,data_nascimento=date(2000,1,1),
                        clinica_id=2 if identity==4 else 1,profissional_id=1 if identity!=4 else None,ativo=True))
    db.flush()
    for patient,line in ((1,1),(2,2),(3,1),(3,2),(4,2)):
        db.add(PacienteModulo(paciente_id=patient,modulo_id=line,ativo=True))
    db.commit()
print('Synthetic runtime ready: four patients, two clinics, two lines; migration chain applied.')
