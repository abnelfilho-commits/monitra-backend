"""cria diagnosticos

Revision ID: a2464f3d64fc
Revises: ab289f2e8f0c
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2464f3d64fc"
down_revision: Union[str, None] = "ab289f2e8f0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnosticos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.String(length=30),
            server_default=sa.text("'DIAGNOSTICO'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'ATIVO'"),
            nullable=False,
        ),
        sa.Column(
            "cid",
            sa.String(length=20),
            nullable=True,
        ),
        sa.Column(
            "descricao_clinica",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "data_diagnostico",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "medico_nome",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "medico_especialidade",
            sa.String(length=150),
            nullable=True,
        ),
        sa.Column(
            "medico_crm",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "medico_cpf",
            sa.String(length=20),
            nullable=True,
        ),
        sa.Column(
            "observacoes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_diagnosticos_id",
        "diagnosticos",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_diagnosticos_paciente_id",
        "diagnosticos",
        ["paciente_id"],
        unique=False,
    )

    op.create_index(
        "ix_diagnosticos_cid",
        "diagnosticos",
        ["cid"],
        unique=False,
    )

    op.create_index(
        "ix_diagnosticos_data_diagnostico",
        "diagnosticos",
        ["data_diagnostico"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_diagnosticos_data_diagnostico",
        table_name="diagnosticos",
    )

    op.drop_index(
        "ix_diagnosticos_cid",
        table_name="diagnosticos",
    )

    op.drop_index(
        "ix_diagnosticos_paciente_id",
        table_name="diagnosticos",
    )

    op.drop_index(
        "ix_diagnosticos_id",
        table_name="diagnosticos",
    )

    op.drop_table("diagnosticos")