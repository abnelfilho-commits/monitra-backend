"""
Definição oficial do relatório CLN-001.
"""

from app.services.report_engine.registry import (
    ReportDefinition,
    report_registry,
)

from app.services.report_engine.providers import (
    PatientProvider,
    TimelineProvider,
    AssessmentProvider,
    DiagnosisProvider,
    PTSProvider,
    SessionProvider,

)


from app.services.report_engine.providers.clinical_engine_provider import NeuroClinicalEngineProvider
from app.services.report_engine.knowledge.registry import (
    ExecutiveSummaryEngine, CurrentStatusEngine, LongitudinalNarrativeEngine,
    JourneyIndicatorsEngine, ClinicalInterpretationEngine, RecommendationEngine,
    PTSExecutionEngine, AssessmentSummaryEngine, DiagnosisSummaryEngine)
from app.services.report_engine.sections.identification import IdentificationSectionBuilder
from app.services.report_engine.sections.temporal_scope import TemporalScopeSection

CLN_001 = ReportDefinition(
    code="CLN-001",
    name="Relatório Longitudinal Inteligente",
    version="1.0",
    domain="CLINICAL",
    slug="clinical-longitudinal-report",
    care_line="NEURO",
    knowledge_engines=[ExecutiveSummaryEngine, CurrentStatusEngine, LongitudinalNarrativeEngine,
        JourneyIndicatorsEngine, ClinicalInterpretationEngine, RecommendationEngine,
        PTSExecutionEngine, AssessmentSummaryEngine, DiagnosisSummaryEngine],
    providers=[
        PatientProvider,
        TimelineProvider,
        AssessmentProvider,
        DiagnosisProvider,
        PTSProvider,
        SessionProvider,
        NeuroClinicalEngineProvider,

    ],
    engines=[],
    sections=[IdentificationSectionBuilder, TemporalScopeSection],
    renderer="PDF",
    required_parameters=[
        "subject_id",
        "period_start",
        "period_end",
        "module",
    ],
)


report_registry.register(
    CLN_001
)
