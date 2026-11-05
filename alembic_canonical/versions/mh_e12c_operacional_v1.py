from alembic import op
revision = 'mh_e12c_operacional_v1'
down_revision = 'mh_executor_v1'
branch_labels = None
depends_on = None
CK_WAC_ORIGEM = "origem IN ('PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO','CONFIRMACAO_OPERACIONAL','PORTAL_PROFISSIONAL','WHATSAPP_PARAR','ENCERRAMENTO','TROCA_TELEFONE')"
OLD_CK_WAC_ORIGEM = "origem IN ('PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO','PORTAL_PROFISSIONAL','WHATSAPP_PARAR','ENCERRAMENTO','TROCA_TELEFONE')"
CK_WAC_EVIDENCIA = "estado <> 'AUTORIZADA' OR (origem IN ('PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO') AND usuario_id IS NOT NULL AND chave IS NOT NULL AND referencia_evidencia IS NOT NULL AND length(trim(referencia_evidencia)) >= 8 AND evidencia_sha256 IS NOT NULL AND length(evidencia_sha256) = 64 AND motivo IS NULL) OR (estado='AUTORIZADA' AND origem='CONFIRMACAO_OPERACIONAL' AND usuario_id IS NOT NULL AND chave IS NOT NULL AND referencia_evidencia IS NULL AND evidencia_sha256 IS NULL AND motivo IS NULL)"
OLD_CK_WAC_EVIDENCIA = "estado <> 'AUTORIZADA' OR (origem IN ('PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO') AND usuario_id IS NOT NULL AND chave IS NOT NULL AND referencia_evidencia IS NOT NULL AND length(trim(referencia_evidencia)) >= 8 AND evidencia_sha256 IS NOT NULL AND length(evidencia_sha256) = 64 AND motivo IS NULL)"

def upgrade():
    op.execute("""CREATE TABLE whatsapp_confirmacoes_operacionais (
        autorizacao_id INTEGER PRIMARY KEY REFERENCES whatsapp_autorizacoes_comunicacao(id) ON DELETE RESTRICT,
        modalidade VARCHAR(24) NOT NULL,
        versao_atestacao VARCHAR(16) NOT NULL,
        texto_atestacao VARCHAR(1000) NOT NULL,
        CONSTRAINT ck_wco_modalidade CHECK (modalidade IN ('PRESENCIAL','TELEFONE','CANAL_ELETRONICO')),
        CONSTRAINT ck_wco_atestacao CHECK (versao_atestacao='v1' AND length(trim(texto_atestacao))>0)
    )""")
    for name, expression in [('ck_wac_origem', CK_WAC_ORIGEM), ('ck_wac_evidencia', CK_WAC_EVIDENCIA)]:
        op.drop_constraint(name, 'whatsapp_autorizacoes_comunicacao', type_='check')
        op.create_check_constraint(name, 'whatsapp_autorizacoes_comunicacao', expression)
    op.execute('CREATE TRIGGER whatsapp_writer_fence BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON whatsapp_confirmacoes_operacionais FOR EACH STATEMENT EXECUTE FUNCTION whatsapp_protocol_fence()')
    op.execute('CREATE TRIGGER whatsapp_operational_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON whatsapp_confirmacoes_operacionais FOR EACH STATEMENT EXECUTE FUNCTION whatsapp_agenda_audit_immutable()')
    op.execute("""CREATE FUNCTION whatsapp_operational_complete() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE identity INTEGER; source TEXT;
    BEGIN
      IF TG_TABLE_NAME='whatsapp_autorizacoes_comunicacao' THEN identity=NEW.id;
      ELSE identity=NEW.autorizacao_id; END IF;
      SELECT origem INTO source FROM whatsapp_autorizacoes_comunicacao WHERE id=identity;
      IF (source='CONFIRMACAO_OPERACIONAL') IS DISTINCT FROM
         (EXISTS(SELECT 1 FROM whatsapp_confirmacoes_operacionais WHERE autorizacao_id=identity)) THEN
        RAISE EXCEPTION 'Operational confirmation metadata mismatch' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$""")
    for table in ('whatsapp_autorizacoes_comunicacao','whatsapp_confirmacoes_operacionais'):
        op.execute(f'CREATE CONSTRAINT TRIGGER whatsapp_operational_complete AFTER INSERT ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION whatsapp_operational_complete()')

def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM whatsapp_confirmacoes_operacionais) THEN
        RAISE EXCEPTION 'Operational confirmations exist; downgrade refused';
      END IF;
    END $$""")
    for table in ('whatsapp_autorizacoes_comunicacao','whatsapp_confirmacoes_operacionais'):
        op.execute(f'DROP TRIGGER whatsapp_operational_complete ON {table}')
    op.execute('DROP FUNCTION whatsapp_operational_complete()')
    for name, expression in [('ck_wac_origem', OLD_CK_WAC_ORIGEM), ('ck_wac_evidencia', OLD_CK_WAC_EVIDENCIA)]:
        op.drop_constraint(name, 'whatsapp_autorizacoes_comunicacao', type_='check')
        op.create_check_constraint(name, 'whatsapp_autorizacoes_comunicacao', expression)
    op.drop_table('whatsapp_confirmacoes_operacionais')
