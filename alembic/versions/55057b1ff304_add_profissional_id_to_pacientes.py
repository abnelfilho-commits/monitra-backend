"""add profissional_id to pacientes

Revision ID: 55057b1ff304
Revises: de86dbaaa645
Create Date: 2026-03-24 19:45:50.042837
"""

from alembic import op
import sqlalchemy as sa


revision = "55057b1ff304"
down_revision = "de86dbaaa645"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pacientes",
        sa.Column("profissional_id", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("pacientes", "profissional_id")
