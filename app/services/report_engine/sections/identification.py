"""
Section de identificação do relatório.
"""

from typing import Any, Dict

from ..constants import SECTION_IDENTIFICATION
from ..context import ReportContext
from ..models import ReportComponent, ReportSection
from .base_section import BaseSectionBuilder


class IdentificationSectionBuilder(BaseSectionBuilder):
    """
    Constrói a seção de identificação do relatório.
    """

    code = SECTION_IDENTIFICATION
    title = "Identificação"
    order = 1
    required = True

    def build(self, context: ReportContext) -> ReportSection:
        subject = self._resolve_subject(context)

        section = ReportSection(
            code=self.code,
            title=self.title,
            order=self.order,
            required=self.required,
        )

        section.add_component(
            ReportComponent(
                type="SUBJECT",
                data=subject,
                order=1,
            )
        )

        return section

    @staticmethod
    def _resolve_subject(context: ReportContext) -> Dict[str, Any]:
        """
        Resolve o objeto principal do relatório.
        """
        if isinstance(context.subject, dict):
            return context.subject

        patient_data = context.collected_data.get("PATIENT_PROVIDER")

        if isinstance(patient_data, dict):
            return patient_data

        return {
            "id": context.subject_id,
            "name": f"Paciente {context.subject_id}",
        }