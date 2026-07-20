"""cria whatsapp conversas

Revision ID: c75f02a84258
Revises: a2464f3d64fc
Create Date: 2026-07-18 17:21:39.742304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c75f02a84258'
down_revision: Union[str, Sequence[str], None] = 'a2464f3d64fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "whatsapp_conversas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("responsavel_id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=True),
        sa.Column("telefone", sa.String(length=30), nullable=False),
        sa.Column("etapa_atual", sa.String(length=50), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=True),
        sa.Column("respostas_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["responsavel_id"],
            ["responsaveis.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_whatsapp_conversas_paciente_id",
        "whatsapp_conversas",
        ["paciente_id"],
        unique=False,
    )

    op.create_index(
        "ix_whatsapp_conversas_responsavel_id",
        "whatsapp_conversas",
        ["responsavel_id"],
        unique=False,
    )

    op.create_index(
        "ix_whatsapp_conversas_telefone",
        "whatsapp_conversas",
        ["telefone"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_whatsapp_conversas_telefone",
        table_name="whatsapp_conversas",
    )

    op.drop_index(
        "ix_whatsapp_conversas_responsavel_id",
        table_name="whatsapp_conversas",
    )

    op.drop_index(
        "ix_whatsapp_conversas_paciente_id",
        table_name="whatsapp_conversas",
    )

    op.drop_table("whatsapp_conversas")