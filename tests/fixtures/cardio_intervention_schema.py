"""Physical Cardio table verified in HML; synthetic databases only.

SQLite is a unit-test approximation. PostgreSQL is the structural oracle.
pre_line=True reconstructs the same table before migration 8c01a0d1a003.
"""
from sqlalchemy import text


def create_cardio_intervention_table(conn, pre_line=False):
    postgres = conn.dialect.name == 'postgresql'
    identity = 'SERIAL' if postgres else 'INTEGER'
    timestamp = 'TIMESTAMPTZ' if postgres else 'TIMESTAMP'
    now = 'now()' if postgres else 'CURRENT_TIMESTAMP'
    line = '' if pre_line else ', modulo_id INTEGER NOT NULL CONSTRAINT fk_cardio_intervencoes_modulo REFERENCES modulos_clinicos(id)'
    conn.execute(text("""CREATE TABLE intervencoes_cardiometabolicas (
        id {identity} PRIMARY KEY,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        tipo VARCHAR NOT NULL, descricao TEXT, prioridade VARCHAR,
        created_at {timestamp} DEFAULT {now}{line})""".format(
            identity=identity, timestamp=timestamp, now=now, line=line)))
    conn.execute(text('CREATE INDEX ix_intervencoes_cardio_paciente_id ON intervencoes_cardiometabolicas (paciente_id)'))
