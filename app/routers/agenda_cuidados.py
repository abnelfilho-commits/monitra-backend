from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db

from app.models.agenda_cuidado import AgendaCuidado
from app.models.pts import PTS, PTSObjetivo

from app.models.atividade_terapeutica import (
    AtividadeTerapeutica,
    OcupacaoProfissional,
)

from app.models.paciente import Paciente
from app.models.profissional import Profissional

from app.schemas.agenda_cuidado import (
    AgendaCuidadoCreate,
    AgendaCuidadoUpdate,
    AgendaCuidadoResponse,
    AgendaFrequenciaUpdate,
)

router = APIRouter(
    prefix="/agenda-cuidados",
    tags=["Agenda de Cuidados"]
)

def montar_response_agenda(item: AgendaCuidado):
    return {
        "id": item.id,
        "pts_id": item.pts_id,
        "objetivo_id": item.objetivo_id,

        "atividade_id": item.atividade_id,
        "ocupacao_id": item.ocupacao_id,

        "atividade_nome":
            item.atividade.nome
            if item.atividade else None,

        "ocupacao_nome":
            item.ocupacao.nome
            if item.ocupacao else None,

        "frequencia_semanal":
            item.frequencia_semanal,

        "duracao_minutos":
            item.duracao_minutos,

        "data_inicio":
            item.data_inicio,

        "data_fim":
            item.data_fim,

        "status":
            item.status,

        "status_execucao":
            item.status_execucao,

        "data_realizacao":
            item.data_realizacao,

        "observacao_execucao":
            item.observacao_execucao,

        "observacoes":
            item.observacoes,

        "profissional_id":
            item.profissional_id,

        "profissional_nome":
            item.profissional.nome
            if item.profissional else None,

        "quantidade_sessoes":
            item.quantidade_sessoes,

        "created_at":
            item.created_at,
    }

@router.get(
    "/objetivo/{objetivo_id}",
    response_model=list[AgendaCuidadoResponse]
)
def listar_agenda_objetivo(
    objetivo_id: int,
    db: Session = Depends(get_db)
):
    agendas = (
        db.query(AgendaCuidado)
        .filter(AgendaCuidado.objetivo_id == objetivo_id)
        .order_by(AgendaCuidado.created_at.desc())
        .all()
    )

    return [montar_response_agenda(item) for item in agendas]

@router.post(
    "/",
    response_model=AgendaCuidadoResponse
)
def criar_agenda_cuidado(
    payload: AgendaCuidadoCreate,
    db: Session = Depends(get_db)
):
    objetivo = (
        db.query(PTSObjetivo)
        .filter(
            PTSObjetivo.id == payload.objetivo_id
        )
        .first()
    )

    if not objetivo:
        raise HTTPException(
            status_code=404,
            detail="Objetivo não encontrado."
        )

    # 1. VALIDAR SE O OBJETIVO PERTENCE AO PTS
    if objetivo.pts_id != payload.pts_id:
        raise HTTPException(
            status_code=400,
            detail="O objetivo informado não pertence ao PTS."
        )

    # 2. BUSCAR O PTS
    pts = (
        db.query(PTS)
        .filter(PTS.id == payload.pts_id)
        .first()
    )

    if not pts:
        raise HTTPException(
            status_code=404,
            detail="PTS não encontrado."
        )

    # 3. BUSCAR O PACIENTE DO PTS
    paciente = (
        db.query(Paciente)
        .filter(Paciente.id == pts.paciente_id)
        .first()
    )

    if not paciente:
        raise HTTPException(
            status_code=404,
            detail="Paciente do PTS não encontrado."
        )

    # 4. VALIDAR O PROFISSIONAL RESPONSÁVEL
    if payload.profissional_id is None:
        raise HTTPException(
            status_code=400,
            detail="Selecione o profissional responsável pelo planejamento."
        )

    profissional = (
        db.query(Profissional)
        .filter(
            Profissional.id == payload.profissional_id,
            Profissional.ativo == True,
        )
        .first()
    )

    if not profissional:
        raise HTTPException(
            status_code=400,
            detail="Profissional responsável inválido ou inativo."
        )

    if profissional.clinica_id != paciente.clinica_id:
        raise HTTPException(
            status_code=400,
            detail="O profissional responsável não pertence à mesma clínica do paciente."
        )

    if profissional.ocupacao_id != payload.ocupacao_id:
        raise HTTPException(
            status_code=400,
            detail="O profissional responsável não possui a ocupação selecionada."
        )

    # 5. SOMENTE DEPOIS DAS VALIDAÇÕES, CRIA A AGENDA
    agenda = AgendaCuidado(
        pts_id=payload.pts_id,
        objetivo_id=payload.objetivo_id,

        atividade_id=payload.atividade_id,
        ocupacao_id=payload.ocupacao_id,

        profissional_id=payload.profissional_id,

        frequencia_semanal=payload.frequencia_semanal,
        quantidade_sessoes=payload.quantidade_sessoes,
        duracao_minutos=payload.duracao_minutos,

        data_inicio=payload.data_inicio,
        data_fim=payload.data_fim,

        observacoes=payload.observacoes,

        status="PLANEJADO",
    )

    db.add(agenda)
    db.commit()
    db.refresh(agenda)

    return montar_response_agenda(agenda)


@router.put(
    "/{agenda_id}",
    response_model=AgendaCuidadoResponse
)
def atualizar_agenda_cuidado(
    agenda_id: int,
    payload: AgendaCuidadoUpdate,
    db: Session = Depends(get_db)
):
    agenda = (
        db.query(AgendaCuidado)
        .filter(
            AgendaCuidado.id == agenda_id
        )
        .first()
    )

    if not agenda:
        raise HTTPException(
            status_code=404,
            detail="Agenda não encontrada."
        )

    dados = payload.model_dump(
        exclude_unset=True
    )

    for campo, valor in dados.items():
        setattr(agenda, campo, valor)

    db.commit()
    db.refresh(agenda)

    return montar_response_agenda(agenda)
    

@router.delete("/{agenda_id}")
def excluir_agenda_cuidado(
    agenda_id: int,
    db: Session = Depends(get_db)
):
    agenda = (
        db.query(AgendaCuidado)
        .filter(
            AgendaCuidado.id == agenda_id
        )
        .first()
    )

    if not agenda:
        raise HTTPException(
            status_code=404,
            detail="Agenda não encontrada."
        )

    db.delete(agenda)
    db.commit()

    return {
        "message":
            "Agenda removida com sucesso."
    }
    
@router.patch(
    "/{agenda_id}/frequencia",
    response_model=AgendaCuidadoResponse
)
def registrar_frequencia(
    agenda_id: int,
    payload: AgendaFrequenciaUpdate,
    db: Session = Depends(get_db)
):
    agenda = (
        db.query(AgendaCuidado)
        .filter(
            AgendaCuidado.id == agenda_id
        )
        .first()
    )

    if not agenda:
        raise HTTPException(
            status_code=404,
            detail="Agenda não encontrada."
        )

    agenda.status_execucao = payload.status_execucao

    agenda.data_realizacao = payload.data_realizacao

    agenda.observacao_execucao = (
        payload.observacao_execucao
    )

    db.commit()
    db.refresh(agenda)

    return montar_response_agenda(agenda)