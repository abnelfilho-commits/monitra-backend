"""
Knowledge Engine responsável pela Narrativa Longitudinal.
"""

from ..context import ReportContext

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import LongitudinalNarrativeModel
from .narrative_builder import NarrativeBuilder


class LongitudinalNarrativeEngine(BaseKnowledgeEngine):
    """
    Produz a narrativa cronológica da jornada assistencial.
    """

    code = "LONGITUDINAL_NARRATIVE_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        builder = NarrativeBuilder()
        
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
        
        assessments = context.collected_data.get(
            "ASSESSMENT_PROVIDER",
            [],
        )    
        
        builder.add_if_value(
            len(timeline) if timeline else None,
            lambda total: (
                f"A jornada assistencial registrada contempla "
                f"{total} eventos clínicos longitudinais."
            ),
        )

        builder.paragraph()
        
        builder.add_if(
            pts.get("pts_ativo") is not None,
            "O paciente possui Plano Terapêutico Singular ativo."
        )

        builder.add_if_value(
            len(
                pts.get("pts_ativo", {}).get("objetivos", [])
            )
            if pts.get("pts_ativo")
            else None,
            lambda total: (
                f"Foram definidos {total} objetivos terapêuticos."
            ),
        )

        builder.paragraph()
        
        if sessions.get("total_sessoes", 0) > 0:

            builder.add(
                f"A jornada assistencial contempla "
                f"{sessions.get('total_sessoes')} sessões planejadas."
            )

            builder.add(
                f"Até o momento, "
                f"{sessions.get('realizadas', 0)} sessões foram realizadas."
            )

            builder.add(
                f"Outras "
                f"{sessions.get('agendadas', 0)} permanecem agendadas."
            )

        builder.paragraph()
        
        lambda total: (
            f"A jornada registrada contempla "
            f"{total} avaliações clínicas."
        ),

        builder.paragraph()
        
        model = LongitudinalNarrativeModel(
            narrative=builder.build(),
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )