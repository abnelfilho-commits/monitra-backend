"""Institutional weekly executor grants, disabled by absence. No data conversion."""
from alembic import op

revision = 'mh_executor_v1'
down_revision = 'mh_agenda_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE whatsapp_executor_habilitacoes (
        id SERIAL PRIMARY KEY,
        instituicao_id INTEGER NOT NULL REFERENCES instituicoes(id) ON DELETE RESTRICT,
        identidade VARCHAR(32) NOT NULL DEFAULT 'EXECUTOR_SEMANAL_MENTAL',
        habilitado BOOLEAN NOT NULL DEFAULT false,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
        motivo VARCHAR(160) NOT NULL,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CONSTRAINT ck_weh_identidade CHECK (identidade = 'EXECUTOR_SEMANAL_MENTAL'),
        CONSTRAINT ck_weh_motivo CHECK (length(trim(motivo)) BETWEEN 8 AND 160)
    )""")
    op.create_index('ix_weh_instituicao', 'whatsapp_executor_habilitacoes', ['instituicao_id', 'id'])
    op.execute('CREATE TRIGGER whatsapp_writer_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON whatsapp_executor_habilitacoes FOR EACH STATEMENT EXECUTE FUNCTION whatsapp_protocol_fence()')
    op.execute('CREATE TRIGGER whatsapp_executor_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON whatsapp_executor_habilitacoes FOR EACH STATEMENT EXECUTE FUNCTION whatsapp_agenda_audit_immutable()')
    op.create_index('ix_wagc_executor', 'whatsapp_agenda_checkins', ['status', 'previsto_em', 'id'])


def downgrade():
    raise RuntimeError('Forward recovery required; preserve executor grant audit')
