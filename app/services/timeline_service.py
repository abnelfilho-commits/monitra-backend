"""
Serviço de domínio responsável pela Timeline Clínica.

Canonical institutional owner plus explicitly retained legacy acquisition profiles.
get_events returns institutional events; get_timeline preserves Report behavior.
"""
from app.services.care_lines import care_line_registry
from app.services.care_lines.exceptions import CareLineNotFound
from app.services.timeline.models import TimelineScope, TimelineReadMode, CareLineAssociation, event_order_key
from app.services.timeline.sources import SOURCES
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
        Report compatibility profile: preserve historical selection/counts.

        These legacy dictionaries are not institutional TimelineEvent instances.
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

    @staticmethod
    def get_events(db, query, registry=None, sources=None):
        """Institutional read for an already-authorized patient context.

        Historical association is not filtered by current active patient links.
        BOUNDED limits the globally ordered result, not independent source pages.
        """
        registry = registry or care_line_registry
        selected = None
        if query.scope == TimelineScope.CARE_LINE:
            selected = registry.get(query.requested_care_line)
            if selected is None:
                raise CareLineNotFound('Unknown requested care line.')
        events = []
        for collect in (SOURCES if sources is None else sources):
            for event in collect(db, query.patient_id, registry):
                if event.patient_id != query.patient_id:
                    raise ValueError('Timeline source returned another patient.')
                if selected is not None and not (
                    event.care_line_association in (CareLineAssociation.EXPLICIT, CareLineAssociation.DERIVED)
                    and event.care_line is not None
                    and event.care_line.module_id == selected.module_id
                ):
                    continue
                events.append(event)
        identities = [(event.source_type, event.source_id) for event in events]
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate institutional source identity.')
        events.sort(key=event_order_key)
        return events[:query.limit] if query.mode == TimelineReadMode.BOUNDED else events


    @staticmethod
    def get_neuro_legacy_timeline(db, paciente_id):
        """Legacy acquisition profile: preserve Neuro shape, counts and dates."""
        registros = db.execute(
            text("""
                SELECT
                    rl.id,
                    rl.paciente_id,
                    rl.data_registro,
                    rl.criado_em,
                    rl.origem,

                    MAX(CASE WHEN cf.nome_campo = 'sono_qualidade'
                        THEN rr.valor_numero END) AS sono_qualidade,

                    MAX(CASE WHEN cf.nome_campo = 'irritabilidade'
                        THEN rr.valor_numero END) AS irritabilidade,

                    MAX(CASE WHEN cf.nome_campo = 'crise_sensorial'
                        THEN rr.valor_numero END) AS crise_sensorial,

                    MAX(CASE WHEN cf.nome_campo = 'tempo_tela'
                        THEN rr.valor_texto END) AS tempo_tela,

                    MAX(CASE WHEN cf.nome_campo = 'seletividade_alimentar'
                        THEN rr.valor_texto END) AS seletividade_alimentar,

                    COALESCE(
                        BOOL_OR(
                            CASE
                                WHEN cf.nome_campo = 'aceitou_alimento_novo'
                                THEN rr.valor_booleano
                            END
                        ),
                        false
                    ) AS aceitou_alimento_novo,

                    MAX(CASE WHEN cf.nome_campo = 'observacao'
                        THEN rr.valor_texto END) AS observacao

                FROM registros_longitudinais rl
                LEFT JOIN respostas_registro rr
                    ON rr.registro_id = rl.id
                LEFT JOIN campos_formulario cf
                    ON cf.id = rr.campo_id

                WHERE rl.paciente_id = :paciente_id
                  AND rl.modulo_id = 1

                GROUP BY
                    rl.id,
                    rl.paciente_id,
                    rl.data_registro,
                    rl.criado_em,
                    rl.origem

                ORDER BY rl.data_registro DESC, rl.id DESC
            """),
            {"paciente_id": paciente_id}
        ).fetchall()

        timeline = []

        for r in registros:
            timeline.append({
                "id": r.id,
                "paciente_id": r.paciente_id,
                "tipo_evento": "REGISTRO_DIARIO",
                "data": TimelineService._iso_timestamp_utc(
                    r.criado_em or r.data_registro
                ),
                "descricao": r.observacao,
                "origem": r.origem or "PROFISSIONAL",
                "sono_qualidade": str(int(r.sono_qualidade)) if r.sono_qualidade is not None else None,
                "irritabilidade": str(int(r.irritabilidade)) if r.irritabilidade is not None else None,
                "crise_sensorial": bool(r.crise_sensorial) if r.crise_sensorial is not None else None,
                "tempo_tela": r.tempo_tela,
                "seletividade_alimentar": r.seletividade_alimentar,
                "aceitou_alimento_novo": r.aceitou_alimento_novo,
            })

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
            {"paciente_id": paciente_id}
        ).fetchall()

        for i in intervencoes:
            timeline.append({
                "id": i.id,
                "paciente_id": i.paciente_id,
                "tipo_evento": "INTERVENCAO",
                "data": TimelineService._iso_timestamp_utc(
                    i.created_at if i.created_at else i.data_intervencao
                ),
                "data_intervencao": (
                    i.data_intervencao.isoformat()
                    if i.data_intervencao
                    else None
                ),
                "descricao": i.descricao,
                "origem": "PROFISSIONAL",
                "usuario_id": i.profissional_id,
                "sono_qualidade": None,
                "irritabilidade": None,
                "crise_sensorial": None,
            })

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
            {"paciente_id": paciente_id}
        ).fetchall()

        for a in avaliacoes:
            timeline.append({
                "id": a.id,
                "paciente_id": paciente_id,
                "tipo_evento": "AVALIACAO_CLINICA",
                "data": TimelineService._iso_timestamp_utc(a.created_at),
                "descricao": (
                    f"Aplicação do {a.instrumento}. "
                    f"Score {a.score}. "
                    f"Classificação: {a.classificacao}."
                ),
                "origem": "FRAMEWORK",
                "instrumento": a.instrumento,
                "score": a.score,
                "classificacao": a.classificacao,
            })

        eventos_sessoes = (
            TimelineEventService.obter_eventos_paciente(
                db=db,
                paciente_id=paciente_id,
            )
        )

        timeline.extend(eventos_sessoes)

        timeline = sorted(
            timeline,
            key=lambda x: x["data"],
            reverse=True
        )

        return timeline
