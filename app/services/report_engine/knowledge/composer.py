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
            return cls._text_section(
                code="CURRENT_STATUS",
                title="Situação Atual",
                order=3,
                content=model.current_status,
            )

        if isinstance(model, LongitudinalNarrativeModel):
            return cls._text_section(
                code="LONGITUDINAL_NARRATIVE",
                title="Narrativa Longitudinal",
                order=4,
                content=model.narrative,
            )

        if isinstance(model, ClinicalInterpretationModel):
            return cls._text_section(
                code="CLINICAL_INTERPRETATION",
                title="Interpretação Clínica",
                order=5,
                content=model.interpretation,
            )

        if isinstance(model, RecommendationModel):
            return cls._text_section(
                code="RECOMMENDATIONS",
                title="Recomendações",
                order=6,
                content=model.recommendation,
            )

        raise ValueError(
            f"Knowledge Model não suportado: {type(model)}"
        )