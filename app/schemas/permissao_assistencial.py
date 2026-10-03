"""Structural records, not HTTP commands or authorization decisions."""
from datetime import date, datetime
from typing import Annotated, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identity = Annotated[int, Field(strict=True, gt=0)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Capability = Literal['ASSISTENCIAL_LER', 'ASSISTENCIAL_REGISTRAR', 'CONTEXTO_ADMINISTRAR']
Scope = Literal['INSTITUICAO', 'CONTEXTO']


class StructuralRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)


class ContextoProfissionalRecord(StructuralRecord):
    id: Identity
    instituicao_id: Identity
    contexto_assistencial_id: Identity
    profissional_instituicao_id: Identity
    data_inicio: date
    data_fim: Optional[date] = None
    criado_por_usuario_id: Identity
    criado_em: datetime
    motivo_criacao: Reason
    encerrado_por_usuario_id: Optional[Identity] = None
    encerrado_em: Optional[datetime] = None
    motivo_encerramento: Optional[Reason] = None
    invalidado_por_usuario_id: Optional[Identity] = None
    invalidado_em: Optional[datetime] = None
    motivo_invalidacao: Optional[Reason] = None

    @model_validator(mode='after')
    def structural_consistency(self):
        if self.data_fim is not None and self.data_fim < self.data_inicio:
            raise ValueError('INVALID_PERIOD')
        for prefix in ('encerrado', 'invalidado'):
            reason = 'motivo_encerramento' if prefix == 'encerrado' else 'motivo_invalidacao'
            values = (getattr(self, prefix+'_por_usuario_id'), getattr(self, prefix+'_em'), getattr(self, reason))
            if any(v is not None for v in values) and not all(v is not None for v in values):
                raise ValueError('INCOMPLETE_EVENT')
        if self.encerrado_em is not None and self.data_fim is None:
            raise ValueError('END_REQUIRED')
        return self


class PermissionRecord(StructuralRecord):
    id: Identity
    usuario_instituicao_acesso_id: Identity
    instituicao_id: Identity
    contexto_assistencial_id: Optional[Identity] = None
    concedido_por_usuario_id: Identity
    concedido_em: datetime
    motivo_concessao: Reason
    revogado_por_usuario_id: Optional[Identity] = None
    revogado_em: Optional[datetime] = None
    motivo_revogacao: Optional[Reason] = None
    revogacao_origem: Optional[Annotated[Reason, Field(max_length=32)]] = None

    @model_validator(mode='after')
    def revocation_consistency(self):
        values = (self.revogado_por_usuario_id, self.revogado_em, self.motivo_revogacao, self.revogacao_origem)
        if any(v is not None for v in values) and not all(v is not None for v in values):
            raise ValueError('INCOMPLETE_REVOCATION')
        return self

    def validate_scope(self, scope):
        if (scope == 'CONTEXTO') != (self.contexto_assistencial_id is not None):
            raise ValueError('INVALID_SCOPE')


class ConcessaoAssistencialRecord(PermissionRecord):
    capacidade: Capability
    escopo_tipo: Scope
    autoridade_delegacao_id: Optional[Identity] = None

    @model_validator(mode='after')
    def scope_consistency(self):
        self.validate_scope(self.escopo_tipo)
        if self.capacidade != 'CONTEXTO_ADMINISTRAR' and self.escopo_tipo != 'CONTEXTO':
            raise ValueError('CLINICAL_CONTEXT_REQUIRED')
        return self


class AutoridadeDelegacaoRecord(PermissionRecord):
    capacidade_delegavel: Capability
    envelope_tipo: Scope
    origem: Literal['BOOTSTRAP', 'RECOVERY']
    operacao_id: UUID

    @model_validator(mode='after')
    def scope_consistency(self):
        self.validate_scope(self.envelope_tipo)
        return self
