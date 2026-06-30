from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AssessmentContext:
    registro_id: int
    instrumento: str
    respostas: dict

    paciente_id: Optional[int] = None
    modulo_id: Optional[int] = None
    profissional_id: Optional[int] = None
    formulario_id: Optional[int] = None
    data_registro: Optional[str] = None

    metadata: dict = field(default_factory=dict)