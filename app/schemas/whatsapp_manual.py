from typing import Literal
from pydantic import BaseModel, ConfigDict

class ManualRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    motivo: Literal['ACOMPANHAMENTO_EXTRAORDINARIO', 'SOLICITACAO_DA_PESSOA']
