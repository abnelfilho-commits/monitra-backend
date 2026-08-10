"""
Report Engine.
Framework responsável pela geração dos relatórios inteligentes
do Integra Care.
"""

from .report_service import ReportService
from .reports import CLN_001

__all__ = [
    "ReportService",
    "CLN_001",
]