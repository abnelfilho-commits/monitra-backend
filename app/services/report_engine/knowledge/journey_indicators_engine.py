"""
Knowledge Engine responsável pelos Indicadores da Jornada.
"""

from ..context import ReportContext

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import JourneyIndicatorsModel


class JourneyIndicatorsEngine(BaseKnowledgeEngine):
    """
    Produz indicadores quantitativos consolidados
    da jornada assistencial.
    """

    code = "JOURNEY_INDICATORS_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        timeline = context.collected_data.get(
            "TIMELINE_PROVIDER",
            [],
        )

        pts = context.collected_data.get(
            "PTS_PROVIDER",
            {},
        )

        sessions = context.collected_data.get(
            "SESSION_PROVIDER",
            {},
        )

        pts_active = pts.get("pts_ativo") or {}

        model = JourneyIndicatorsModel(
            total_events=len(timeline),

            pts_objectives=len(
                pts_active.get(
                    "objetivos",
                    [],
                )
            ),

            planned_sessions=sessions.get(
                "total_sessoes",
                0,
            ),

            completed_sessions=sessions.get(
                "realizadas",
                0,
            ),

            scheduled_sessions=sessions.get(
                "agendadas",
                0,
            ),
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )