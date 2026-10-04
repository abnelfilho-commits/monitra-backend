"""Legacy view isolation only; historical two-source timeline preserved if present."""
from alembic import op

revision = 'w1c_isolamento_legado_v1'
down_revision = 'w1c_contexto_clinico_v1'
branch_labels = None
depends_on = None

DIMENSION = """ SELECT p.modulo_id,
    ac.ocupacao_id,
    op.nome AS ocupacao_nome,
    count(*) AS total_planejamentos,
    sum(ac.frequencia_semanal * ac.duracao_minutos) AS minutos_semanais,
    round(sum(ac.frequencia_semanal * ac.duracao_minutos)::numeric / 60.0, 2) AS horas_semanais,
    round(sum(ac.frequencia_semanal * ac.duracao_minutos)::numeric / 60.0 * 4.33, 2) AS horas_mensais,
    round(sum(ac.frequencia_semanal * ac.duracao_minutos)::numeric / 60.0 * 52::numeric, 2) AS horas_anuais
   FROM agenda_cuidados ac
     JOIN pts p ON p.id = ac.pts_id
     JOIN ocupacoes_profissionais op ON op.id = ac.ocupacao_id
  WHERE ac.status::text = 'PLANEJADO'::text
  GROUP BY p.modulo_id, ac.ocupacao_id, op.nome;"""
TIMELINE = """SELECT
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
    FROM intervencoes i"""

def replace_views(protected):
    connection = op.get_bind()
    dimension = DIMENSION.replace("WHERE ac.status", "WHERE p.contexto_assistencial_id IS NULL AND ac.status") if protected else DIMENSION
    op.execute('CREATE OR REPLACE VIEW public.vw_dimensionamento_ocupacao AS ' + dimension)
    # M0 deliberately excludes this residual view from new installations.
    # Preserve absence; never activate a residual product path.
    if connection.exec_driver_sql("SELECT to_regclass('public.vw_timeline_paciente')").scalar() is not None:
        timeline = TIMELINE + (' WHERE i.contexto_assistencial_id IS NULL' if protected else '')
        op.execute('CREATE OR REPLACE VIEW public.vw_timeline_paciente AS ' + timeline)


def upgrade():
    replace_views(True)


def downgrade():
    replace_views(False)
