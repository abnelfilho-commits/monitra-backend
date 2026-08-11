"""
Knowledge Engine responsável pela Situação Atual.
"""

from ..context import ReportContext
from ..models import ReportSection

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import CurrentStatusModel
from .narrative_builder import NarrativeBuilder


class CurrentStatusEngine(BaseKnowledgeEngine):
    """
    Produz a Situação Atual oficial do relatório.
    """

    code = "CURRENT_STATUS_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        reading = context.official_readings.get(
            (context.module or "").upper(),
            {},
        )
        
        builder = NarrativeBuilder()
        
        builder.add_if_value(
            reading.get("risco_atual"),
            lambda risk: (
                f"A leitura clínica oficial indica "
                f"{risk.replace('_', ' ').lower()}."
            ),
        )
        builder.add_if_value(
            reading.get("tendencia"),
            lambda trend: (
                "A tendência clínica atual é "
                f"{'estável' if trend.lower() == 'estavel' else trend.lower()}."
            ),
        )

        clinical_moment = reading.get(
            "momento_clinico",
            {},
        )

        model = CurrentStatusModel(
            clinical_status=clinical_moment.get(
                "status",
                "SEM_DADOS",
            ),
            current_status=builder.build(),

            risk=reading.get(
                "risco_atual",
            ),

            trend=reading.get(
                "tendencia",
            ),

            clinical_moment=clinical_moment.get(
                "status",
            ),

            protocol=reading.get(
                "protocolo",
            ),
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )