from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.sessao_assistencial import SessaoAssistencial
from app.schemas.sessao_assistencial import SessaoAssistencialResponse
from app.services.assistential_execution_service import (
    AssistentialExecutionService,
)

from app.services.assistential_session_service import (
    AssistentialSessionService,
)

from app.schemas.assistential_session import (
    AssistentialSessionResponse,
    RegistrarAtendimentoRequest,
    RegistrarAtendimentoResponse,
)

from app.schemas.registros_longitudinais import (
    RegistroLongitudinalCreate,
    RegistroLongitudinalOut,
)

from app.services.registro_longitudinal_service import (
    RegistroLongitudinalService,
)

router = APIRouter(
    prefix="/sessoes-assistenciais",
    tags=["Sessões Assistenciais"],
)


class ReagendarSessaoRequest(BaseModel):
    motivo: Optional[str] = None


def buscar_sessao(
    sessao_id: int,
    db: Session,
) -> SessaoAssistencial:
    sessao = (
        db.query(SessaoAssistencial)
        .filter(SessaoAssistencial.id == sessao_id)
        .first()
    )

    if not sessao:
        raise HTTPException(
            status_code=404,
            detail="Sessão Assistencial não encontrada.",
        )

    return sessao


def tratar_erro_transicao(erro: ValueError) -> None:
    raise HTTPException(
        status_code=422,
        detail=str(erro),
    )


@router.post(
    "/{sessao_id}/confirmar",
    response_model=SessaoAssistencialResponse,
)
def confirmar_sessao(
    sessao_id: int,
    db: Session = Depends(get_db),
):
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.confirmar(
            db=db,
            sessao=sessao,
        )
    except ValueError as erro:
        tratar_erro_transicao(erro)


@router.post(
    "/{sessao_id}/iniciar",
    response_model=SessaoAssistencialResponse,
)
def iniciar_sessao(
    sessao_id: int,
    db: Session = Depends(get_db),
):
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.iniciar(
            db=db,
            sessao=sessao,
        )
    except ValueError as erro:
        tratar_erro_transicao(erro)


@router.post(
    "/{sessao_id}/finalizar",
    response_model=SessaoAssistencialResponse,
)
def finalizar_sessao(
    sessao_id: int,
    db: Session = Depends(get_db),
):
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.finalizar(
            db=db,
            sessao=sessao,
        )
    except ValueError as erro:
        tratar_erro_transicao(erro)


@router.post(
    "/{sessao_id}/reagendar",
    response_model=SessaoAssistencialResponse,
)
def reagendar_sessao(
    sessao_id: int,
    payload: ReagendarSessaoRequest,
    db: Session = Depends(get_db),
):
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.reagendar(
            db=db,
            sessao=sessao,
            motivo=payload.motivo,
        )
    except ValueError as erro:
        tratar_erro_transicao(erro)
        
@router.post(
    "/{sessao_id}/registrar-evolucao",
    response_model=RegistroLongitudinalOut,
)
def registrar_evolucao_sessao(
    sessao_id: int,
    payload: RegistroLongitudinalCreate,
    db: Session = Depends(get_db),
):
    sessao = buscar_sessao(
        sessao_id=sessao_id,
        db=db,
    )

    try:
        registro = (
            RegistroLongitudinalService
            .criar_a_partir_da_sessao(
                db=db,
                sessao=sessao,
                payload=payload,
            )
        )

    except ValueError as erro:
        mensagem = str(erro)

        if "já possui" in mensagem:
            raise HTTPException(
                status_code=409,
                detail=mensagem,
            )

        raise HTTPException(
            status_code=422,
            detail=mensagem,
        )

    return registro

@router.post(
    "/{sessao_id}/registrar-atendimento",
    response_model=RegistrarAtendimentoResponse,
)
def registrar_atendimento(
    sessao_id: int,
    payload: RegistrarAtendimentoRequest,
    db: Session = Depends(get_db),
):
    sessao = buscar_sessao(
        sessao_id=sessao_id,
        db=db,
    )

    try:
        return AssistentialExecutionService.registrar_atendimento(
            db=db,
            sessao=sessao,
            payload=payload,
        )

    except ValueError as erro:
        tratar_erro_transicao(erro)

@router.get("/paciente/{paciente_id}")
def listar_sessoes_por_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
):
    """
    Lista as Sessões Assistenciais de um paciente,
    ordenadas cronologicamente.
    """

    sessoes = (
        db.query(SessaoAssistencial)
        .filter(
            SessaoAssistencial.paciente_id == paciente_id
        )
        .order_by(
            SessaoAssistencial.data_agendada.asc(),
            SessaoAssistencial.hora_inicio.asc(),
            SessaoAssistencial.numero_sessao.asc(),
        )
        .all()
    )

    return [
        {
            "id": sessao.id,
            "paciente_id": sessao.paciente_id,
            "agenda_cuidado_id": sessao.agenda_cuidado_id,
            "profissional_id": sessao.profissional_id,

            "numero_sessao": sessao.numero_sessao,

            "data_agendada": sessao.data_agendada,
            "hora_inicio": sessao.hora_inicio,
            "hora_fim": sessao.hora_fim,
            "duracao_minutos": sessao.duracao_minutos,

            "status": sessao.status,

            "data_realizacao": sessao.data_realizacao,
            "hora_inicio_real": sessao.hora_inicio_real,
            "hora_fim_real": sessao.hora_fim_real,

            "profissional": (
                {
                    "id": sessao.profissional.id,
                    "nome": sessao.profissional.nome,
                }
                if sessao.profissional
                else None
            ),
        }
        for sessao in sessoes
    ]
        
@router.get(
    "/{sessao_id}",
    response_model=AssistentialSessionResponse,
)
def obter_sessao_assistencial(
    sessao_id: int,
    db: Session = Depends(get_db),
):
    """
    Retorna todos os dados da Sessão Assistencial.
    """

    return AssistentialSessionService.get_session_details(
        db=db,
        sessao_id=sessao_id,
    )