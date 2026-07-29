"""adiciona ocupacao ao profissional

Revision ID: fb27d5139e1e
Revises: c75f02a84258
Create Date: 2026-07-24 09:23:19.991767
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fb27d5139e1e"
down_revision: Union[str, Sequence[str], None] = "c75f02a84258"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profissionais",
        sa.Column(
            "ocupacao_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_profissionais_ocupacao_id",
        "profissionais",
        "ocupacoes_profissionais",
        ["ocupacao_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_profissionais_ocupacao_id",
        "profissionais",
        type_="foreignkey",
    )

    op.drop_column(
        "profissionais",
        "ocupacao_id",
    )