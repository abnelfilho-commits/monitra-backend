"""normalize cardio formulario tipo

Revision ID: 6d13389c3a8f
Revises: 62740b46b634
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "6d13389c3a8f"
down_revision: Union[str, Sequence[str], None] = "62740b46b634"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE formularios_modulo
        SET tipo = 'REGISTRO_DIARIO'
        WHERE modulo_id = 2
          AND LOWER(tipo) = 'registro_diario';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE formularios_modulo
        SET tipo = 'registro_diario'
        WHERE modulo_id = 2
          AND tipo = 'REGISTRO_DIARIO';
    """)