"""
Serviço principal de execução do Report Engine.
"""
from sqlalchemy.orm import Session
from .report_composer import ReportComposer
from datetime import date
from typing import Any, Dict, Optional

from .context import ReportContext
from .registry import (
    ReportDefinition,
    ReportRegistry,
    report_registry,
)

from .knowledge import knowledge_registry
from .knowledge.composer import KnowledgeComposer

class ReportService:
    """
    Ponto de entrada do Report Engine.

    Resolve a definição do relatório, cria o contexto de execução
    e coordena os Engines declarados no Report Registry.
    """

    def __init__(
        self,
        registry: Optional[ReportRegistry] = None,
        composer: Optional[ReportComposer] = None,
    ) -> None:
        self.registry = registry or report_registry
        self.composer = composer or ReportComposer()

    def get_definition(self, report_code: str) -> ReportDefinition:
        """
        Localiza a definição oficial do relatório.
        """
        return self.registry.get(report_code)

    def create_context(
        self,
        *,
        report_code: str,
        subject_id: int,
        requested_by: int,
        period_start: date,
        period_end: date,
        module: Optional[str] = None,
        output_format: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
    ) -> ReportContext:
        """
        Cria o contexto inicial de uma execução.
        """
        definition = self.get_definition(report_code)

        context = ReportContext(
            report_code=definition.code,
            subject_id=subject_id,
            requested_by=requested_by,
            period_start=period_start,
            period_end=period_end,
            module=module,
            output_format=output_format or definition.renderer or "PDF",
            parameters=parameters or {},
            definition=definition,
            db=db,
        )

        self._validate_context(context)

        return context

    def execute(self, context: ReportContext) -> ReportContext:
        """
        Executa os Engines registrados para o relatório.

        Nesta primeira versão, o resultado permanece armazenado
        no próprio ReportContext.
        """
        definition = context.definition

        if definition is None:
            definition = self.get_definition(context.report_code)
            context.definition = definition

        self._validate_context(context)

        for provider_class in definition.providers:
            provider = provider_class()

            if not provider.supports(context):
                if provider.required:
                    raise ValueError(
                        f"Provider obrigatório não aplicável: {provider.code}"
                    )

                context.add_warning(
                    f"Provider não aplicável ao contexto: {provider.code}"
                )
                continue

            result = provider.collect(context)

            context.add_collected_data(
                result.provider_code,
                result.data,
            )

            for warning in result.warnings:
                context.add_warning(warning)

            context.audit.setdefault("providers", []).append(
                {
                    "code": result.provider_code,
                    "version": result.provider_version,
                    "status": result.status,
                    "collected_at": result.collected_at.isoformat(),
                }
            )

        for engine_class in definition.engines:
            engine = engine_class()

            if not engine.supports(context):
                context.add_warning(
                    f"Engine não aplicável ao contexto: {engine.code}"
                )
                continue

            result = engine.execute(context)

            context.indicators.extend(result.indicators)
            context.evidences.extend(result.evidences)
            context.narratives.extend(result.narratives)
            context.recommendations.extend(result.recommendations)

            for warning in result.warnings:
                context.add_warning(warning)

            context.audit.setdefault("engines", []).append(
                {
                    "code": result.engine_code,
                    "version": result.engine_version,
                    "status": result.status,
                    "executed_at": result.executed_at.isoformat(),
                }
            )

        for engine_class in knowledge_registry.all():

            engine = engine_class()

            result = engine.execute(context)

            for model in result.knowledge:
                section = KnowledgeComposer.compose(model)

                context.add_section(section)

            context.audit.setdefault(
                "knowledge_engines",
                [],
            ).append(
                {
                    "code": result.engine_code,
                    "version": result.engine_version,
                    "status": result.status,
                    "executed_at": result.executed_at.isoformat(),
                }
            )
        
        context.canonical_report = self.composer.compose(context)
        
        return context

    def generate(
        self,
        *,
        report_code: str,
        subject_id: int,
        requested_by: int,
        period_start: date,
        period_end: date,
        module: Optional[str] = None,
        output_format: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
    ) -> ReportContext:
        """
        Cria e executa o contexto de geração.

        Ainda não compõe ou renderiza o documento.
        """
        context = self.create_context(
            report_code=report_code,
            subject_id=subject_id,
            requested_by=requested_by,
            period_start=period_start,
            period_end=period_end,
            module=module,
            output_format=output_format,
            parameters=parameters,
            db=db,
        )

        return self.execute(context)

    @staticmethod
    def _validate_context(context: ReportContext) -> None:
        """
        Valida os dados mínimos da execução.
        """
        if not context.report_code:
            raise ValueError("report_code é obrigatório.")

        if not context.subject_id:
            raise ValueError("subject_id é obrigatório.")

        if not context.requested_by:
            raise ValueError("requested_by é obrigatório.")

        if context.period_start > context.period_end:
            raise ValueError(
                "period_start não pode ser posterior a period_end."
            )

        definition = context.definition

        if definition is None:
            raise ValueError(
                "A definição do relatório não foi carregada."
            )

        available_parameters = {
            "subject_id": context.subject_id,
            "requested_by": context.requested_by,
            "period_start": context.period_start,
            "period_end": context.period_end,
            "module": context.module,
            "output_format": context.output_format,
            **context.parameters,
        }

        missing_parameters = [
            parameter
            for parameter in definition.required_parameters
            if available_parameters.get(parameter) in (None, "")
        ]

        if missing_parameters:
            missing = ", ".join(missing_parameters)
            raise ValueError(
                f"Parâmetros obrigatórios ausentes: {missing}"
            )