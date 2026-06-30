"""adiciona codigo formularios

Revision ID: f24360467758
Revises: 9dc9aeb87217
Create Date: 2026-06-26 18:54:09.777506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f24360467758'
down_revision: Union[str, Sequence[str], None] = '9dc9aeb87217'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.add_column(
        "formularios_modulo",
        sa.Column(
            "codigo",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.execute("""
        UPDATE formularios_modulo
        SET codigo = 'MCHAT'
        WHERE nome = 'M-CHAT';
    """)

    op.execute("""
        UPDATE formularios_modulo
        SET codigo = UPPER(
            REPLACE(
                REPLACE(nome, '-', ''),
                ' ', '_'
            )
        )
        WHERE codigo IS NULL;
    """)

    op.alter_column(
        "formularios_modulo",
        "codigo",
        nullable=False,
    )

def downgrade() -> None:

    op.drop_column(
        "formularios_modulo",
        "codigo",
    )
