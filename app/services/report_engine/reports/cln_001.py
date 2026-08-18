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
    ClinicalEngineProvider,
)


CLN_001 = ReportDefinition(
    code="CLN-001",
    name="Relatório Longitudinal Inteligente",
    version="1.0",
    domain="CLINICAL",
    slug="clinical-longitudinal-report",
    providers=[
        PatientProvider,
        TimelineProvider,
        AssessmentProvider,
        DiagnosisProvider,
        PTSProvider,
        SessionProvider,
        ClinicalEngineProvider,
    ],
    engines=[],
    sections=[],
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