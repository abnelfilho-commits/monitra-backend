"""
Modelos institucionais produzidos pelos Knowledge Engines.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutiveSummaryModel:
    """
    Representa o conhecimento do Resumo Executivo.
    """

    clinical_status: str
    risk_level: Optional[str] = None
    trend: Optional[str] = None
    adherence: Optional[str] = None
    summary: str = ""


@dataclass
class CurrentStatusModel:
    """
    Representa a situação clínica atual do paciente.

    Mantém tanto os dados estruturados da leitura oficial
    quanto sua representação narrativa.
    """

    clinical_status: str
    current_status: str

    risk: Optional[str] = None
    trend: Optional[str] = None
    clinical_moment: Optional[str] = None
    protocol: Optional[str] = None


@dataclass
class LongitudinalNarrativeModel:
    """
    Representa a narrativa longitudinal institucional.
    """

    narrative: str


@dataclass
class ClinicalInterpretationModel:
    """
    Representa a interpretação clínica institucional.
    """

    interpretation: str


@dataclass
class RecommendationModel:
    """
    Representa as recomendações clínicas produzidas
    pelo Framework.
    """

    recommendation: str
    
@dataclass
class JourneyIndicatorsModel:
    """
    Indicadores quantitativos da jornada assistencial.
    """

    total_events: int = 0
    pts_objectives: int = 0
    planned_sessions: int = 0
    completed_sessions: int = 0
    scheduled_sessions: int = 0
    
@dataclass
class PTSExecutionModel:
    """
    Representa a síntese executiva do
    Plano Terapêutico Singular e sua execução assistencial.
    """

    status: str

    total_objectives: int = 0
    total_plannings: int = 0

    total_sessions: int = 0
    completed_sessions: int = 0
    scheduled_sessions: int = 0
    missed_sessions: int = 0
    cancelled_sessions: int = 0

    execution_rate: float = 0.0