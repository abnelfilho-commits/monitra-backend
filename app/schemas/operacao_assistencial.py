"""Thin contextual transport; W1B commands remain the authority."""
from datetime import date
from typing import Optional
from pydantic import Field, model_validator
from app.schemas.permissao_assistencial import StructuralRecord, Identity, Reason, Capability


class ReasonRequest(StructuralRecord):
    motivo: Reason


class NominationRequest(ReasonRequest):
    usuario_instituicao_acesso_id: Identity
    capacidades: list[Capability] = Field(min_length=1)

    @model_validator(mode='after')
    def distinct(self):
        if len(set(self.capacidades)) != len(self.capacidades):
            raise ValueError('DUPLICATE_CAPABILITY')
        return self


class GrantRequest(ReasonRequest):
    usuario_instituicao_acesso_id: Identity
    capacidade: Capability


class ParticipationRequest(ReasonRequest):
    profissional_instituicao_id: Identity
    data_inicio: date
    data_fim: Optional[date] = None
