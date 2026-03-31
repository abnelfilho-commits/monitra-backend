from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.responsavel import Responsavel
from app.models.responsavel_paciente import ResponsavelPaciente
from app.models.registro import RegistroDiario
from app.models.paciente import Paciente
from app.core.deps import get_responsavel_atual
from app.schemas.registro import (
    RegistroDiarioResponsavelCreate,
    RegistroDiarioResponsavelOut,
)

router = APIRouter(
    prefix="/responsavel",
    tags=["App Responsável - Registros"]
)


def validar_vinculo_ativo(db: Session, responsavel_id: int, paciente_id: int):
    vinculo = (
        db.query(ResponsavelPaciente)
        .filter(
            ResponsavelPaciente.responsavel_id == responsavel_id,
            ResponsavelPaciente.paciente_id == paciente_id,
            ResponsavelPaciente.ativo == True,
        )
        .first()
    )
    return vinculo is not None


@router.get("/pacientes/{paciente_id}/registros", response_model=list[RegistroDiarioResponsavelOut])
def listar_registros_meu_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    if not validar_vinculo_ativo(db, responsavel.id, paciente_id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado a este paciente.")

    registros = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.paciente_id == paciente_id,
            RegistroDiario.origem == "RESPONSAVEL",
            RegistroDiario.responsavel_id == responsavel.id,
        )
        .order_by(RegistroDiario.data.desc(), RegistroDiario.id.desc())
        .all()
    )
    return registros


@router.post("/pacientes/{paciente_id}/registros", response_model=RegistroDiarioResponsavelOut)
def criar_registro_meu_paciente(
    paciente_id: int,
    payload: RegistroDiarioResponsavelCreate,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    if not validar_vinculo_ativo(db, responsavel.id, paciente_id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado a este paciente.")

    paciente = (
        db.query(Paciente)
        .filter(Paciente.id == paciente_id, Paciente.ativo == True)
        .first()
    )
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    hoje = date.today()
    if payload.data < (hoje - timedelta(days=1)) or payload.data > hoje:
        raise HTTPException(
            status_code=400,
            detail="A data do registro deve ser hoje ou ontem."
        )

    existente = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.paciente_id == paciente_id,
            RegistroDiario.data == payload.data,
            RegistroDiario.origem == "RESPONSAVEL",
            RegistroDiario.responsavel_id == responsavel.id,
        )
        .first()
    )

    if existente:
        raise HTTPException(
            status_code=400,
            detail="Você já enviou um registro para esta data."
        )

    registro = RegistroDiario(
        paciente_id=paciente_id,
        data=payload.data,
        sono_qualidade=payload.sono_qualidade,
        evacuacao=payload.evacuacao,
        consistencia_fezes=payload.consistencia_fezes,
        irritabilidade=payload.irritabilidade,
        crise_sensorial=payload.crise_sensorial,
        alimentacao=payload.alimentacao,
        observacao=payload.observacao,
        origem="RESPONSAVEL",
        responsavel_id=responsavel.id,
        criado_por_tipo="RESPONSAVEL",
        criado_por_id=responsavel.id,
    )

    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


@router.get("/registros/{registro_id}", response_model=RegistroDiarioResponsavelOut)
def obter_registro(
    registro_id: int,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    registro = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.id == registro_id,
            RegistroDiario.origem == "RESPONSAVEL",
            RegistroDiario.responsavel_id == responsavel.id,
        )
        .first()
    )

    if not registro:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    if not validar_vinculo_ativo(db, responsavel.id, registro.paciente_id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado a este registro.")

    return registro
