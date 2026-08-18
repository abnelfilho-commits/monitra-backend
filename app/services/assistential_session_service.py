from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.agenda_cuidado import AgendaCuidado
from app.models.atividade_terapeutica import AtividadeTerapeutica
from app.models.avaliacao_clinica import AvaliacaoClinica
from app.models.intervencao import Intervencao
from app.models.modular import RegistroLongitudinal
from app.models.paciente import Paciente
from app.models.profissional import Profissional
from app.models.pts import PTS, PTSObjetivo
from app.models.sessao_assistencial import SessaoAssistencial


class AssistentialSessionService:
    """
    Consolida todas as informações relacionadas a uma
    Sessão Assistencial em uma visão 360°.

    Este serviço é somente de leitura. Ele não altera
    a sessão, o PTS, os registros ou as intervenções.
    """

    @staticmethod
    def montar_resumo_sessao(
        sessao: SessaoAssistencial,
        paciente: Paciente,
        atividade: Optional[AtividadeTerapeutica],
        registro: Optional[RegistroLongitudinal],
        avaliacoes: List[AvaliacaoClinica],
        intervencoes: List[Intervencao],
        proxima_sessao: Optional[SessaoAssistencial],
        sessoes_realizadas: int,
        total_sessoes: int,
    ) -> Dict[str, Any]:
        """
        Monta um resumo determinístico da sessão.

        Não utiliza IA. O texto é produzido a partir
        das informações já registradas no sistema.
        """

        percentual_conclusao = 0.0

        if total_sessoes > 0:
            percentual_conclusao = round(
                (sessoes_realizadas / total_sessoes) * 100,
                1,
            )

        # Proteção para massas antigas ou dados inconsistentes.
        percentual_conclusao = min(
            max(percentual_conclusao, 0.0),
            100.0,
        )

        numero_sessao = sessao.numero_sessao
        atividade_nome = (
            atividade.nome
            if atividade
            else "atividade assistencial"
        )

        if sessao.status == "REALIZADA":
            titulo = f"Sessão nº {numero_sessao} concluída"
            descricao = (
                f"{paciente.nome} participou da Sessão nº "
                f"{numero_sessao} de {atividade_nome}."
            )
        else:
            titulo = f"Sessão nº {numero_sessao}"
            descricao = (
                f"Sessão nº {numero_sessao} de "
                f"{atividade_nome} para {paciente.nome}."
            )

        return {
            "titulo": titulo,
            "descricao": descricao,
            "registro_realizado": registro is not None,
            "avaliacoes_realizadas": len(avaliacoes),
            # Nesta versão, são intervenções recentes do paciente,
            # não necessariamente vinculadas diretamente à sessão.
            "intervencoes": len(intervencoes),
            "proxima_sessao": (
                proxima_sessao.data_agendada
                if proxima_sessao
                else None
            ),
            "sessoes_realizadas": sessoes_realizadas,
            "total_sessoes": total_sessoes,
            "percentual_conclusao": percentual_conclusao,
        }

    @staticmethod
    def get_session_details(
        db: Session,
        sessao_id: int,
    ) -> Dict[str, Any]:
        """
        Retorna a visão completa da Sessão Assistencial:

        Sessão
            ↓
        Agenda de Cuidados
            ↓
        PTS
            ↓
        Objetivo Terapêutico
            ↓
        Atividade
            ↓
        Paciente
            ↓
        Profissional e Ocupação
            ↓
        Registro Longitudinal
            ↓
        Avaliações
            ↓
        Contexto de Intervenções
            ↓
        Próxima Sessão
            ↓
        Resumo e progresso
        """

        # ---------------------------------------------------------
        # Sessão Assistencial
        # ---------------------------------------------------------

        sessao = (
            db.query(SessaoAssistencial)
            .filter(
                SessaoAssistencial.id == sessao_id
            )
            .first()
        )

        if not sessao:
            raise HTTPException(
                status_code=404,
                detail="Sessão Assistencial não encontrada.",
            )

        # ---------------------------------------------------------
        # Agenda de Cuidados
        # ---------------------------------------------------------

        agenda = (
            db.query(AgendaCuidado)
            .filter(
                AgendaCuidado.id
                == sessao.agenda_cuidado_id
            )
            .first()
        )

        if not agenda:
            raise HTTPException(
                status_code=404,
                detail="Agenda de cuidados não encontrada.",
            )

        # ---------------------------------------------------------
        # PTS
        # ---------------------------------------------------------

        pts = (
            db.query(PTS)
            .filter(
                PTS.id == agenda.pts_id
            )
            .first()
        )

        if not pts:
            raise HTTPException(
                status_code=404,
                detail="PTS não encontrado.",
            )

        # ---------------------------------------------------------
        # Objetivo Terapêutico
        # ---------------------------------------------------------

        objetivo = (
            db.query(PTSObjetivo)
            .filter(
                PTSObjetivo.id == agenda.objetivo_id
            )
            .first()
        )

        # ---------------------------------------------------------
        # Atividade Terapêutica
        # ---------------------------------------------------------

        atividade = (
            db.query(AtividadeTerapeutica)
            .filter(
                AtividadeTerapeutica.id
                == agenda.atividade_id
            )
            .first()
        )

        # ---------------------------------------------------------
        # Paciente
        # ---------------------------------------------------------

        paciente = (
            db.query(Paciente)
            .filter(
                Paciente.id == pts.paciente_id
            )
            .first()
        )

        if not paciente:
            raise HTTPException(
                status_code=404,
                detail="Paciente da sessão não encontrado.",
            )

        # ---------------------------------------------------------
        # Profissional
        #
        # Prioridade:
        # 1. profissional informado na sessão;
        # 2. profissional definido no planejamento.
        # ---------------------------------------------------------

        profissional = None

        profissional_id = (
            sessao.profissional_id
            or agenda.profissional_id
        )

        if profissional_id:
            profissional = (
                db.query(Profissional)
                .filter(
                    Profissional.id == profissional_id
                )
                .first()
            )

        # ---------------------------------------------------------
        # Ocupação Profissional
        #
        # Consulta direta para não depender da existência
        # de relationship SQLAlchemy em AgendaCuidado.
        # ---------------------------------------------------------

        ocupacao_nome = None

        if agenda.ocupacao_id:
            ocupacao_nome = db.execute(
                text(
                    """
                    SELECT nome
                    FROM ocupacoes_profissionais
                    WHERE id = :ocupacao_id
                    """
                ),
                {
                    "ocupacao_id": agenda.ocupacao_id,
                },
            ).scalar_one_or_none()

        # ---------------------------------------------------------
        # Registro Longitudinal
        # ---------------------------------------------------------

        registro = None

        if sessao.registro_longitudinal_id:
            registro = (
                db.query(RegistroLongitudinal)
                .filter(
                    RegistroLongitudinal.id
                    == sessao.registro_longitudinal_id
                )
                .first()
            )

        # ---------------------------------------------------------
        # Avaliações originadas do Registro Longitudinal
        # ---------------------------------------------------------

        avaliacoes: List[AvaliacaoClinica] = []

        if registro:
            avaliacoes = (
                db.query(AvaliacaoClinica)
                .filter(
                    AvaliacaoClinica.registro_id
                    == registro.id
                )
                .order_by(
                    AvaliacaoClinica.created_at.asc()
                )
                .all()
            )

        # ---------------------------------------------------------
        # Contexto de intervenções recentes
        #
        # Ainda são intervenções do paciente, não intervenções
        # diretamente vinculadas à sessão.
        # ---------------------------------------------------------

        intervencoes = (
            db.query(Intervencao)
            .filter(
                Intervencao.paciente_id == paciente.id
            )
            .order_by(
                Intervencao.data_intervencao.desc()
            )
            .limit(5)
            .all()
        )

        # ---------------------------------------------------------
        # Próxima sessão futura
        # ---------------------------------------------------------

        data_referencia = (
            sessao.data_realizacao
            or sessao.data_agendada
        )

        proxima_sessao = (
            db.query(SessaoAssistencial)
            .filter(
                SessaoAssistencial.agenda_cuidado_id
                == agenda.id,
                SessaoAssistencial.id != sessao.id,
                SessaoAssistencial.status == "AGENDADA",
                SessaoAssistencial.data_agendada
                > data_referencia,
            )
            .order_by(
                SessaoAssistencial.data_agendada.asc(),
                SessaoAssistencial.numero_sessao.asc(),
            )
            .first()
        )

        # ---------------------------------------------------------
        # Progresso do planejamento assistencial
        # ---------------------------------------------------------

        total_sessoes = (
            db.query(SessaoAssistencial)
            .filter(
                SessaoAssistencial.agenda_cuidado_id
                == agenda.id
            )
            .count()
        )

        sessoes_realizadas = (
            db.query(SessaoAssistencial)
            .filter(
                SessaoAssistencial.agenda_cuidado_id
                == agenda.id,
                SessaoAssistencial.status == "REALIZADA",
            )
            .count()
        )

        # ---------------------------------------------------------
        # Duração real
        # ---------------------------------------------------------

        duracao_segundos = None
        duracao_minutos = None

        if (
            sessao.data_realizacao
            and sessao.hora_inicio_real
            and sessao.hora_fim_real
        ):
            inicio = datetime.combine(
                sessao.data_realizacao,
                sessao.hora_inicio_real,
            )

            fim = datetime.combine(
                sessao.data_realizacao,
                sessao.hora_fim_real,
            )

            total_segundos = max(
                0,
                int((fim - inicio).total_seconds()),
            )

            duracao_segundos = total_segundos

            duracao_minutos = (
                round(total_segundos / 60)
                if total_segundos >= 60
                else 0
            )

        # ---------------------------------------------------------
        # Resumo automático
        # ---------------------------------------------------------

        resumo = (
            AssistentialSessionService
            .montar_resumo_sessao(
                sessao=sessao,
                paciente=paciente,
                atividade=atividade,
                registro=registro,
                avaliacoes=avaliacoes,
                intervencoes=intervencoes,
                proxima_sessao=proxima_sessao,
                sessoes_realizadas=sessoes_realizadas,
                total_sessoes=total_sessoes,
            )
        )

        # ---------------------------------------------------------
        # Resposta consolidada
        # ---------------------------------------------------------

        return {
            "sessao": {
                "id": sessao.id,
                "numero": sessao.numero_sessao,
                "status": sessao.status,
                "data": (
                    sessao.data_realizacao
                    or sessao.data_agendada
                ),
                "hora_inicio": (
                    sessao.hora_inicio_real
                    or sessao.hora_inicio
                ),
                "hora_fim": (
                    sessao.hora_fim_real
                    or sessao.hora_fim
                ),
                "duracao_minutos": duracao_minutos,
                "duracao_segundos": duracao_segundos,
            },

            "paciente": {
                "id": paciente.id,
                "nome": paciente.nome,
            },

            "objetivo": (
                {
                    "id": objetivo.id,
                    "descricao": objetivo.descricao,
                    "status": objetivo.status,
                    "prioridade": objetivo.prioridade,
                }
                if objetivo
                else None
            ),

            "atividade": (
                {
                    "id": atividade.id,
                    "nome": atividade.nome,
                }
                if atividade
                else None
            ),

            "profissional": (
                {
                    "id": (
                        profissional.id
                        if profissional
                        else None
                    ),
                    "nome": (
                        profissional.nome
                        if profissional
                        else None
                    ),
                    "ocupacao": ocupacao_nome,
                }
                if profissional or ocupacao_nome
                else None
            ),

            "registro_longitudinal": (
                {
                    "id": registro.id,
                    "data": registro.data_registro,
                    "origem": registro.origem,
                }
                if registro
                else None
            ),

            "avaliacoes": [
                {
                    "id": avaliacao.id,
                    "instrumento": avaliacao.instrumento,
                    "score": (
                        float(avaliacao.score)
                        if avaliacao.score is not None
                        else None
                    ),
                    "classificacao": (
                        avaliacao.classificacao
                    ),
                }
                for avaliacao in avaliacoes
            ],

            "intervencoes": [
                {
                    "id": intervencao.id,
                    "descricao": intervencao.descricao,
                    "data": intervencao.data_intervencao,
                }
                for intervencao in intervencoes
            ],

            "proxima_sessao": (
                {
                    "id": proxima_sessao.id,
                    "numero": (
                        proxima_sessao.numero_sessao
                    ),
                    "data": (
                        proxima_sessao.data_agendada
                    ),
                    "status": proxima_sessao.status,
                }
                if proxima_sessao
                else None
            ),

            "resumo": resumo,
        }
        
    @staticmethod
    def _serialize_session(
        session: SessaoAssistencial,
    ) -> Dict[str, Any]:
        """
        Serializa uma Sessão Assistencial para consumo
        pelo Framework Institucional de Conhecimento.
        """

        return {
            "id": session.id,
            "agenda_cuidado_id": session.agenda_cuidado_id,
            "paciente_id": session.paciente_id,
            "profissional_id": session.profissional_id,
            "numero_sessao": session.numero_sessao,
            "data_agendada": (
                session.data_agendada.isoformat()
                if session.data_agendada
                else None
            ),
            "hora_inicio": (
                session.hora_inicio.isoformat()
                if session.hora_inicio
                else None
            ),
            "hora_fim": (
                session.hora_fim.isoformat()
                if session.hora_fim
                else None
            ),
            "duracao_minutos": session.duracao_minutos,
            "status": session.status,
            "data_realizacao": (
                session.data_realizacao.isoformat()
                if session.data_realizacao
                else None
            ),
            "hora_inicio_real": (
                session.hora_inicio_real.isoformat()
                if session.hora_inicio_real
                else None
            ),
            "hora_fim_real": (
                session.hora_fim_real.isoformat()
                if session.hora_fim_real
                else None
            ),
            "observacoes": session.observacoes,
            "motivo_falta": session.motivo_falta,
            "motivo_cancelamento": session.motivo_cancelamento,
            "motivo_reagendamento": session.motivo_reagendamento,
            "registro_longitudinal_id": (
                session.registro_longitudinal_id
            ),
            "created_at": (
                session.created_at.isoformat()
                if session.created_at
                else None
            ),
        }

    @classmethod
    def build_report_context(
        cls,
        db: Session,
        patient_id: int,
    ) -> Dict[str, Any]:
        """
        Monta o contexto assistencial das sessões do paciente.
        """

        sessions = (
            db.query(SessaoAssistencial)
            .filter(
                SessaoAssistencial.paciente_id == patient_id,
            )
            .order_by(
                SessaoAssistencial.data_agendada.desc(),
                SessaoAssistencial.numero_sessao.desc(),
            )
            .all()
        )

        history = [
            cls._serialize_session(session)
            for session in sessions
        ]

        completed = [
            session
            for session in history
            if session["status"] == "REALIZADA"
        ]

        scheduled = [
            session
            for session in history
            if session["status"] == "AGENDADA"
        ]

        cancelled = [
            session
            for session in history
            if session["status"] == "CANCELADA"
        ]

        missed = [
            session
            for session in history
            if session["status"] == "FALTA"
        ]

        last_session = completed[0] if completed else None

        next_session = next(
            (
                session
                for session in reversed(history)
                if session["status"] == "AGENDADA"
            ),
            None,
        )

        return {
            "total_sessoes": len(history),
            "realizadas": len(completed),
            "agendadas": len(scheduled),
            "canceladas": len(cancelled),
            "faltas": len(missed),
            "ultima_sessao": last_session,
            "proxima_sessao": next_session,
            "historico": history,
        }