"""
Registry dos Knowledge Engines.
"""

from .executive_summary_engine import ExecutiveSummaryEngine
from .current_status_engine import CurrentStatusEngine
from .clinical_interpretation_engine import ClinicalInterpretationEngine
from .recommendation_engine import RecommendationEngine
from .longitudinal_narrative_engine import LongitudinalNarrativeEngine

class KnowledgeRegistry:
    """
    Registro oficial dos Knowledge Engines.
    """

    def __init__(self):
        self._engines = []

    def register(self, engine):
        self._engines.append(engine)

    def all(self):
        return list(self._engines)


knowledge_registry = KnowledgeRegistry()

knowledge_registry.register(
    ExecutiveSummaryEngine
)

knowledge_registry.register(
    CurrentStatusEngine
)

knowledge_registry.register(
    LongitudinalNarrativeEngine
)

knowledge_registry.register(
    ClinicalInterpretationEngine
)

knowledge_registry.register(
    RecommendationEngine
)