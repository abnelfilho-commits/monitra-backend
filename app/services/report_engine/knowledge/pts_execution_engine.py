"""
Knowledge Engine responsável pela síntese
do PTS e sua execução assistencial.
"""

from ..context import ReportContext

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import PTSExecutionModel


class PTSExecutionEngine(BaseKnowledgeEngine):
    """
    Produz a visão executiva do Plano Terapêutico
    Singular e de sua execução assistencial.
    """

    code = "PTS_EXECUTION_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        pts_context = context.collected_data.get(
            "PTS_PROVIDER",
            {},
        )

        sessions = context.collected_data.get(
            "SESSION_PROVIDER",
            {},
        )

        active_pts = (
            pts_context.get("pts_ativo")
            or {}
        )

        objectives = (
            active_pts.get("objetivos")
            or []
        )

        plannings = (
            active_pts.get("planejamentos")
            or []
        )

        total_sessions = (
            sessions.get("total_sessoes")
            or 0
        )

        completed_sessions = (
            sessions.get("realizadas")
            or 0
        )

        execution_rate = (
            (completed_sessions / total_sessions) * 100
            if total_sessions > 0
            else None
        )

        model = PTSExecutionModel(
            status=active_pts.get(
                "status",
                "SEM_PTS_ATIVO",
            ),

            total_objectives=len(objectives),
            total_plannings=len(plannings),

            total_sessions=total_sessions,

            completed_sessions=completed_sessions,

            scheduled_sessions=(
                sessions.get("agendadas")
                or 0
            ),

            missed_sessions=(
                sessions.get("faltas")
                or 0
            ),

            cancelled_sessions=(
                sessions.get("canceladas")
                or 0
            ),

            execution_rate=(
                round(execution_rate, 1)
                if execution_rate is not None
                else None
            ),
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )