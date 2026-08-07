"""
Serviço de domínio responsável pelo Plano Terapêutico Singular (PTS).

Centraliza a leitura do PTS, objetivos e planejamentos assistenciais
para reutilização pelo Report Engine e futuros consumidores.
"""

from typing import Any, Dict, List

from sqlalchemy.orm import Session, joinedload

from app.models.agenda_cuidado import AgendaCuidado
from app.models.pts import PTS, PTSObjetivo


class PTSService:
    """Serviço institucional do Plano Terapêutico Singular."""

    @staticmethod
    def get_patient_pts(
        db: Session,
        patient_id: int,
    ) -> List[PTS]:
        """
        Recupera o histórico de PTS do paciente.
        """

        return (
            db.query(PTS)
            .options(
                joinedload(PTS.objetivos),
            )
            .filter(
                PTS.paciente_id == patient_id,
            )
            .order_by(
                PTS.data_inicio.desc(),
                PTS.id.desc(),
            )
            .all()
        )

    @staticmethod
    def get_care_plans(
        db: Session,
        pts_id: int,
    ) -> List[AgendaCuidado]:
        """
        Recupera os planejamentos assistenciais vinculados ao PTS.
        """

        return (
            db.query(AgendaCuidado)
            .options(
                joinedload(AgendaCuidado.atividade),
                joinedload(AgendaCuidado.ocupacao),
                joinedload(AgendaCuidado.profissional),
            )
            .filter(
                AgendaCuidado.pts_id == pts_id,
            )
            .order_by(
                AgendaCuidado.data_inicio.asc(),
                AgendaCuidado.id.asc(),
            )
            .all()
        )

    @staticmethod
    def serialize_objective(
        objective: PTSObjetivo,
    ) -> Dict[str, Any]:
        return {
            "id": objective.id,
            "pts_id": objective.pts_id,
            "descricao": objective.descricao,
            "prioridade": objective.prioridade,
            "status": objective.status,
            "created_at": (
                objective.created_at.isoformat()
                if objective.created_at
                else None
            ),
            "updated_at": (
                objective.updated_at.isoformat()
                if objective.updated_at
                else None
            ),
        }

    @staticmethod
    def serialize_care_plan(
        plan: AgendaCuidado,
    ) -> Dict[str, Any]:
        return {
            "id": plan.id,
            "pts_id": plan.pts_id,
            "objetivo_id": plan.objetivo_id,
            "atividade_id": plan.atividade_id,
            "atividade_nome": (
                plan.atividade.nome
                if plan.atividade
                else None
            ),
            "ocupacao_id": plan.ocupacao_id,
            "ocupacao_nome": (
                plan.ocupacao.nome
                if plan.ocupacao
                else None
            ),
            "profissional_id": plan.profissional_id,
            "profissional_nome": (
                plan.profissional.nome
                if plan.profissional
                else None
            ),
            "frequencia_semanal": plan.frequencia_semanal,
            "quantidade_sessoes": plan.quantidade_sessoes,
            "duracao_minutos": plan.duracao_minutos,
            "data_inicio": (
                plan.data_inicio.isoformat()
                if plan.data_inicio
                else None
            ),
            "data_fim": (
                plan.data_fim.isoformat()
                if plan.data_fim
                else None
            ),
            "status": plan.status,
            "observacoes": plan.observacoes,
        }

    @classmethod
    def serialize_pts(
        cls,
        db: Session,
        pts: PTS,
    ) -> Dict[str, Any]:
        plans = cls.get_care_plans(
            db=db,
            pts_id=pts.id,
        )

        return {
            "id": pts.id,
            "paciente_id": pts.paciente_id,
            "modulo_id": pts.modulo_id,
            "data_inicio": pts.data_inicio.isoformat(),
            "data_fim": (
                pts.data_fim.isoformat()
                if pts.data_fim
                else None
            ),
            "status": pts.status,
            "objetivo_geral": pts.objetivo_geral,
            "observacoes": pts.observacoes,
            "objetivos": [
                cls.serialize_objective(objetivo)
                for objetivo in pts.objetivos
            ],
            "planejamentos": [
                cls.serialize_care_plan(plan)
                for plan in plans
            ],
        }

    @classmethod
    def build_report_context(
        cls,
        db: Session,
        patient_id: int,
    ) -> Dict[str, Any]:
        """
        Monta o contexto completo do PTS para o
        Framework Institucional de Conhecimento.
        """

        patient_pts = cls.get_patient_pts(
            db=db,
            patient_id=patient_id,
        )

        pts_list = [
            cls.serialize_pts(
                db=db,
                pts=pts,
            )
            for pts in patient_pts
        ]

        active_pts = next(
            (
                item
                for item in pts_list
                if item["status"] == "ATIVO"
            ),
            None,
        )

        return {
            "pts_ativo": active_pts,
            "historico": pts_list,
            "total_pts": len(pts_list),
        }