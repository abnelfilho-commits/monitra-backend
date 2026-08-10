"""
Knowledge Engine responsável pelas Recomendações Assistenciais.
"""

from ..context import ReportContext

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import RecommendationModel
from .narrative_builder import NarrativeBuilder


class RecommendationEngine(BaseKnowledgeEngine):
    """
    Produz recomendações assistenciais a partir das
    evidências e leituras disponíveis no relatório.
    """

    code = "RECOMMENDATION_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        builder = NarrativeBuilder()

        reading = context.official_readings.get(
            (context.module or "").upper(),
            {},
        )

        pts = context.collected_data.get(
            "PTS_PROVIDER",
            {},
        )

        #
        # REC-001
        # Manutenção do acompanhamento
        #

        if (
            reading.get("risco_atual") == "baixo_risco"
            and reading.get("tendencia", "").lower() == "estavel"
        ):
            builder.add(
                "Recomenda-se a manutenção do acompanhamento "
                "conforme a estratégia assistencial vigente."
            )

            builder.paragraph()

        #
        # REC-002
        # Reavaliação da estratégia assistencial
        #

        if (
            reading.get("risco_atual") == "alto_risco"
            or reading.get("tendencia", "").lower() == "piora"
        ):
            builder.add(
                "Recomenda-se a reavaliação da estratégia assistencial "
                "pela equipe responsável, considerando as evidências "
                "clínicas identificadas."
            )

            builder.paragraph()

        #
        # REC-003
        # Continuidade do PTS
        #

        if pts.get("pts_ativo") is not None:
            builder.add(
                "Recomenda-se a continuidade do acompanhamento dos "
                "objetivos e atividades previstos no Plano Terapêutico Singular."
            )

            builder.paragraph()
            
        #
        # REC-004
        # Evidência insuficiente
        #

        if not reading or reading.get("risco_atual") == "sem_dados":
            builder.add(
                "Recomenda-se a continuidade da coleta longitudinal "
                "para ampliar a base de evidências clínicas disponíveis."
            )

            builder.paragraph()

        model = RecommendationModel(
            recommendation=builder.build(),
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )