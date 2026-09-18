from ..registry import ReportDefinition, report_registry
from ..providers.patient_provider import PatientProvider
from ..providers.diagnosis_provider import DiagnosisProvider
from ..providers.timeline_provider import CardioTimelineProvider
from ..providers.cardio_evolution_provider import CardioEvolutionProvider
from ..providers.clinical_engine_provider import ClinicalEngineProvider
from ..sections.identification import IdentificationSectionBuilder
from ..sections.temporal_scope import TemporalScopeSection
from ..sections.cardio import (CardioSummary, CardioStatus, CardioDiagnoses, CardioRecords,
    CardioInterventions, CardioEvolution, CardioInterpretation, CardioNarrative, CardioConsiderations)

CARDIO_V1=ReportDefinition(code='CLN-CARDIO-001',name='Relatório Longitudinal Cardiometabólico',
    version='1.0',domain='CLINICAL',care_line='CARDIO',
    providers=[PatientProvider,DiagnosisProvider,CardioTimelineProvider,CardioEvolutionProvider,ClinicalEngineProvider],
    sections=[IdentificationSectionBuilder,TemporalScopeSection,CardioSummary,CardioStatus,CardioDiagnoses,
        CardioRecords,CardioInterventions,CardioEvolution,CardioInterpretation,CardioNarrative,CardioConsiderations],
    required_parameters=['subject_id','module','period_start','period_end'],renderer='PDF')
report_registry.register(CARDIO_V1)
