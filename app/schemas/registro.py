from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class IntervencaoCreate(BaseModel):
    paciente_id: int
    profissional_id: int
    tipo: str
    descricao: Optional[str] = None
    data_intervencao: datetime


class RegistroDiarioCreate(BaseModel):
    paciente_id: int
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None

    # Campo legado ainda usado pelo router antigo app/routers/registros.py
    # Manter por enquanto para evitar erro AttributeError em registro.alimentacao.
    alimentacao: Optional[str] = None

    # Campos adicionados na Sprint 2.7.
    # No modelo longitudinal, eles são persistidos em respostas_registro.
    # Aqui ficam apenas para compatibilidade temporária com o schema legado.
    tempo_tela: Optional[str] = None
    seletividade_alimentar: Optional[str] = None
    aceitou_alimento_novo: Optional[bool] = None

    observacao: Optional[str] = None


class RegistroDiarioOut(BaseModel):
    id: int
    paciente_id: int
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None

    # Campo legado.
    alimentacao: Optional[str] = None

    # Compatibilidade temporária com a Sprint 2.7.
    tempo_tela: Optional[str] = None
    seletividade_alimentar: Optional[str] = None
    aceitou_alimento_novo: Optional[bool] = None

    observacao: Optional[str] = None

    class Config:
        from_attributes = True


class RegistroDiarioResponsavelCreate(BaseModel):
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None

    # Campo legado.
    alimentacao: Optional[str] = None

    # Campos adicionados na Sprint 2.7.
    tempo_tela: Optional[str] = None
    seletividade_alimentar: Optional[str] = None
    aceitou_alimento_novo: Optional[bool] = None

    observacao: Optional[str] = None


class RegistroDiarioResponsavelOut(BaseModel):
    id: int
    paciente_id: int
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None

    # Campo legado.
    alimentacao: Optional[str] = None

    # Compatibilidade temporária com a Sprint 2.7.
    tempo_tela: Optional[str] = None
    seletividade_alimentar: Optional[str] = None
    aceitou_alimento_novo: Optional[bool] = None

    observacao: Optional[str] = None
    origem: Optional[str] = None
    responsavel_id: Optional[int] = None
    criado_por_tipo: Optional[str] = None
    criado_por_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
