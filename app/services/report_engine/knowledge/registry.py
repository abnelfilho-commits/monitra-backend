"""
Registry dos Knowledge Engines.
"""

from .executive_summary_engine import ExecutiveSummaryEngine


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