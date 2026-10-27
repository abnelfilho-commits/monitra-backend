"""Selected routing cutover: paused by default, fence old binaries, then drop phone uniqueness."""
from alembic import op
revision = 'e14b_close_v1'
down_revision = 'e14b3b2_comunicacao'
branch_labels = None
depends_on = None

TABLES = ('acompanhamentos_whatsapp', 'whatsapp_conversas_contextuais',
          'whatsapp_conversas', 'whatsapp_mensagens', 'whatsapp_convite_envios',
          'whatsapp_resposta_execucoes', 'whatsapp_comunicacao_eventos',
          'whatsapp_autorizacoes_comunicacao', 'whatsapp_solicitacoes_manuais',
          'whatsapp_resolucoes', 'whatsapp_mensagens_roteaveis')


def upgrade():
    op.execute("""CREATE TABLE whatsapp_runtime (
        id integer PRIMARY KEY CHECK(id=1),
        protocol text NOT NULL CHECK(protocol='e14b_close_v1'),
        active boolean NOT NULL DEFAULT false)""")
    op.execute("INSERT INTO whatsapp_runtime(id,protocol) VALUES (1,'e14b_close_v1')")
    op.execute('REVOKE ALL ON whatsapp_runtime FROM PUBLIC')
    op.execute("""CREATE FUNCTION whatsapp_protocol_fence() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF current_setting('integra.whatsapp_protocol',true) IS DISTINCT FROM 'e14b_close_v1' THEN
        RAISE EXCEPTION 'WHATSAPP_WRITER_PROTOCOL_REQUIRED' USING ERRCODE='55000';
      END IF;
      RETURN NULL;
    END; $$""")
    for table in TABLES:
        op.execute('CREATE TRIGGER whatsapp_writer_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON '
                   + table + ' FOR EACH STATEMENT EXECUTE FUNCTION whatsapp_protocol_fence()')
    # Transactional DDL: the fence and pause exist before phone uniqueness goes.
    op.execute('DROP INDEX uq_wcc_aberta_telefone')
    op.execute("CREATE INDEX ix_wcc_aberta_telefone ON whatsapp_conversas_contextuais(telefone) WHERE status IN ('AGUARDANDO_ACEITE','EM_ANDAMENTO')")


def downgrade():
    # Duplicates may now be legitimate. Never delete/close care data to fit an old binary.
    raise RuntimeError('Selected routing requires forward recovery; old writers must remain fenced')
