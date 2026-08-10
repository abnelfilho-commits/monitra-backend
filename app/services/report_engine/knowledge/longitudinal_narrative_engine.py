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
                f"Durante o período analisado foram registrados "
                f"{total} eventos clínicos longitudinais."
            ),
        )

        builder.paragraph()
        
        builder.add_if(
            pts.get("pts_ativo") is not None,
            "O paciente manteve Plano Terapêutico Singular ativo durante o período analisado."
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
        
        builder.add_if_value(
            sessions.get("total_sessoes"),
            lambda total: (
                f"A jornada assistencial contempla "
                f"{total} sessões planejadas."
            ),
        )

        builder.add_if_value(
            sessions.get("realizadas"),
            lambda total: (
                f"Até o momento, {total} sessões foram realizadas."
            ),
        )

        builder.add_if_value(
            sessions.get("agendadas"),
            lambda total: (
                f"Outras {total} permanecem agendadas."
            ),
        )

        builder.paragraph()
        
        builder.add_if_value(
            len(assessments) if assessments else None,
            lambda total: (
                f"Foram realizadas {total} avaliações clínicas durante o acompanhamento."
            ),
        )

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