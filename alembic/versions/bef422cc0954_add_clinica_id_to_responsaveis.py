"""add clinica_id to responsaveis

Revision ID: bef422cc0954
Revises: f24360467758
Create Date: 2026-07-08 04:59:58.637106

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bef422cc0954"
down_revision: Union[str, Sequence[str], None] = "f24360467758"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "responsaveis",
        sa.Column(
            "clinica_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_responsaveis_clinica_id",
        "responsaveis",
        ["clinica_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_responsaveis_clinica_id",
        "responsaveis",
        "clinicas",
        ["clinica_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_responsaveis_clinica_id",
        "responsaveis",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_responsaveis_clinica_id",
        table_name="responsaveis",
    )

    op.drop_column(
        "responsaveis",
        "clinica_id",
    )