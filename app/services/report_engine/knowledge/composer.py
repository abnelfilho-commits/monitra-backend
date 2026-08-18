"""
Knowledge Composer.

Responsável por transformar Knowledge Models
em ReportSections.
"""

from .models import (
    ExecutiveSummaryModel,
    CurrentStatusModel,
    LongitudinalNarrativeModel,
    ClinicalInterpretationModel,
    RecommendationModel,
    JourneyIndicatorsModel,
    PTSExecutionModel,
    AssessmentSummaryModel,
    DiagnosisSummaryModel,
)

from ..models import (
    ReportComponent,
    ReportSection,
)


class KnowledgeComposer:
    """
    Converte modelos de conhecimento em
    seções canônicas do relatório.
    """

    @staticmethod
    def _text_section(
        *,
        code: str,
        title: str,
        order: int,
        content: str,
    ) -> ReportSection:

        section = ReportSection(
            code=code,
            title=title,
            order=order,
        )

        section.add_component(
            ReportComponent(
                type="TEXT",
                data=content,
                order=1,
            )
        )

        return section

    @classmethod
    def compose(cls, model):

        if isinstance(model, ExecutiveSummaryModel):
            return cls._text_section(
                code="EXECUTIVE_SUMMARY",
                title="Resumo Executivo",
                order=2,
                content=model.summary,
            )

        if isinstance(model, CurrentStatusModel):

            section = ReportSection(
                code="CURRENT_STATUS",
                title="Situação Atual",
                order=3,
            )

            section.add_component(
                ReportComponent(
                    type="STATUS_CARD",
                    data={
                        "risk": model.risk,
                        "trend": model.trend,
                        "clinical_moment": model.clinical_moment,
                        "protocol": model.protocol,
                    },
                    order=1,
                )
            )

            section.add_component(
                ReportComponent(
                    type="TEXT",
                    data=model.current_status,
                    order=2,
                )
            )

            return section

        if isinstance(model, DiagnosisSummaryModel):

            if not model.has_active_diagnosis:
                return None

            section = ReportSection(
                code="DIAGNOSIS_SUMMARY",
                title="Diagnóstico Clínico",
                order=4,
            )

            section.add_component(
                ReportComponent(
                    type="DIAGNOSIS_SUMMARY",
                    data={
                        "cid": model.cid,
                        "clinical_description": model.clinical_description,
                        "diagnosis_date": model.diagnosis_date,
                        "physician_name": model.physician_name,
                        "physician_specialty": model.physician_specialty,
                        "physician_registry": model.physician_registry,
                    },
                    order=1,
                )
            )

            return section

        if isinstance(model, LongitudinalNarrativeModel):
            return cls._text_section(
                code="LONGITUDINAL_NARRATIVE",
                title="Narrativa Longitudinal",
                order=5,
                content=model.narrative,
            )
            
        if isinstance(model, JourneyIndicatorsModel):

            section = ReportSection(
                code="JOURNEY_INDICATORS",
                title="Indicadores da Jornada",
                order=6,
            )

            section.add_component(
                ReportComponent(
                    type="JOURNEY_INDICATORS",
                    data={
                        "total_events": model.total_events,
                        "pts_objectives": model.pts_objectives,
                        "planned_sessions": model.planned_sessions,
                        "completed_sessions": model.completed_sessions,
                        "scheduled_sessions": model.scheduled_sessions,
                    },
                    order=1,
                )
            )

            return section

        if isinstance(model, PTSExecutionModel):

            section = ReportSection(
                code="PTS_EXECUTION",
                title="PTS e Execução Assistencial",
                order=7,
            )

            section.add_component(
                ReportComponent(
                    type="PTS_EXECUTION",
                    data={
                        "status": model.status,
                        "total_objectives": model.total_objectives,
                        "total_plannings": model.total_plannings,
                        "total_sessions": model.total_sessions,
                        "completed_sessions": model.completed_sessions,
                        "scheduled_sessions": model.scheduled_sessions,
                        "missed_sessions": model.missed_sessions,
                        "cancelled_sessions": model.cancelled_sessions,
                        "execution_rate": model.execution_rate,
                    },
                    order=1,
                )
            )

            return section
        
        if isinstance(model, AssessmentSummaryModel):

            if model.total_assessments == 0:
                return None

            section = ReportSection(
                code="ASSESSMENT_SUMMARY",
                title="Avaliações Clínicas",
                order=8,
            )

            section.add_component(
                ReportComponent(
                    type="ASSESSMENT_SUMMARY",
                    data={
                        "total_assessments": model.total_assessments,
                        "assessments": model.assessments,
                    },
                    order=1,
                )
            )

            return section

        if isinstance(model, ClinicalInterpretationModel):
            return cls._text_section(
                code="CLINICAL_INTERPRETATION",
                title="Interpretação Clínica",
                order=9,
                content=model.interpretation,
            )

        if isinstance(model, RecommendationModel):
            return cls._text_section(
                code="RECOMMENDATIONS",
                title="Recomendações",
                order=10,
                content=model.recommendation,
            )

        raise ValueError(
            f"Knowledge Model não suportado: {type(model)}"
        )