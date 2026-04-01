from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.responsavel import Responsavel
from app.models.responsavel_paciente import ResponsavelPaciente
from app.models.paciente import Paciente
from app.core.deps import get_responsavel_atual

router = APIRouter(
    prefix="/responsavel/pacientes",
    tags=["App Responsável - Pacientes"]
)


def calcular_idade(data_nascimento):
    if not data_nascimento:
        return None
    hoje = date.today()
    return hoje.year - data_nascimento.year - (
        (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day)
    )

@router.get("")
@router.get("/")
def listar_meus_pacientes(
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    vinculos = (
        db.query(ResponsavelPaciente, Paciente)
        .join(Paciente, Paciente.id == ResponsavelPaciente.paciente_id)
        .filter(
            ResponsavelPaciente.responsavel_id == responsavel.id,
            ResponsavelPaciente.ativo == True,
            Paciente.ativo == True,
        )
        .all()
    )

    resultado = []
    for vinculo, paciente in vinculos:
        resultado.append({
            "id": paciente.id,
            "nome": paciente.nome,
            "data_nascimento": paciente.data_nascimento,
            "idade": calcular_idade(paciente.data_nascimento),
            "profissional_nome": getattr(paciente, "profissional_nome", None),
            "clinica_nome": getattr(paciente, "clinica_nome", None),
        })

    return resultado


@router.get("/{paciente_id}")
def obter_meu_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    vinculo = (
        db.query(ResponsavelPaciente)
        .filter(
            ResponsavelPaciente.responsavel_id == responsavel.id,
            ResponsavelPaciente.paciente_id == paciente_id,
            ResponsavelPaciente.ativo == True,
        )
        .first()
    )

    if not vinculo:
        raise HTTPException(status_code=403, detail="Acesso não autorizado a este paciente.")

    paciente = (
        db.query(Paciente)
        .filter(Paciente.id == paciente_id, Paciente.ativo == True)
        .first()
    )
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    return {
        "id": paciente.id,
        "nome": paciente.nome,
        "data_nascimento": paciente.data_nascimento,
        "idade": calcular_idade(paciente.data_nascimento),
        "profissional_nome": getattr(paciente, "profissional_nome", None),
        "clinica_nome": getattr(paciente, "clinica_nome", None),
    }
