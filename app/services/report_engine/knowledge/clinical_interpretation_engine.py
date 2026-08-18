"""
Knowledge Engine responsável pela Interpretação Clínica.
"""

from ..context import ReportContext

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import ClinicalInterpretationModel
from .narrative_builder import NarrativeBuilder


class ClinicalInterpretationEngine(BaseKnowledgeEngine):
    """
    Produz a interpretação clínica baseada nas evidências
    disponíveis no contexto do relatório.
    """

    code = "CLINICAL_INTERPRETATION_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        builder = NarrativeBuilder()
        
        pts = context.collected_data.get(
            "PTS_PROVIDER",
            {},
        )

        timeline = context.collected_data.get(
            "TIMELINE_PROVIDER",
            [],
        )

        sessions = context.collected_data.get(
            "SESSION_PROVIDER",
            {},
        )

        if (
            pts.get("pts_ativo") is not None
            and len(timeline) > 0
            and sessions.get("total_sessoes", 0) > 0
        ):
            builder.add(
                "O paciente apresenta continuidade assistencial documentada ao longo de sua jornada de cuidado."
            )

            builder.paragraph()

        assessments = context.collected_data.get(
            "ASSESSMENT_PROVIDER",
            [],
        )
        
        if (
            len(assessments) > 0
            and len(timeline) > 0
        ):
            builder.add(
                "As evidências clínicas registradas fornecem base consistente para acompanhamento evolutivo."
            )

            builder.paragraph()
            
        reading = context.official_readings.get(
            (context.module or "").upper(),
            {},
        )
        
        #
        # CI-003
        # Momento Clínico Estável
        #

        if (
            reading.get("risco_atual") == "baixo_risco"
            and reading.get("tendencia", "").lower() == "estavel"
        ):
            builder.add(
                "As evidências disponíveis são compatíveis com manutenção da estratégia assistencial atualmente adotada."
            )

            builder.paragraph()

        #
        # CI-004
        # Necessidade de Intensificação
        #

        if (
            reading.get("risco_atual") == "alto_risco"
            or reading.get("tendencia", "").lower() == "piora"
        ):
            builder.add(
                "As evidências sugerem necessidade de reavaliação clínica e intensificação do acompanhamento."
            )

            builder.paragraph()
            
        model = ClinicalInterpretationModel(
            interpretation=builder.build(),
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )