"""Physical ownership only; no contextual write path, backfill or legacy changes."""
from alembic import op
import sqlalchemy as sa

revision = 'w1c_contexto_clinico_v1'
down_revision = 'w1b_permissoes_v1'
branch_labels = None
depends_on = None

ROOTS = ('registros_longitudinais', 'diagnosticos', 'pts', 'intervencoes')


def upgrade():
    op.create_unique_constraint('uq_contexto_paciente', 'contextos_assistenciais',
                                ['id', 'paciente_id'], schema='public')
    for table in ROOTS:
        op.add_column(table, sa.Column('contexto_assistencial_id', sa.Integer(), nullable=True), schema='public')
        op.create_foreign_key(f'fk_{table}_contexto_paciente', table, 'contextos_assistenciais',
                             ['contexto_assistencial_id', 'paciente_id'], ['id', 'paciente_id'],
                             source_schema='public', referent_schema='public', ondelete='RESTRICT', onupdate='RESTRICT')
        op.create_foreign_key(f'fk_{table}_contexto_linha', table, 'contexto_assistencial_linhas',
                             ['contexto_assistencial_id', 'modulo_id'], ['contexto_assistencial_id', 'modulo_id'],
                             source_schema='public', referent_schema='public', ondelete='RESTRICT', onupdate='RESTRICT')
        op.create_check_constraint(f'ck_{table}_contexto_identidade', table,
                                   'contexto_assistencial_id IS NULL OR (paciente_id IS NOT NULL AND modulo_id IS NOT NULL)', schema='public')
        op.create_index(f'ix_{table}_contexto', table, ['contexto_assistencial_id'], schema='public')
    op.create_index('uq_pts_contexto_linha_ativo', 'pts', ['contexto_assistencial_id', 'modulo_id'],
                    unique=True, postgresql_where=sa.text("contexto_assistencial_id IS NOT NULL AND status = 'ATIVO'"), schema='public')


def downgrade():
    connection = op.get_bind()
    if connection.exec_driver_sql('SHOW transaction_isolation').scalar() != 'read committed':
        raise RuntimeError('W1C_READ_COMMITTED_REQUIRED')
    # Prevent contextual writes between the history check and removal of ownership.
    connection.exec_driver_sql('LOCK TABLE ' + ', '.join('public.' + t for t in ROOTS) + ' IN ACCESS EXCLUSIVE MODE')
    if any(connection.exec_driver_sql('SELECT EXISTS (SELECT 1 FROM public.' + t +
                                      ' WHERE contexto_assistencial_id IS NOT NULL)').scalar() for t in ROOTS):
        raise RuntimeError('W1C_DOWNGRADE_BLOCKED_CONTEXTUAL_HISTORY')
    op.drop_index('uq_pts_contexto_linha_ativo', table_name='pts', schema='public')
    for table in reversed(ROOTS):
        op.drop_index(f'ix_{table}_contexto', table_name=table, schema='public')
        op.drop_constraint(f'ck_{table}_contexto_identidade', table, type_='check', schema='public')
        op.drop_constraint(f'fk_{table}_contexto_linha', table, type_='foreignkey', schema='public')
        op.drop_constraint(f'fk_{table}_contexto_paciente', table, type_='foreignkey', schema='public')
        op.drop_column(table, 'contexto_assistencial_id', schema='public')
    op.drop_constraint('uq_contexto_paciente', 'contextos_assistenciais', type_='unique', schema='public')
