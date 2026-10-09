"""Transversal aggregate; legacy view stays unchanged, no patient-level output."""
from sqlalchemy import text
from fastapi import HTTPException

SUPPORTED = ('neurodesenvolvimento', 'cardiometabolico', 'saude_mental')


def demand(db, linha):
    if linha not in ('todas', *SUPPORTED):
        raise HTTPException(422, 'Linha de cuidado não suportada.')
    # Every contextual AgendaCuidado contributes once. Applicability is an EXISTS,
    # never a join that expands a planning row across an activity's care lines.
    return list(db.execute(text("""
        WITH fontes AS (
            SELECT d.ocupacao_id, d.ocupacao_nome, d.total_planejamentos, d.minutos_semanais
            FROM vw_dimensionamento_ocupacao d
            JOIN modulos_clinicos m ON m.id=d.modulo_id
            WHERE m.slug IN ('neurodesenvolvimento','cardiometabolico')
              AND (:linha='todas' OR m.slug=:linha)
            UNION ALL
            SELECT ac.ocupacao_id, o.nome, count(*), sum(ac.frequencia_semanal*ac.duracao_minutos)
            FROM agenda_cuidados ac
            JOIN pts p ON p.id=ac.pts_id
            JOIN pts_objetivos ob ON ob.id=ac.objetivo_id AND ob.pts_id=p.id
            JOIN modulos_clinicos m ON m.id=p.modulo_id AND m.slug='saude_mental'
            JOIN contextos_assistenciais c ON c.id=p.contexto_assistencial_id AND c.paciente_id=p.paciente_id
            JOIN contexto_assistencial_linhas cl ON cl.contexto_assistencial_id=c.id AND cl.modulo_id=p.modulo_id
            JOIN paciente_instituicoes pi ON pi.id=c.paciente_instituicao_id
              AND pi.paciente_id=c.paciente_id AND pi.instituicao_id=c.instituicao_id
            JOIN instituicoes i ON i.id=c.instituicao_id
            JOIN ocupacoes_profissionais o ON o.id=ac.ocupacao_id
            JOIN atividades_terapeuticas a ON a.id=ac.atividade_id
            WHERE ac.status='PLANEJADO' AND p.status='ATIVO'
              AND c.ativo AND cl.ativo AND pi.ativo AND i.ativo AND m.ativo
              AND (:linha='todas' OR :linha=m.slug)
              AND (EXISTS (SELECT 1 FROM atividade_modulos am WHERE am.atividade_id=a.id AND am.modulo_id=p.modulo_id)
                OR (NOT EXISTS (SELECT 1 FROM atividade_modulos am WHERE am.atividade_id=a.id) AND a.modulo_id=p.modulo_id))
            GROUP BY ac.ocupacao_id,o.nome
        ), carga AS (
            SELECT ocupacao_id,ocupacao_nome,sum(total_planejamentos) AS total_planejamentos,
              sum(minutos_semanais) AS minutos_semanais
            FROM fontes GROUP BY ocupacao_id,ocupacao_nome
        ), horas AS (
            SELECT *,round(minutos_semanais::numeric/60.0,2) AS horas_semanais,
              round(minutos_semanais::numeric/60.0*4.33,2) AS horas_mensais,
              round(minutos_semanais::numeric/60.0*52,2) AS horas_anuais
            FROM carga
        )
        SELECT *,round(horas_semanais/40.0,2) AS fte FROM horas
        ORDER BY horas_semanais DESC,ocupacao_id
    """), dict(linha=linha)).mappings().all())
