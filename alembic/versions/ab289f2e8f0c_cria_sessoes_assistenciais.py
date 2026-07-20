"""cria sessoes assistenciais

Revision ID: ab289f2e8f0c
Revises: bef422cc0954
Create Date: 2026-07-14 17:33:43.768300

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab289f2e8f0c'
down_revision: Union[str, Sequence[str], None] = 'bef422cc0954'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Evolução do Planejamento Assistencial existente.
    #
    # Os campos começam como opcionais porque já existem registros
    # em agenda_cuidados. Depois da atualização dos dados antigos,
    # poderemos avaliar se quantidade_sessoes deve virar obrigatória.
    op.add_column(
        "agenda_cuidados",
        sa.Column(
            "quantidade_sessoes",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "agenda_cuidados",
        sa.Column(
            "profissional_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "agenda_cuidados_profissional_id_fkey",
        "agenda_cuidados",
        "profissionais",
        ["profissional_id"],
        ["id"],
    )

    op.create_index(
        "ix_agenda_cuidados_profissional_id",
        "agenda_cuidados",
        ["profissional_id"],
        unique=False,
    )

    # Nova unidade operacional do cuidado.
    op.create_table(
        "sessoes_assistenciais",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "agenda_cuidado_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "paciente_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "profissional_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "numero_sessao",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "data_agendada",
            sa.Date(),
            nullable=False,
        ),

        sa.Column(
            "hora_inicio",
            sa.Time(),
            nullable=True,
        ),

        sa.Column(
            "hora_fim",
            sa.Time(),
            nullable=True,
        ),

        sa.Column(
            "duracao_minutos",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="AGENDADA",
        ),

        sa.Column(
            "data_realizacao",
            sa.Date(),
            nullable=True,
        ),

        sa.Column(
            "hora_inicio_real",
            sa.Time(),
            nullable=True,
        ),

        sa.Column(
            "hora_fim_real",
            sa.Time(),
            nullable=True,
        ),

        sa.Column(
            "observacoes",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "motivo_falta",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "motivo_cancelamento",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "motivo_reagendamento",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "sessao_origem_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "registro_longitudinal_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.ForeignKeyConstraint(
            ["agenda_cuidado_id"],
            ["agenda_cuidados.id"],
            name="sessoes_assistenciais_agenda_cuidado_id_fkey",
        ),

        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            name="sessoes_assistenciais_paciente_id_fkey",
        ),

        sa.ForeignKeyConstraint(
            ["profissional_id"],
            ["profissionais.id"],
            name="sessoes_assistenciais_profissional_id_fkey",
        ),

        sa.ForeignKeyConstraint(
            ["sessao_origem_id"],
            ["sessoes_assistenciais.id"],
            name="sessoes_assistenciais_sessao_origem_id_fkey",
        ),

        sa.ForeignKeyConstraint(
            ["registro_longitudinal_id"],
            ["registros_longitudinais.id"],
            name="sessoes_assistenciais_registro_longitudinal_id_fkey",
        ),

        sa.UniqueConstraint(
            "agenda_cuidado_id",
            "numero_sessao",
            name="uq_sessao_agenda_numero",
        ),
    )

    op.create_index(
        "ix_sessoes_assistenciais_agenda_cuidado_id",
        "sessoes_assistenciais",
        ["agenda_cuidado_id"],
        unique=False,
    )

    op.create_index(
        "ix_sessoes_assistenciais_paciente_id",
        "sessoes_assistenciais",
        ["paciente_id"],
        unique=False,
    )

    op.create_index(
        "ix_sessoes_assistenciais_profissional_id",
        "sessoes_assistenciais",
        ["profissional_id"],
        unique=False,
    )

    op.create_index(
        "ix_sessoes_assistenciais_data_agendada",
        "sessoes_assistenciais",
        ["data_agendada"],
        unique=False,
    )

    op.create_index(
        "ix_sessoes_assistenciais_status",
        "sessoes_assistenciais",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sessoes_assistenciais_status",
        table_name="sessoes_assistenciais",
    )

    op.drop_index(
        "ix_sessoes_assistenciais_data_agendada",
        table_name="sessoes_assistenciais",
    )

    op.drop_index(
        "ix_sessoes_assistenciais_profissional_id",
        table_name="sessoes_assistenciais",
    )

    op.drop_index(
        "ix_sessoes_assistenciais_paciente_id",
        table_name="sessoes_assistenciais",
    )

    op.drop_index(
        "ix_sessoes_assistenciais_agenda_cuidado_id",
        table_name="sessoes_assistenciais",
    )

    op.drop_table("sessoes_assistenciais")

    op.drop_index(
        "ix_agenda_cuidados_profissional_id",
        table_name="agenda_cuidados",
    )

    op.drop_constraint(
        "agenda_cuidados_profissional_id_fkey",
        "agenda_cuidados",
        type_="foreignkey",
    )

    op.drop_column(
        "agenda_cuidados",
        "profissional_id",
    )

    op.drop_column(
        "agenda_cuidados",
        "quantidade_sessoes",
    )
