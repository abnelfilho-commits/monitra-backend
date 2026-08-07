"""
Knowledge Composer.

Responsável por transformar Knowledge Models
em ReportSections.
"""

from .models import (
    ExecutiveSummaryModel,
)

from ..models import ReportSection


class KnowledgeComposer:
    """
    Converte modelos de conhecimento em
    seções canônicas do relatório.
    """

    @staticmethod
    def compose(model):

        if isinstance(
            model,
            ExecutiveSummaryModel,
        ):
            return ReportSection(
                code="EXECUTIVE_SUMMARY",
                title="Resumo Executivo",
                order=2,
                visible=True,
                type="TEXT",
                content=model.summary,
            )

        raise ValueError(
            f"Knowledge Model não suportado: {type(model)}"
        )