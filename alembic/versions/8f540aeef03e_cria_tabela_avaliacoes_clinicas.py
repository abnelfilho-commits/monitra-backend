"""cria tabela avaliacoes_clinicas

Revision ID: 8f540aeef03e
Revises: 6d13389c3a8f
Create Date: 2026-06-25 20:14:48.849858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f540aeef03e'
down_revision: Union[str, Sequence[str], None] = '6d13389c3a8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "avaliacoes_clinicas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("modulo_id", sa.Integer(), nullable=False),
        sa.Column("formulario_id", sa.Integer(), nullable=True),
        sa.Column("instrumento", sa.String(length=50), nullable=False),
        sa.Column("versao", sa.String(length=20), nullable=True),
        sa.Column("score", sa.Numeric(10, 2), nullable=True),
        sa.Column("score_texto", sa.String(length=100), nullable=True),
        sa.Column("classificacao", sa.String(length=100), nullable=True),
        sa.Column("classificacao_codigo", sa.String(length=50), nullable=True),
        sa.Column("conduta", sa.Text(), nullable=True),
        sa.Column("interpretacao", sa.Text(), nullable=True),
        sa.Column("resultado", sa.JSON(), nullable=True),
        sa.Column("engine_version", sa.String(length=20), nullable=True),
        sa.Column("profissional_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="CONCLUIDA"
        ),
        sa.Column(
            "executado_em",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()")
        ),
    )

    op.create_index(
        "idx_avaliacoes_registro",
        "avaliacoes_clinicas",
        ["registro_id"]
    )

    op.create_index(
        "idx_avaliacoes_paciente",
        "avaliacoes_clinicas",
        ["paciente_id"]
    )

    op.create_index(
        "idx_avaliacoes_modulo",
        "avaliacoes_clinicas",
        ["modulo_id"]
    )

    op.create_index(
        "idx_avaliacoes_instrumento",
        "avaliacoes_clinicas",
        ["instrumento"]
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS avaliacoes_clinicas CASCADE")