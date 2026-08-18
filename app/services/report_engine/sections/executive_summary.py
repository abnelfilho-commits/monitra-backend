"""
Section de resumo executivo do relatório.
"""

from ..constants import SECTION_EXECUTIVE_SUMMARY
from ..context import ReportContext
from ..models import ReportComponent, ReportSection
from .base_section import BaseSectionBuilder


class ExecutiveSummarySectionBuilder(BaseSectionBuilder):
    """
    Constrói a seção de resumo executivo.
    """

    code = SECTION_EXECUTIVE_SUMMARY
    title = "Resumo Executivo"
    order = 2
    required = True

    def build(self, context: ReportContext) -> ReportSection:
        section = ReportSection(
            code=self.code,
            title=self.title,
            order=self.order,
            required=self.required,
        )

        summary = self._resolve_summary(context)

        section.add_component(
            ReportComponent(
                type="TEXT",
                data=summary,
                order=1,
            )
        )

        return section

    @staticmethod
    def _resolve_summary(context: ReportContext) -> str:
        """
        Resolve o resumo executivo disponível no contexto.
        """
        if context.narratives:
            return str(context.narratives[0])

        return (
            "Ainda não há informações suficientes para gerar "
            "o resumo executivo do período analisado."
        )