"""
Resultado produzido por um Knowledge Engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..models import ReportSection


@dataclass
class KnowledgeResult:
    """
    Representa o resultado produzido por um
    Knowledge Engine.
    """

    engine_code: str
    engine_version: str
    status: str = "SUCCESS"
    
    knowledge: list[Any] = field(default_factory=list)

    sections: list[ReportSection] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)

    executed_at: datetime = field(default_factory=datetime.utcnow)