from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel

class SessaoResumo(BaseModel):
    id: int
    numero: int
    status: str
    data: date
    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None
    duracao_minutos: Optional[int] = None
    duracao_segundos: Optional[int] = None

class ResumoSessao(BaseModel):
    titulo: str
    descricao: str
    registro_realizado: bool
    avaliacoes_realizadas: int
    intervencoes: int
    proxima_sessao: Optional[date] = None
    sessoes_realizadas: int
    total_sessoes: int
    percentual_conclusao: float
    
class PacienteResumo(BaseModel):
    id: int
    nome: str

class ObjetivoResumo(BaseModel):
    id: int
    descricao: str
    status: Optional[str] = None
    prioridade: Optional[str] = None


class AtividadeResumo(BaseModel):
    id: int
    nome: str


class ProfissionalResumo(BaseModel):
    id: Optional[int] = None
    nome: Optional[str] = None
    ocupacao: Optional[str] = None


class RegistroResumo(BaseModel):
    id: int
    data: date
    origem: str


class AvaliacaoResumo(BaseModel):
    id: int
    instrumento: str
    score: Optional[float] = None
    classificacao: Optional[str] = None


class IntervencaoResumo(BaseModel):
    id: int
    descricao: str
    data: datetime

class ProximaSessaoResumo(BaseModel):
    id: int
    numero: int
    data: date
    status: str


class AssistentialSessionResponse(BaseModel):
    sessao: SessaoResumo
    paciente: PacienteResumo
    objetivo: Optional[ObjetivoResumo] = None
    atividade: Optional[AtividadeResumo] = None
    profissional: Optional[ProfissionalResumo] = None
    registro_longitudinal: Optional[RegistroResumo] = None
    avaliacoes: List[AvaliacaoResumo] = []
    intervencoes: List[IntervencaoResumo] = []
    proxima_sessao: Optional[ProximaSessaoResumo] = None
    resumo: ResumoSessao
    
class RegistrarAtendimentoRequest(BaseModel):
    """
    Caso de uso da Jornada Assistencial.

    O frontend informa apenas os dados produzidos
    durante o atendimento.

    O backend é responsável por transformar essas
    informações em um Registro Longitudinal.
    """

    narrativa: str
    proximos_passos: List[str] = []
    
class RegistrarAtendimentoResponse(BaseModel):
    success: bool
    sessao_id: int
    registro_id: int
    mensagem: str