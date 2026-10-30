"""Add opt-in agenda storage; no conversion, executor, or delivery authorization."""
from alembic import op
import sqlalchemy as sa

revision = 'mh_agenda_v1'
down_revision = 'mh_weekly_config_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('acompanhamentos_whatsapp', sa.Column('programacao_data_fim', sa.Date()))
    op.add_column('acompanhamentos_whatsapp', sa.Column('programacao_versao', sa.Integer(), nullable=False, server_default='0'))
    op.create_check_constraint('ck_aw_versao', 'acompanhamentos_whatsapp', 'programacao_versao >= 0')
    op.create_check_constraint('ck_aw_agenda', 'acompanhamentos_whatsapp', 'programacao_data_fim IS NULL OR (dia_semana IS NOT NULL AND programacao_versao > 0)')
    op.create_unique_constraint('uq_wcc_agenda_identidade', 'whatsapp_conversas_contextuais', ['id', 'acompanhamento_whatsapp_id'])
    op.execute("""CREATE TABLE whatsapp_agenda_checkins (
        id SERIAL PRIMARY KEY,
        acompanhamento_id INTEGER NOT NULL REFERENCES acompanhamentos_whatsapp(id) ON DELETE RESTRICT,
        previsto_em TIMESTAMPTZ NOT NULL,
        status VARCHAR(16) NOT NULL,
        programacao_versao INTEGER NOT NULL CONSTRAINT ck_wagc_versao CHECK(programacao_versao > 0),
        conversa_id INTEGER,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
        atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
        processamento_iniciado_em TIMESTAMPTZ,
        processado_em TIMESTAMPTZ,
        motivo_estado VARCHAR(64) NOT NULL,
        CONSTRAINT uq_wagc_instante UNIQUE(acompanhamento_id, previsto_em),
        CONSTRAINT uq_wagc_identidade UNIQUE(id, acompanhamento_id),
        CONSTRAINT fk_wagc_conversa FOREIGN KEY(conversa_id, acompanhamento_id)
            REFERENCES whatsapp_conversas_contextuais(id, acompanhamento_whatsapp_id) ON DELETE RESTRICT,
        CONSTRAINT ck_wagc_status CHECK(status IN ('AGENDADO','PROCESSANDO','EXECUTADO','CANCELADO','PERDIDO','BLOQUEADO')),
        CONSTRAINT ck_wagc_processamento CHECK(processado_em IS NULL OR processamento_iniciado_em IS NOT NULL)
    )""")
    op.create_index('ix_wagc_estado_instante', 'whatsapp_agenda_checkins', ['acompanhamento_id', 'status', 'previsto_em'])
    op.execute("""CREATE TABLE whatsapp_agenda_eventos (
        id SERIAL PRIMARY KEY,
        acompanhamento_id INTEGER NOT NULL REFERENCES acompanhamentos_whatsapp(id) ON DELETE RESTRICT,
        ocorrencia_id INTEGER,
        programacao_versao INTEGER NOT NULL CONSTRAINT ck_wage_versao CHECK(programacao_versao > 0),
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE RESTRICT,
        origem VARCHAR(32) NOT NULL,
        motivo VARCHAR(64) NOT NULL,
        estado_anterior VARCHAR(16), estado_novo VARCHAR(16), configuracao JSON,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT fk_wage_ocorrencia FOREIGN KEY(ocorrencia_id, acompanhamento_id)
            REFERENCES whatsapp_agenda_checkins(id, acompanhamento_id) ON DELETE RESTRICT,
        CONSTRAINT ck_wage_anterior CHECK(estado_anterior IS NULL OR estado_anterior IN ('AGENDADO','PROCESSANDO','EXECUTADO','CANCELADO','PERDIDO','BLOQUEADO')),
        CONSTRAINT ck_wage_novo CHECK(estado_novo IS NULL OR estado_novo IN ('AGENDADO','PROCESSANDO','EXECUTADO','CANCELADO','PERDIDO','BLOQUEADO'))
    )""")
    op.create_index('ix_wage_acompanhamento', 'whatsapp_agenda_eventos', ['acompanhamento_id', 'id'])
    for table in ('whatsapp_agenda_checkins', 'whatsapp_agenda_eventos'):
        op.execute('CREATE TRIGGER whatsapp_writer_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON '
                   + table + ' FOR EACH STATEMENT EXECUTE FUNCTION whatsapp_protocol_fence()')
    op.execute("""CREATE FUNCTION whatsapp_agenda_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'WHATSAPP_AGENDA_AUDIT_IMMUTABLE' USING ERRCODE='55000'; END; $$""")
    op.execute('CREATE TRIGGER whatsapp_agenda_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON whatsapp_agenda_eventos FOR EACH STATEMENT EXECUTE FUNCTION whatsapp_agenda_audit_immutable()')


def downgrade():
    raise RuntimeError('Agenda requires forward recovery; preserve occurrence history')
