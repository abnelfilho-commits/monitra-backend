"""
Section da Narrativa Longitudinal.
"""

from typing import Optional

from ..constants import SECTION_LONGITUDINAL_NARRATIVE
from ..context import ReportContext
from ..models import ReportComponent, ReportSection
from .base_section import BaseSectionBuilder


class LongitudinalNarrativeSectionBuilder(BaseSectionBuilder):
    """
    Apresenta a narrativa longitudinal produzida pelo Report Engine.

    Esta Section descreve a evolução durante o período analisado
    e não substitui a Leitura Atual dos Engines Especializados.
    """

    code = SECTION_LONGITUDINAL_NARRATIVE
    title = "Narrativa Longitudinal"
    order = 4
    required = False

    def supports(self, context: ReportContext) -> bool:
        return bool(context.narratives)

    def build(
        self,
        context: ReportContext,
    ) -> Optional[ReportSection]:
        if not self.supports(context):
            return None

        section = ReportSection(
            code=self.code,
            title=self.title,
            order=self.order,
            required=self.required,
        )

        for index, narrative in enumerate(
            context.narratives,
            start=1,
        ):
            section.add_component(
                ReportComponent(
                    type="TEXT",
                    data=str(narrative),
                    order=index,
                )
            )

        return section