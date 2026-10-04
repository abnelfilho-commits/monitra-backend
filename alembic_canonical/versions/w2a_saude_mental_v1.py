"""Add only the Mental Health care-line catalogue entry; no clinical backfill."""
from alembic import op
import sqlalchemy as sa

revision = 'w2a_saude_mental_v1'
down_revision = 'w1c_isolamento_legado_v1'
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    c.execute(sa.text('LOCK TABLE public.modulos_clinicos IN SHARE ROW EXCLUSIVE MODE'))
    if c.execute(sa.text("SELECT EXISTS(SELECT FROM public.modulos_clinicos WHERE id=3 OR slug='saude_mental')")).scalar():
        raise RuntimeError('MENTAL_HEALTH_CATALOG_CONFLICT')
    c.execute(sa.text("INSERT INTO public.modulos_clinicos(id,nome,slug,ativo) VALUES (3,'Saúde Mental','saude_mental',true)"))
    # A transactional restart avoids a future generated ID colliding with the seed.
    next_id = c.execute(sa.text("SELECT GREATEST((SELECT max(id)+1 FROM public.modulos_clinicos), (SELECT last_value+1 FROM public.modulos_clinicos_id_seq))")).scalar_one()
    c.exec_driver_sql('ALTER SEQUENCE public.modulos_clinicos_id_seq RESTART WITH ' + str(int(next_id)))


def downgrade():
    c = op.get_bind()
    c.execute(sa.text('LOCK TABLE public.modulos_clinicos IN ACCESS EXCLUSIVE MODE'))
    inspector = sa.inspect(c)
    quote = c.dialect.identifier_preparer.quote
    # Even legacy CASCADE FKs must not remove clinical/operational relationships.
    for table in inspector.get_table_names(schema='public'):
        for fk in inspector.get_foreign_keys(table, schema='public'):
            if fk['referred_table'] == 'modulos_clinicos':
                if fk['referred_columns'] != ['id'] or len(fk['constrained_columns']) != 1:
                    raise RuntimeError('MENTAL_HEALTH_UNKNOWN_DEPENDENCY')
                column = fk['constrained_columns'][0]
                sql = 'SELECT EXISTS(SELECT FROM public.' + quote(table) + ' WHERE ' + quote(column) + '=3)'
                if c.exec_driver_sql(sql).scalar():
                    raise RuntimeError('MENTAL_HEALTH_HAS_DEPENDENCIES')
    c.execute(sa.text("DELETE FROM public.modulos_clinicos WHERE id=3 AND slug='saude_mental'"))
