from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.paciente import Paciente
from app.schemas.paciente import PacienteCreate, PacienteResponse
from app.core.deps import get_usuario_atual
from app.models.usuario import Usuario

router = APIRouter(prefix="/pacientes", tags=["Pacientes"])

@router.post("/", response_model=PacienteResponse)
def criar_paciente(
    paciente: PacienteCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if usuario.clinica_id is None:
        raise HTTPException(status_code=400, detail="Usuário sem clínica vinculada")

    data = paciente.dict(exclude={"clinica_id"})  # ignora clinica_id do cliente
    novo = Paciente(**data)
    novo.clinica_id = usuario.clinica_id

    # força o paciente a nascer na clínica do usuário
    if hasattr(novo, "clinica_id"):
        novo.clinica_id = usuario.clinica_id

    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo

@router.get("/", response_model=list[PacienteResponse])
def listar_pacientes(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual)
):
    return db.query(Paciente).filter(
        Paciente.clinica_id == usuario.clinica_id,
        Paciente.ativo == True
    ).all()

