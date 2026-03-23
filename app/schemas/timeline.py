from datetime import datetime
from typing import Literal
from pydantic import BaseModel

TipoEvento = Literal["INTERVENCAO", "REGISTRO_DIARIO"]

class TimelineItemOut(BaseModel):
    id: int
    tipo_evento: TipoEvento
    data: datetime
    descricao: str
    usuario_id: int
