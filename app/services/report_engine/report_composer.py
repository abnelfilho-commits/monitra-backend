"""
Compositor do Modelo Canônico do Report Engine.
"""

from typing import Any, Dict, Iterable, Optional

from .context import ReportContext
from .models import CanonicalReport
from .sections.base_section import BaseSectionBuilder


class ReportComposer:
    """
    Transforma o ReportContext em um CanonicalReport.

    O Composer não conhece regras clínicas nem estruturas
    específicas de um relatório. Ele apenas executa os
    Section Builders declarados na ReportDefinition.
    """

    def compose(self, context: ReportContext) -> CanonicalReport:
        """
        Monta o relatório canônico a partir do contexto.
        """
        definition = context.definition

        if definition is None:
            raise ValueError(
                "A definição do relatório é obrigatória para composição."
            )

        subject = self._resolve_subject(context)

        report = CanonicalReport(
            report_code=definition.code,
            report_name=definition.name,
            report_version=definition.version,
            subject=subject,
            period_start=context.period_start.isoformat(),
            period_end=context.period_end.isoformat(),
            warnings=list(context.warnings),
            audit=dict(context.audit),
            metadata={
                "execution_id": context.execution_id,
                "module": context.module,
                "output_format": context.output_format,
            },
        )

        for builder_class in self._resolve_section_builders(context):
            builder = builder_class()

            if not builder.supports(context):
                if builder.required:
                    raise ValueError(
                        f"Section obrigatória não suportada: {builder.code}"
                    )
                continue

            section = builder.build(context)

            if section is None:
                if builder.required:
                    raise ValueError(
                        f"Section obrigatória não foi construída: {builder.code}"
                    )
                continue

            report.add_section(section)

        return report

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

    @staticmethod
    def _resolve_section_builders(
        context: ReportContext,
    ) -> Iterable[type[BaseSectionBuilder]]:
        """
        Retorna os Section Builders declarados na definição.
        """
        definition = context.definition

        if definition is None:
            return []

        return definition.sections