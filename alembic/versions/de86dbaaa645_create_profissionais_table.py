"""create profissionais table

Revision ID: de86dbaaa645
Revises: cef1d38ebe55
Create Date: 2026-03-24 14:40:00.011473

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de86dbaaa645'
down_revision: Union[str, Sequence[str], None] = 'cef1d38ebe55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        'profissionais',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('especialidade', sa.String(), nullable=True),
        sa.Column('clinica_id', sa.Integer(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['clinica_id'], ['clinicas.id']),
    )

def downgrade():
    op.drop_table('profissionais')
