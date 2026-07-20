from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.diagnostico import (
    DiagnosticoCreate,
    DiagnosticoResponse,
    DiagnosticoUpdate,
)
from app.services.diagnostico_service import DiagnosticoService


router = APIRouter(
    prefix="/diagnosticos",
    tags=["Diagnósticos"],
)


@router.post(
    "",
    response_model=DiagnosticoResponse,
    status_code=201,
)
def criar_diagnostico(
    payload: DiagnosticoCreate,
    db: Session = Depends(get_db),
):
    """
    Cria um diagnóstico, hipótese diagnóstica ou revisão
    vinculada a um paciente.

    O diagnóstico é opcional dentro da Jornada Assistencial.
    """

    return DiagnosticoService.criar(
        db=db,
        payload=payload,
    )


@router.get(
    "/{diagnostico_id}",
    response_model=DiagnosticoResponse,
)
def buscar_diagnostico(
    diagnostico_id: int,
    db: Session = Depends(get_db),
):
    """
    Retorna um diagnóstico específico.
    """

    return DiagnosticoService.buscar_por_id(
        db=db,
        diagnostico_id=diagnostico_id,
    )


@router.put(
    "/{diagnostico_id}",
    response_model=DiagnosticoResponse,
)
def atualizar_diagnostico(
    diagnostico_id: int,
    payload: DiagnosticoUpdate,
    db: Session = Depends(get_db),
):
    """
    Atualiza parcialmente os dados clínicos
    e profissionais do diagnóstico.
    """

    return DiagnosticoService.atualizar(
        db=db,
        diagnostico_id=diagnostico_id,
        payload=payload,
    )


@router.patch(
    "/{diagnostico_id}/cancelar",
    response_model=DiagnosticoResponse,
)
def cancelar_diagnostico(
    diagnostico_id: int,
    db: Session = Depends(get_db),
):
    """
    Cancela logicamente o diagnóstico.

    O registro permanece no histórico longitudinal.
    """

    return DiagnosticoService.cancelar(
        db=db,
        diagnostico_id=diagnostico_id,
    )


@router.patch(
    "/{diagnostico_id}/revisar",
    response_model=DiagnosticoResponse,
)
def revisar_diagnostico(
    diagnostico_id: int,
    db: Session = Depends(get_db),
):
    """
    Marca o diagnóstico como revisado.
    """

    return DiagnosticoService.revisar(
        db=db,
        diagnostico_id=diagnostico_id,
    )


@router.get(
    "/paciente/{paciente_id}",
    response_model=List[DiagnosticoResponse],
)
def listar_diagnosticos_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
):
    """
    Retorna o histórico diagnóstico do paciente,
    do mais recente para o mais antigo.
    """

    return DiagnosticoService.listar_por_paciente(
        db=db,
        paciente_id=paciente_id,
    )