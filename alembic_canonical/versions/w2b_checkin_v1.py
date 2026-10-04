"""Canonical wellbeing form and transversal respondent/recorder provenance."""
from alembic import op
import sqlalchemy as sa

revision = 'w2b_checkin_v1'
down_revision = 'w2a_saude_mental_v1'
branch_labels = None
depends_on = None

CODE = 'BEM_ESTAR_V1'
NAME = 'Check-in de Bem-Estar'
OPTIONS = [('MUITO_RUIM','Muito ruim'),('RUIM','Ruim'),('REGULAR','Regular'),('BOM','Bom'),('MUITO_BOM','Muito bom')]
INTENSITY = [('NENHUMA','Nenhuma'),('POUCA','Pouca'),('MODERADA','Moderada'),('MUITA','Muita'),('EXTREMA','Extrema')]
YES_NO = [('SIM','Sim'),('NAO','Não')]
FIELDS = [
 ('humor','Como você percebe seu humor hoje?', OPTIONS),
 ('ansiedade','Quanta ansiedade ou tensão você percebe hoje?', INTENSITY),
 ('estresse','Quanto estresse você percebe hoje?', INTENSITY),
 ('sono','Como você percebe seu sono?', OPTIONS),
 ('energia','Como você percebe sua energia hoje?', OPTIONS),
 ('funcionamento','Como você percebe sua capacidade de realizar as atividades do dia?', OPTIONS),
 ('trabalho','Como você percebe seu bem-estar em relação ao trabalho?', OPTIONS + [('NAO_SE_APLICA','Não se aplica')]),
 ('evento_relevante','Houve algum evento relevante que gostaria de registrar?', YES_NO),
 ('pedido_ajuda','Você gostaria de receber apoio ou conversar com um profissional?', YES_NO),
 ('evento_descricao','Descrição do evento (opcional)', []),
]


def upgrade():
    c = op.get_bind()
    c.exec_driver_sql('LOCK TABLE formularios_modulo, campos_formulario IN SHARE ROW EXCLUSIVE MODE')
    if c.execute(sa.text("SELECT count(*) FROM modulos_clinicos WHERE id=3 AND slug='saude_mental' AND ativo")).scalar()!=1:
        raise RuntimeError('CHECKIN_MODULE_CONFLICT')
    if c.execute(sa.text("SELECT EXISTS(SELECT FROM formularios_modulo WHERE codigo=:code OR (modulo_id=3 AND nome=:name))"),dict(code=CODE,name=NAME)).scalar():
        raise RuntimeError('CHECKIN_FORM_CONFLICT')
    op.create_table('registro_proveniencias',
        sa.Column('registro_id',sa.Integer(),sa.ForeignKey('registros_longitudinais.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('respondente_pessoa_id',sa.Integer(),sa.ForeignKey('pessoas.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('registrador_pessoa_id',sa.Integer(),sa.ForeignKey('pessoas.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('registrador_profissional_id',sa.Integer(),sa.ForeignKey('profissionais.id',ondelete='RESTRICT')),
        sa.Column('canal',sa.String(32),nullable=False),sa.Column('modalidade',sa.String(16),nullable=False),
        sa.CheckConstraint("(modalidade='ASSISTIDO' AND canal='PORTAL_PROFISSIONAL' AND registrador_profissional_id IS NOT NULL) OR "
            "(modalidade='AUTORRELATO' AND canal='WHATSAPP' AND registrador_profissional_id IS NULL AND registrador_pessoa_id=respondente_pessoa_id)",name='ck_registro_proveniencia_modalidade'))
    form=c.execute(sa.text("INSERT INTO formularios_modulo(modulo_id,nome,tipo,ativo,codigo) VALUES (3,:name,'LONGITUDINAL',true,:code) RETURNING id"),dict(name=NAME,code=CODE)).scalar_one()
    fields=sa.table('campos_formulario',sa.column('formulario_id',sa.Integer),sa.column('nome_campo',sa.String),sa.column('label',sa.String),sa.column('tipo_campo',sa.String),sa.column('obrigatorio',sa.Boolean),sa.column('ordem',sa.Integer),sa.column('opcoes',sa.JSON),sa.column('regra_exibicao',sa.JSON),sa.column('ativo',sa.Boolean))
    c.execute(fields.insert(),[dict(formulario_id=form,nome_campo=name,label=label,tipo_campo='radio' if options else 'textarea',obrigatorio=bool(options),ordem=i,opcoes=[dict(valor=v,label=l) for v,l in options],regra_exibicao={'campo':'evento_relevante','valor':'SIM'} if not options else None,ativo=True) for i,(name,label,options) in enumerate(FIELDS,1)])


def downgrade():
    c=op.get_bind()
    if c.exec_driver_sql("SHOW transaction_isolation").scalar() != "read committed":
        raise RuntimeError("READ_COMMITTED_REQUIRED")
    c.exec_driver_sql('LOCK TABLE formularios_modulo, campos_formulario, registros_longitudinais, respostas_registro, registro_proveniencias IN ACCESS EXCLUSIVE MODE')
    if c.execute(sa.text("SELECT EXISTS(SELECT FROM registro_proveniencias) OR EXISTS(SELECT FROM registros_longitudinais WHERE formulario_id IN (SELECT id FROM formularios_modulo WHERE codigo=:code)) OR EXISTS(SELECT FROM respostas_registro WHERE campo_id IN (SELECT c.id FROM campos_formulario c JOIN formularios_modulo f ON f.id=c.formulario_id WHERE f.codigo=:code))"),dict(code=CODE)).scalar():
        raise RuntimeError('CHECKIN_HISTORY_PRESENT')
    c.execute(sa.text('DELETE FROM campos_formulario WHERE formulario_id IN (SELECT id FROM formularios_modulo WHERE codigo=:code)'),dict(code=CODE))
    c.execute(sa.text('DELETE FROM formularios_modulo WHERE codigo=:code'),dict(code=CODE))
    op.drop_table('registro_proveniencias')
