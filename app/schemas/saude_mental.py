"""Contextual journey read models; no onboarding payload."""
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, field_serializer, Field


class InstituicaoDisponivel(BaseModel):
    id: int
    nome: str


class JornadaMental(BaseModel):
    pessoa_id: int
    nome_completo: str
    nome_social: Optional[str]
    paciente_id: int
    instituicao_id: int
    instituicao_nome: str
    paciente_instituicao_id: int
    contexto_assistencial_id: int
    data_inicio: date
    data_fim: Optional[date]
    contexto_estado: Literal['ABERTO', 'ENCERRADO', 'PROGRAMADO']
    modulo_id: int
    linha_estado: Literal['ATIVA', 'INATIVA', 'AUSENTE']


class PessoasMentais(BaseModel):
    itens: list[JornadaMental]
    tem_mais: bool


from app.schemas.checkin_bem_estar import BemEstarJornada


from app.services.clinical_reading.models import ClinicalReading


from app.schemas.diagnostico_mental import DiagnosticosJornada


from app.schemas.intervencao_mental import IntervencoesJornada


from app.schemas.phq9 import PHQ9Jornada


from app.schemas.cbi import CBIJornada
from app.schemas.gad7 import GAD7Jornada


from app.schemas.sessoes_mentais import SessaoMentalOut


class JornadaMentalDetalhe(JornadaMental):
    sessoes: list[SessaoMentalOut] = Field(default_factory=list)
    gad7: GAD7Jornada
    cbi: CBIJornada
    phq9: PHQ9Jornada
    intervencoes: IntervencoesJornada
    diagnosticos: DiagnosticosJornada
    bem_estar: BemEstarJornada
    clinical_reading: Optional[ClinicalReading] = None

    @field_serializer('clinical_reading')
    def serialize_reading(self, reading):
        if reading is None:
            return None
        # The HTTP boundary exposes the canonical code, not the internal registry.
        return {**vars(reading), 'care_line': reading.care_line.code}
