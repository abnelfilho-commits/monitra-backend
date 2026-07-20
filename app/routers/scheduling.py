from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agenda_cuidado import AgendaCuidado

from app.schemas.scheduling import (
    ConfirmarCronogramaRequest,
    ConfirmarCronogramaResponse,
    CronogramaPropostoResponse,
    SessaoPropostaResponse,
)

from app.services.scheduling_engine import SchedulingEngine
from app.services.scheduling_models import PlanejamentoAssistencial
from app.services.scheduling_service import SchedulingService


router = APIRouter(
    prefix="/scheduling",
    tags=["Scheduling Engine"],
)


@router.post(
    "/agenda/{agenda_id}/sugerir",
    response_model=CronogramaPropostoResponse,
)
def sugerir_cronograma(
    agenda_id: int,
    db: Session = Depends(get_db),
):
    agenda = (
        db.query(AgendaCuidado)
        .filter(AgendaCuidado.id == agenda_id)
        .first()
    )

    if not agenda:
        raise HTTPException(
            status_code=404,
            detail="Planejamento Assistencial não encontrado.",
        )

    try:
        planejamento = PlanejamentoAssistencial.from_model(
            agenda
        )

        cronograma = SchedulingEngine.generate_sessions(
            planejamento
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=422,
            detail=str(erro),
        )

    return CronogramaPropostoResponse(
        agenda_id=agenda.id,
        atividade=(
            agenda.atividade.nome
            if agenda.atividade
            else "Atividade não informada"
        ),
        profissional=(
            agenda.profissional.nome
            if agenda.profissional
            else None
        ),
        cronograma=[
            SessaoPropostaResponse(
                numero=sessao.numero,
                data=sessao.data_agendada,
                duracao=sessao.duracao_minutos,
            )
            for sessao in cronograma
        ],
    )

@router.post(
    "/agenda/{agenda_id}/confirmar",
    response_model=ConfirmarCronogramaResponse,
)
def confirmar_cronograma(
    agenda_id: int,
    payload: ConfirmarCronogramaRequest,
    db: Session = Depends(get_db),
):
    agenda = (
        db.query(AgendaCuidado)
        .filter(AgendaCuidado.id == agenda_id)
        .first()
    )

    if not agenda:
        raise HTTPException(
            status_code=404,
            detail="Planejamento Assistencial não encontrado.",
        )

    try:
        sessoes = SchedulingService.confirmar_cronograma(
            db=db,
            agenda=agenda,
            cronograma=payload.cronograma,
        )

    except ValueError as erro:
        mensagem = str(erro)

        if "já foi confirmado" in mensagem:
            raise HTTPException(
                status_code=409,
                detail=mensagem,
            )

        raise HTTPException(
            status_code=422,
            detail=mensagem,
        )

    return ConfirmarCronogramaResponse(
        mensagem=(
            f"{len(sessoes)} sessões assistenciais "
            "criadas com sucesso."
        ),
        total=len(sessoes),
        agenda_id=agenda.id,
    )