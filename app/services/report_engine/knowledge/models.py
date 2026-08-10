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
    Estado clínico atual do paciente.
    """

    risk: str

    trend: Optional[str] = None

    clinical_moment: Optional[str] = None

    official_reading: str = ""


@dataclass
class LongitudinalNarrativeModel:
    """
    Narrativa longitudinal institucional.
    """

    narrative: str

    total_events: int


@dataclass
class ClinicalInterpretationModel:
    """
    Interpretação clínica institucional.
    """

    interpretation: str


@dataclass
class RecommendationModel:
    """
    Recomendações clínicas produzidas pelo Framework.
    """

    recommendation: str
    
@dataclass
class CurrentStatusModel:

    clinical_status: str

    current_status: str
    
@dataclass
class LongitudinalNarrativeModel:

    narrative: str
    
@dataclass
class ClinicalInterpretationModel:

    interpretation: str 
    
@dataclass
class RecommendationModel:

    recommendation: str