"""
Knowledge Engine responsável pelo Resumo Executivo.
"""

from ..context import ReportContext
from ..models import ReportSection
from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import ExecutiveSummaryModel
from .narrative_builder import NarrativeBuilder

class ExecutiveSummaryEngine(BaseKnowledgeEngine):
    """
    Produz o Resumo Executivo oficial do relatório.
    """

    code = "EXECUTIVE_SUMMARY_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        patient = (
            context.collected_data
            .get("PATIENT_PROVIDER", {})
        )

        diagnosis = context.collected_data.get(
            "DIAGNOSIS_PROVIDER",
            {},
        )

        pts = context.collected_data.get(
            "PTS_PROVIDER",
            {},
        )

        sessions = context.collected_data.get(
            "SESSION_PROVIDER",
            {},
        )

        timeline = context.collected_data.get(
            "TIMELINE_PROVIDER",
            {},
        )

        reading = context.official_readings.get(
            context.module.upper(),
            {},
        )

        patient_name = (
            patient.get("nome")
            or "Paciente"
        )

        builder = NarrativeBuilder()

        builder.add(
            f"Ao longo da jornada assistencial registrada, {patient_name} "
            "manteve acompanhamento longitudinal contínuo."
        )

        builder.add_if(
            pts.get("pts_ativo") is not None,
            "O Plano Terapêutico Singular permaneceu ativo."
        )

        builder.add_if(
            len(diagnosis.get("ativos", [])) > 0,
            "Há diagnóstico clínico registrado."
        )

        builder.paragraph()

        builder.add_if_value(
            len(timeline) if timeline else None,
            lambda total: (
                f"A jornada clínica registrada contempla "
                f"{total} eventos longitudinais."
            ),
        )

        builder.add_if(
            sessions.get("total_sessoes", 0) > 0,
            (
                f"A jornada contempla "
                f"{sessions.get('total_sessoes')} sessões assistenciais."
            ),
        )
        builder.paragraph()

        builder.add_if_value(
            reading.get("risco_atual"),
            lambda risk: (
                f"A leitura clínica oficial indica {risk.replace('_', ' ').lower()}."
            ),
        )

        builder.add_if_value(
            reading.get("tendencia"),
            lambda trend: (
                "A tendência clínica observada é "
                f"{'estável' if trend.lower() == 'estavel' else trend.lower()}."
            ),
        )

        model = ExecutiveSummaryModel(
            clinical_status="AVAILABLE",
            summary=builder.build(),
        )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )