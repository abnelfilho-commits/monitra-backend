from app.services.legacy_scope import legacy_session
from typing import Optional
from datetime import time

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

from app.core.deps import get_usuario_atual
from app.services.session_service import SessionService
from app.models.sessao_assistencial import SessaoAssistencial

from app.services.sessoes_mentais import SessoesMentaisService
from app.services.pts_mental import PTSDenied, PTSConflict
from app.services.planejamento_mental import PlanningInvalid
from app.schemas.sessoes_mentais import AtendimentoMental
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError


def contextual_operation(db, identity, user, *, action=None, attendance=None):
    """Dispatch only persisted contextual ancestry; legacy path remains unchanged."""
    write = action is not None or attendance is not None
    try:
        service = SessoesMentaisService()
        if not write:
            result = service.operational_detail(db, identity, user.id)
            return AssistentialSessionResponse.model_validate(result) if result is not None else None
        row = service.operational_mutate(db, identity, user.id, action,
            AtendimentoMental.model_validate(attendance) if attendance is not None else None)
        if row is None: return None
        result = (RegistrarAtendimentoResponse(success=True, sessao_id=row.id,
            registro_id=row.registro_longitudinal_id, mensagem='Atendimento registrado com sucesso.')
            if attendance is not None else SessaoAssistencialResponse.model_validate(row))
        db.commit()
        return result
    except PTSDenied:
        if write: db.rollback()
        raise HTTPException(403 if write else 404, 'Sessão indisponível.') from None
    except (PlanningInvalid, ValidationError) as exc:
        if write: db.rollback()
        raise HTTPException(422, 'Dados de atendimento inválidos.' if isinstance(exc, ValidationError) else str(exc)) from None
    except (PTSConflict, SQLAlchemyError):
        if write: db.rollback()
        raise HTTPException(409, 'Conflito na sessão assistencial.') from None
    except Exception:
        if write: db.rollback()
        raise


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
        db.query(SessaoAssistencial).filter(legacy_session())
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

@router.get("/minhas")
def listar_minhas_sessoes(
    usuario=Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    contextual = SessoesMentaisService().personal_sessions(db, usuario)
    from app.models.usuario import Usuario
    native_person = db.query(Usuario.pessoa_id).filter(Usuario.id == usuario.id).scalar()
    legacy_ready = (getattr(usuario, 'perfil', None) == 'PROFISSIONAL' and getattr(usuario, 'profissional_id', None)
                    and getattr(usuario, 'clinica_id', None))
    sessoes = SessionService().personal_sessions(db, usuario) if legacy_ready or native_person is None else []

    return sorted([
        {
            "id": sessao.id,
            "paciente_id": sessao.paciente_id,
            "paciente": (
                sessao.paciente.nome
                if sessao.paciente
                else None
            ),
            "agenda_cuidado_id":
                sessao.agenda_cuidado_id,
            "profissional_id":
                sessao.profissional_id,
            "numero_sessao":
                sessao.numero_sessao,
            "data_agendada":
                sessao.data_agendada,
            "hora_inicio":
                sessao.hora_inicio,
            "hora_fim":
                sessao.hora_fim,
            "duracao_minutos":
                sessao.duracao_minutos,
            "status":
                sessao.status,
            "atividade": (
                sessao.agenda_cuidado.atividade.nome
                if sessao.agenda_cuidado
                and sessao.agenda_cuidado.atividade
                else None
            ),
        }
        for sessao in sessoes
    ] + contextual, key=lambda row: (row["data_agendada"], row["hora_inicio"] or time.min, row["id"]))

@router.post(
    "/{sessao_id}/confirmar",
    response_model=SessaoAssistencialResponse,
)
def confirmar_sessao(
    sessao_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    contextual = contextual_operation(db, sessao_id, usuario, action='confirmar')
    if contextual is not None: return contextual
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.confirmar(
            db=db,
            sessao=sessao,
            usuario=usuario,
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
    usuario=Depends(get_usuario_atual),
):
    contextual = contextual_operation(db, sessao_id, usuario, action='iniciar')
    if contextual is not None: return contextual
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.iniciar(
            db=db,
            sessao=sessao,
            usuario=usuario,
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
    usuario=Depends(get_usuario_atual),
):
    contextual = contextual_operation(db, sessao_id, usuario, action='finalizar')
    if contextual is not None: return contextual
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.finalizar(
            db=db,
            sessao=sessao,
            usuario=usuario,
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
    usuario=Depends(get_usuario_atual),
):
    sessao = buscar_sessao(sessao_id, db)

    try:
        return AssistentialExecutionService.reagendar(
            db=db,
            sessao=sessao,
            usuario=usuario,
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
    usuario=Depends(get_usuario_atual),
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
                usuario=usuario,
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
    usuario=Depends(get_usuario_atual),
):
    contextual = contextual_operation(db, sessao_id, usuario, attendance=payload.model_dump())
    if contextual is not None: return contextual
    sessao = buscar_sessao(
        sessao_id=sessao_id,
        db=db,
    )

    try:
        return AssistentialExecutionService.registrar_atendimento(
            db=db,
            sessao=sessao,
            usuario=usuario,
            payload=payload,
        )

    except ValueError as erro:
        tratar_erro_transicao(erro)

@router.get("/paciente/{paciente_id}")
def listar_sessoes_por_paciente(
    paciente_id: int,
    care_line: str = "NEURO",
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    """
    Lista as Sessões Assistenciais de um paciente,
    ordenadas cronologicamente.
    """

    sessoes = SessionService().patient_sessions(db, paciente_id, usuario, care_line=care_line)

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
    usuario=Depends(get_usuario_atual),
):
    """
    Retorna todos os dados da Sessão Assistencial.
    """

    contextual = contextual_operation(db, sessao_id, usuario)
    if contextual is not None: return contextual
    SessionService().context(db, sessao_id, usuario)
    return AssistentialSessionService.get_session_details(
        db=db,
        sessao_id=sessao_id,
    )