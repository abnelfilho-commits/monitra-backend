"""Persist the proven source association of the specialized Cardio table."""
from alembic import op
import sqlalchemy as sa

revision = '8c01a0d1a003'
down_revision = '8c01a0d1a002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('intervencoes_cardiometabolicas', sa.Column('modulo_id', sa.Integer(), nullable=True))
    # The physical source is exclusively Cardio, unlike generic interventions.
    connection = op.get_bind()
    cardio = connection.execute(sa.text("SELECT id FROM modulos_clinicos WHERE slug='cardiometabolico'")).scalar()
    if cardio is None:
        raise RuntimeError('Cardio module must exist before upgrading specialized interventions.')
    connection.execute(sa.text('UPDATE intervencoes_cardiometabolicas SET modulo_id=:module'), {'module':cardio})
    op.alter_column('intervencoes_cardiometabolicas', 'modulo_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key('fk_cardio_intervencoes_modulo', 'intervencoes_cardiometabolicas',
                          'modulos_clinicos', ['modulo_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_cardio_intervencoes_modulo', 'intervencoes_cardiometabolicas', type_='foreignkey')
    op.drop_column('intervencoes_cardiometabolicas', 'modulo_id')
