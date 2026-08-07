"""
Section da Leitura Atual do Paciente.
"""

from typing import Optional

from ..constants import SECTION_CURRENT_STATUS
from ..context import ReportContext
from ..models import ReportComponent, ReportSection
from .base_section import BaseSectionBuilder


class CurrentStatusSectionBuilder(BaseSectionBuilder):
    """
    Apresenta as Leituras Oficiais produzidas pelos
    Engines Especializados.

    Esta Section não cria nem altera inteligência clínica.
    """

    code = SECTION_CURRENT_STATUS
    title = "Leitura Atual do Paciente"
    order = 3
    required = False

    def supports(self, context: ReportContext) -> bool:
        return bool(context.official_readings)

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

        section.add_component(
            ReportComponent(
                type="OFFICIAL_READING",
                data=dict(context.official_readings),
                order=1,
            )
        )

        return section