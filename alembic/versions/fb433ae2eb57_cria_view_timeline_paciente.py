"""cria view timeline paciente

Revision ID: fb433ae2eb57
Revises: f45bc791bc71
Create Date: 2026-06-08
"""

from alembic import op


revision = "fb433ae2eb57"
down_revision = "f45bc791bc71"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    DROP VIEW IF EXISTS vw_timeline_paciente;

    CREATE VIEW vw_timeline_paciente AS
    SELECT
        rd.id AS id,
        rd.paciente_id AS paciente_id,
        'REGISTRO_DIARIO'::varchar AS tipo_evento,
        rd.data::timestamp AS data,
        rd.observacao::text AS descricao,
        NULL::integer AS usuario_id,
        COALESCE(rd.origem, 'PROFISSIONAL')::varchar AS origem,
        rd.sono_qualidade::varchar AS sono_qualidade,
        rd.irritabilidade::varchar AS irritabilidade,
        rd.crise_sensorial::boolean AS crise_sensorial
    FROM registros_diarios rd

    UNION ALL

    SELECT
        i.id AS id,
        i.paciente_id AS paciente_id,
        'INTERVENCAO'::varchar AS tipo_evento,
        i.data_intervencao AS data,
        i.descricao::text AS descricao,
        i.profissional_id AS usuario_id,
        'PROFISSIONAL'::varchar AS origem,
        NULL::varchar AS sono_qualidade,
        NULL::varchar AS irritabilidade,
        NULL::boolean AS crise_sensorial
    FROM intervencoes i;
    """)


def downgrade():
    op.execute("DROP VIEW IF EXISTS vw_timeline_paciente;")