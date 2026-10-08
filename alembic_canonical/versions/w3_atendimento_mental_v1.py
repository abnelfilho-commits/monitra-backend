"""Seed the canonical session attendance form for Mental Health only."""
from alembic import op
import sqlalchemy as sa
revision = 'w3_atendimento_mental_v1'
down_revision = 'w3_atividade_linhas_v1'
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.execute(sa.text("SELECT count(*) FROM formularios_modulo WHERE modulo_id=3 AND codigo='ATENDIMENTO_SESSAO'")).scalar():
        raise RuntimeError('MENTAL_ATTENDANCE_CATALOG_ALREADY_EXISTS')
    identity = c.execute(sa.text("INSERT INTO formularios_modulo(modulo_id,nome,tipo,codigo,ativo) VALUES(3,'Atendimento de sessão','LONGITUDINAL','ATENDIMENTO_SESSAO',true) RETURNING id")).scalar_one()
    for order, name, label, kind, required in [(1,'narrativa_atendimento','Como foi o atendimento?','textarea',True),(2,'proximos_passos','Próximos passos','multiselect',False)]:
        c.execute(sa.text('INSERT INTO campos_formulario(formulario_id,nome_campo,label,tipo_campo,obrigatorio,ordem,ativo) VALUES(:f,:n,:l,:t,:r,:o,true)'),dict(f=identity,n=name,l=label,t=kind,r=required,o=order))


def downgrade():
    op.execute('LOCK TABLE formularios_modulo, campos_formulario, registros_longitudinais IN ACCESS EXCLUSIVE MODE')
    c = op.get_bind()
    ids = c.execute(sa.text("SELECT id FROM formularios_modulo WHERE modulo_id=3 AND codigo='ATENDIMENTO_SESSAO'")).scalars().all()
    for identity in ids:
        if c.execute(sa.text('SELECT EXISTS(SELECT 1 FROM registros_longitudinais WHERE formulario_id=:f)'),dict(f=identity)).scalar():
            raise RuntimeError('MENTAL_ATTENDANCE_RECORDS_PRESENT')
        c.execute(sa.text('DELETE FROM campos_formulario WHERE formulario_id=:f'),dict(f=identity))
        c.execute(sa.text('DELETE FROM formularios_modulo WHERE id=:f'),dict(f=identity))
