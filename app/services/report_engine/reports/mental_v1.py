from ..registry import ReportDefinition, report_registry
from ..providers.mental_health_provider import MentalHealthProvider, resolve_scope
from ..sections.mental_health import MENTAL_SECTIONS

MENTAL_V1 = ReportDefinition(
    code='CLN-MENTAL-001', name='Relatório Longitudinal Assistencial de Saúde Mental',
    version='1.0', domain='CLINICAL', care_line='MENTAL_HEALTH', renderer='PDF',
    required_parameters=['subject_id', 'module', 'period_start', 'period_end', 'contexto_assistencial_id'],
    scope_resolver=resolve_scope, providers=[MentalHealthProvider], sections=MENTAL_SECTIONS)
report_registry.register(MENTAL_V1)
