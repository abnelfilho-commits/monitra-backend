"""sync hml cardiometabolico

Revision ID: 62740b46b634
Revises: fb433ae2eb57
Create Date: 2026-06-10 10:51:50.205832
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "62740b46b634"
down_revision: Union[str, Sequence[str], None] = "fb433ae2eb57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE pacientes
        ADD COLUMN IF NOT EXISTS altura NUMERIC(4, 2);
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE pacientes
        DROP COLUMN IF EXISTS altura;
    """)