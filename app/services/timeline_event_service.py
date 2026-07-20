from datetime import datetime, time

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.diagnostico import Diagnostico

class TimelineEventService:
    @staticmethod
    def coletar_eventos_sessoes(
        db: Session,
        paciente_id: int,
    ):
        sessoes = db.execute(
            text(
                """
                SELECT
                    sa.id,
                    sa.paciente_id,
                    sa.numero_sessao,
                    sa.data_agendada,
                    sa.hora_inicio,
                    sa.status,
                    sa.data_realizacao,
                    sa.hora_inicio_real,
                    sa.hora_fim_real,
                    sa.registro_longitudinal_id,
                    at.nome AS atividade_nome,
                    op.nome AS ocupacao_nome,
                    pr.nome AS profissional_nome

                FROM sessoes_assistenciais sa

                JOIN agenda_cuidados ac
                    ON ac.id = sa.agenda_cuidado_id

                JOIN atividades_terapeuticas at
                    ON at.id = ac.atividade_id

                JOIN ocupacoes_profissionais op
                    ON op.id = ac.ocupacao_id

                LEFT JOIN profissionais pr
                    ON pr.id = COALESCE(
                        sa.profissional_id,
                        ac.profissional_id
                    )

                WHERE sa.paciente_id = :paciente_id
                  AND sa.status = 'REALIZADA'

                ORDER BY
                    sa.data_realizacao DESC,
                    sa.numero_sessao DESC
                """
            ),
            {
                "paciente_id": paciente_id,
            },
        ).fetchall()

        eventos = []

        for sessao in sessoes:
            data_base = (
                sessao.data_realizacao
                or sessao.data_agendada
            )

            data_hora_realizacao = datetime.combine(
                data_base,
                sessao.hora_fim_real or time.min,
            )

            eventos.append(
                {
                    "id": sessao.id,
                    "paciente_id": sessao.paciente_id,
                    "tipo_evento": "SESSAO_REALIZADA",
                    "data": data_hora_realizacao.isoformat(),
                    "descricao": (
                        f"Sessão {sessao.numero_sessao} de "
                        f"{sessao.atividade_nome} realizada."
                    ),
                    "origem": "ASSISTENCIAL",
                    "atividade_nome": sessao.atividade_nome,
                    "ocupacao_nome": sessao.ocupacao_nome,
                    "profissional_nome": sessao.profissional_nome,
                    "numero_sessao": sessao.numero_sessao,
                    "status": sessao.status,
                    "hora_inicio": (
                        sessao.hora_inicio_real.isoformat()
                        if sessao.hora_inicio_real
                        else None
                    ),
                    "hora_fim": (
                        sessao.hora_fim_real.isoformat()
                        if sessao.hora_fim_real
                        else None
                    ),
                    "registro_longitudinal_id": (
                        sessao.registro_longitudinal_id
                    ),
                }
            )

        return eventos
    @staticmethod
    def coletar_eventos_diagnosticos(
        db: Session,
        paciente_id: int,
    ):
        diagnosticos = (
            db.query(Diagnostico)
            .filter(
                Diagnostico.paciente_id == paciente_id,
                Diagnostico.status != "CANCELADO",
            )
            .order_by(
                Diagnostico.data_diagnostico.desc()
            )
            .all()
        )

        eventos = []

        for diagnostico in diagnosticos:

            data_evento = datetime.combine(
                diagnostico.data_diagnostico,
                time.max,
            )

            eventos.append(
                {
                    "id": diagnostico.id,
                    "paciente_id": paciente_id,
                    "tipo_evento": "DIAGNOSTICO",
                    "data": data_evento.isoformat(),

                    "descricao": (
                        f"{diagnostico.cid or ''} "
                        f"{diagnostico.descricao_clinica}"
                    ).strip(),

                    "origem": "ASSISTENCIAL",

                    "cid": diagnostico.cid,

                    "medico_nome":
                        diagnostico.medico_nome,

                    "status":
                        diagnostico.status,
                }
            )

        return eventos

    @staticmethod
    def obter_eventos_paciente(
        db: Session,
        paciente_id: int,
    ):
        eventos = []

        eventos.extend(
            TimelineEventService.coletar_eventos_sessoes(
                db=db,
                paciente_id=paciente_id,
            )
        )

        eventos.extend(
            TimelineEventService.coletar_eventos_diagnosticos(
                db=db,
                paciente_id=paciente_id,
            )
        )

        eventos.sort(
            key=lambda e: e["data"],
            reverse=True,
        )

        return eventos