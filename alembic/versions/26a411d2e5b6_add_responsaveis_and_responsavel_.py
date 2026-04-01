"""add responsaveis and responsavel_paciente

Revision ID: add_responsaveis_responsavel_paciente
Revises: de86dbaaa645
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "26a411d2e5b6"
down_revision = "0847577a7792"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "responsaveis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("senha_hash", sa.String(), nullable=False),
        sa.Column("telefone", sa.String(), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_responsaveis_id", "responsaveis", ["id"], unique=False)
    op.create_index("ix_responsaveis_email", "responsaveis", ["email"], unique=True)

    op.create_table(
        "responsavel_paciente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("responsavel_id", sa.Integer(), nullable=False),
        sa.Column("paciente_id", sa.Integer(), nullable=False),
        sa.Column("parentesco", sa.String(), nullable=True),
        sa.Column("principal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["responsavel_id"], ["responsaveis.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paciente_id"], ["pacientes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("responsavel_id", "paciente_id", name="uq_responsavel_paciente"),
    )
    op.create_index("ix_responsavel_paciente_id", "responsavel_paciente", ["id"], unique=False)
    op.create_index("ix_responsavel_paciente_responsavel_id", "responsavel_paciente", ["responsavel_id"], unique=False)
    op.create_index("ix_responsavel_paciente_paciente_id", "responsavel_paciente", ["paciente_id"], unique=False)

    op.add_column("registros_diarios", sa.Column("origem", sa.String(), nullable=True))
    op.add_column("registros_diarios", sa.Column("responsavel_id", sa.Integer(), nullable=True))
    op.add_column("registros_diarios", sa.Column("criado_por_tipo", sa.String(), nullable=True))
    op.add_column("registros_diarios", sa.Column("criado_por_id", sa.Integer(), nullable=True))

    op.create_index("ix_registros_diarios_origem", "registros_diarios", ["origem"], unique=False)
    op.create_index("ix_registros_diarios_responsavel_id", "registros_diarios", ["responsavel_id"], unique=False)

    op.create_foreign_key(
        "fk_registros_diarios_responsavel_id",
        "registros_diarios",
        "responsaveis",
        ["responsavel_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_registros_diarios_responsavel_id", "registros_diarios", type_="foreignkey")

    op.drop_index("ix_registros_diarios_responsavel_id", table_name="registros_diarios")
    op.drop_index("ix_registros_diarios_origem", table_name="registros_diarios")

    op.drop_column("registros_diarios", "criado_por_id")
    op.drop_column("registros_diarios", "criado_por_tipo")
    op.drop_column("registros_diarios", "responsavel_id")
    op.drop_column("registros_diarios", "origem")

    op.drop_index("ix_responsavel_paciente_paciente_id", table_name="responsavel_paciente")
    op.drop_index("ix_responsavel_paciente_responsavel_id", table_name="responsavel_paciente")
    op.drop_index("ix_responsavel_paciente_id", table_name="responsavel_paciente")
    op.drop_table("responsavel_paciente")

    op.drop_index("ix_responsaveis_email", table_name="responsaveis")
    op.drop_index("ix_responsaveis_id", table_name="responsaveis")
    op.drop_table("responsaveis")
