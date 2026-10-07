"""Add PHQ-9 catalogue to the existing assessment framework; no new tables; preserve full instrument wording."""
from alembic import op
import sqlalchemy as sa

revision = 'w3_phq9_v1'
down_revision = 'w3_intervencao_autoria_v1'
branch_labels = None
depends_on = None

CODE = 'PHQ9'
NAME = 'PHQ-9'
INSTRUCTION = 'Durante as últimas 2 semanas, com que frequência você foi incomodado/a por qualquer um dos problemas abaixo?'
OPTIONS = [('0','Nenhuma vez'),('1','Vários dias'),('2','Mais da metade dos dias'),('3','Quase todos os dias')]
QUESTIONS = [
 'Pouco interesse ou pouco prazer em fazer as coisas',
 'Se sentir “para baixo”, deprimido/a ou sem perspectiva',
 'Dificuldade para pegar no sono ou permanecer dormindo, ou dormir mais do que de costume',
 'Se sentir cansado/a ou com pouca energia',
 'Falta de apetite ou comendo demais',
 'Se sentir mal consigo mesmo/a — ou achar que você é um fracasso ou que decepcionou sua família ou você mesmo/a',
 'Dificuldade para se concentrar nas coisas, como ler o jornal ou ver televisão',
 'Lentidão para se movimentar ou falar, a ponto das outras pessoas perceberem? Ou o oposto – estar tão agitado/a ou irrequieto/a que você fica andando de um lado para o outro muito mais do que de costume',
 'Pensar em se ferir de alguma maneira ou que seria melhor estar morto/a',
]
FIELDS = [(f'phq9_{i}', question, OPTIONS) for i, question in enumerate(QUESTIONS,1)]


def upgrade():
    c = op.get_bind()
    c.exec_driver_sql('LOCK TABLE formularios_modulo, campos_formulario IN SHARE ROW EXCLUSIVE MODE')
    if c.execute(sa.text("SELECT count(*) FROM modulos_clinicos WHERE id=3 AND slug='saude_mental' AND ativo")).scalar()!=1:
        raise RuntimeError('PHQ9_MODULE_CONFLICT')
    if c.execute(sa.text("SELECT EXISTS(SELECT FROM formularios_modulo WHERE codigo=:code OR (modulo_id=3 AND nome=:name))"),dict(code=CODE,name=NAME)).scalar():
        raise RuntimeError('PHQ9_FORM_CONFLICT')
    op.alter_column('campos_formulario', 'label', existing_type=sa.String(200), type_=sa.Text(), existing_nullable=False)
    form=c.execute(sa.text("INSERT INTO formularios_modulo(modulo_id,nome,tipo,ativo,codigo) VALUES (3,:name,'ASSESSMENT',true,:code) RETURNING id"),dict(name=NAME,code=CODE)).scalar_one()
    fields=sa.table('campos_formulario',sa.column('formulario_id',sa.Integer),sa.column('nome_campo',sa.String),sa.column('label',sa.String),sa.column('tipo_campo',sa.String),sa.column('obrigatorio',sa.Boolean),sa.column('ordem',sa.Integer),sa.column('opcoes',sa.JSON),sa.column('regra_exibicao',sa.JSON),sa.column('ativo',sa.Boolean))
    c.execute(fields.insert(),[dict(formulario_id=form,nome_campo=name,label=label,tipo_campo='radio',obrigatorio=True,ordem=i,opcoes=[dict(valor=v,label=l) for v,l in options],regra_exibicao=None,ativo=True) for i,(name,label,options) in enumerate(FIELDS,1)])


def downgrade():
    c=op.get_bind()
    if c.exec_driver_sql("SHOW transaction_isolation").scalar() != "read committed":
        raise RuntimeError("READ_COMMITTED_REQUIRED")
    c.exec_driver_sql('LOCK TABLE formularios_modulo, campos_formulario, registros_longitudinais, respostas_registro, avaliacoes_clinicas IN ACCESS EXCLUSIVE MODE')
    if c.execute(sa.text("SELECT EXISTS(SELECT FROM avaliacoes_clinicas WHERE instrumento='PHQ9') OR EXISTS(SELECT FROM registros_longitudinais WHERE formulario_id IN (SELECT id FROM formularios_modulo WHERE codigo=:code)) OR EXISTS(SELECT FROM respostas_registro WHERE campo_id IN (SELECT c.id FROM campos_formulario c JOIN formularios_modulo f ON f.id=c.formulario_id WHERE f.codigo=:code))"),dict(code=CODE)).scalar():
        raise RuntimeError('PHQ9_HISTORY_PRESENT')
    c.execute(sa.text('DELETE FROM campos_formulario WHERE formulario_id IN (SELECT id FROM formularios_modulo WHERE codigo=:code)'),dict(code=CODE))
    c.execute(sa.text('DELETE FROM formularios_modulo WHERE codigo=:code'),dict(code=CODE))

    if c.execute(sa.text('SELECT EXISTS(SELECT FROM campos_formulario WHERE length(label)>200)')).scalar():
        raise RuntimeError('LONG_QUESTION_LABEL_PRESENT')
    op.alter_column('campos_formulario', 'label', existing_type=sa.Text(), type_=sa.String(200), existing_nullable=False)
