"""add profissional_id to pacientes

Revision ID: 55057b1ff304
Revises: 0847577a7792
Create Date: 2026-03-24 19:45:50.042837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision  = '55057b1ff304'
down_revision = "de86dbaaa645"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("pacientes", sa.Column("profissional_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pacientes_profissional_id",
        "pacientes",
        "profissionais",
        ["profissional_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_pacientes_profissional_id", "pacientes", type_="foreignkey")
    op.drop_column("pacientes", "profissional_id")
