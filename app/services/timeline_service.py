"""
Serviço de domínio responsável pela Timeline Clínica.

Nesta primeira versão, atua como uma camada de orquestração,
reutilizando os serviços existentes da plataforma.
"""
from sqlalchemy import text
from datetime import datetime, time, timezone
from sqlalchemy.orm import Session

from app.services.timeline_event_service import (
    TimelineEventService,
)


class TimelineService:
    """
    Serviço institucional da Timeline Clínica.
    """

    @staticmethod
    def get_assistential_events(
        db: Session,
        patient_id: int,
    ):
        """
        Recupera eventos assistenciais estruturados.

        Nesta primeira versão reutiliza o TimelineEventService
        existente, preservando compatibilidade.
        """

        return TimelineEventService.obter_eventos_paciente(
            db=db,
            paciente_id=patient_id,
        )
        
    @staticmethod
    def _iso_timestamp_utc(valor):
        """
        Normaliza timestamps para UTC explícito.
        """

        if valor is None:
            return None

        if not isinstance(valor, datetime):
            valor = datetime.combine(valor, time.min)

        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)

        return valor.astimezone(timezone.utc).isoformat()
    
    @staticmethod
    def get_daily_records(
        db: Session,
        patient_id: int,
    ):
        """
        Recupera os registros diários do paciente.
        """

        registros = db.execute(
            text("""
                SELECT
                    rl.id,
                    rl.paciente_id,
                    rl.data_registro,
                    rl.criado_em,
                    rl.origem,

                    MAX(CASE WHEN cf.nome_campo = 'observacao'
                        THEN rr.valor_texto END) AS observacao

                FROM registros_longitudinais rl

                LEFT JOIN respostas_registro rr
                    ON rr.registro_id = rl.id

                LEFT JOIN campos_formulario cf
                    ON cf.id = rr.campo_id

                WHERE rl.paciente_id = :paciente_id

                GROUP BY
                    rl.id,
                    rl.paciente_id,
                    rl.data_registro,
                    rl.criado_em,
                    rl.origem

                ORDER BY
                    rl.data_registro DESC,
                    rl.id DESC
            """),
            {
                "paciente_id": patient_id,
            },
        ).fetchall()

        eventos = []

        for registro in registros:

            eventos.append(
                {
                    "id": registro.id,
                    "paciente_id": registro.paciente_id,
                    "tipo_evento": "REGISTRO_DIARIO",
                    "data": TimelineService._iso_timestamp_utc(
                        registro.criado_em
                        or registro.data_registro
                    ),
                    "descricao": registro.observacao,
                    "origem": registro.origem or "PROFISSIONAL",
                }
            )

        return eventos
    
    @staticmethod
    def get_interventions(
        db: Session,
        patient_id: int,
    ):
        """
        Recupera as intervenções do paciente.
        """

        intervencoes = db.execute(
            text("""
                SELECT
                    id,
                    paciente_id,
                    data_intervencao,
                    created_at,
                    descricao,
                    profissional_id
                FROM intervencoes
                WHERE paciente_id = :paciente_id
                ORDER BY created_at DESC, id DESC
            """),
            {
                "paciente_id": patient_id,
            },
        ).fetchall()

        eventos = []

        for intervencao in intervencoes:
            eventos.append(
                {
                    "id": intervencao.id,
                    "paciente_id": intervencao.paciente_id,
                    "tipo_evento": "INTERVENCAO",
                    "data": TimelineService._iso_timestamp_utc(
                        intervencao.created_at
                        or intervencao.data_intervencao
                    ),
                    "data_intervencao": (
                        intervencao.data_intervencao.isoformat()
                        if intervencao.data_intervencao
                        else None
                    ),
                    "descricao": intervencao.descricao,
                    "origem": "PROFISSIONAL",
                    "usuario_id": intervencao.profissional_id,
                }
            )

        return eventos
    
    @staticmethod
    def get_assessments(
        db: Session,
        patient_id: int,
    ):
        """
        Recupera as avaliações clínicas do paciente.
        """

        avaliacoes = db.execute(
            text("""
                SELECT
                    ac.id,
                    ac.registro_id,
                    ac.instrumento,
                    ac.score,
                    ac.classificacao,
                    ac.created_at
                FROM avaliacoes_clinicas ac

                JOIN registros_longitudinais rl
                    ON rl.id = ac.registro_id

                WHERE rl.paciente_id = :paciente_id

                ORDER BY ac.created_at DESC
            """),
            {
                "paciente_id": patient_id,
            },
        ).fetchall()

        eventos = []

        for avaliacao in avaliacoes:
            eventos.append(
                {
                    "id": avaliacao.id,
                    "paciente_id": patient_id,
                    "tipo_evento": "AVALIACAO_CLINICA",
                    "data": TimelineService._iso_timestamp_utc(
                        avaliacao.created_at
                    ),
                    "descricao": (
                        f"Aplicação do {avaliacao.instrumento}. "
                        f"Score {avaliacao.score}. "
                        f"Classificação: {avaliacao.classificacao}."
                    ),
                    "origem": "FRAMEWORK",
                    "instrumento": avaliacao.instrumento,
                    "score": avaliacao.score,
                    "classificacao": avaliacao.classificacao,
                }
            )

        return eventos
    
    @staticmethod
    def get_timeline(
        db: Session,
        patient_id: int,
    ):
        """
        Consolida todos os eventos disponíveis da Timeline Clínica.
        """

        timeline = []

        timeline.extend(
            TimelineService.get_daily_records(
                db=db,
                patient_id=patient_id,
            )
        )

        timeline.extend(
            TimelineService.get_interventions(
                db=db,
                patient_id=patient_id,
            )
        )

        timeline.extend(
            TimelineService.get_assessments(
                db=db,
                patient_id=patient_id,
            )
        )

        timeline.extend(
            TimelineService.get_assistential_events(
                db=db,
                patient_id=patient_id,
            )
        )

        timeline.sort(
            key=lambda event: event.get("data") or "",
            reverse=True,
        )

        return timeline