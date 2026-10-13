from datetime import date, datetime, time
from typing import Optional
from pydantic import BaseModel


class ReferenciaMental(BaseModel):
    pessoa_id: int
    pessoa: str
    instituicao_id: int
    instituicao: str
    contexto_assistencial_id: int


class SessaoCockpit(ReferenciaMental):
    sessao_id: int
    data_agendada: date
    hora_inicio: Optional[time]
    hora_fim: Optional[time]
    atividade: str
    duracao_minutos: int
    status: str
    pode_registrar: bool


class MotivoMental(ReferenciaMental):
    codigo: str
    data: datetime
    fonte: str
    referencia_id: int
    dimensoes: list[str] = []


class PessoaAcompanhamento(BaseModel):
    pessoa_id: int
    pessoa: str
    evidencia_mais_recente: datetime
    motivos: list[MotivoMental]


class EventoMental(ReferenciaMental):
    tipo: str
    referencia_id: int
    data: datetime
    precisao: str


class ResumoMental(BaseModel):
    pessoas_em_acompanhamento: int
    atendimentos_hoje: int
    realizados_hoje: int
    proximos_atendimentos: int


class MetadadosCockpit(BaseModel):
    data_referencia: date
    fuso: str
    instituicao_id: Optional[int]
    limit: int
    inicio_janela_evidencias: date
    tem_mais: dict[str, bool]
    limitacoes: list[str]


class CockpitMentalOut(BaseModel):
    resumo: ResumoMental
    agenda_hoje: list[SessaoCockpit]
    proximos_atendimentos: list[SessaoCockpit]
    pessoas_para_acompanhamento: list[PessoaAcompanhamento]
    atividade_recente: list[EventoMental]
    metadados: MetadadosCockpit
