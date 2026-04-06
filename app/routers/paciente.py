from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO

from app.database import get_db
from app.services.relatorio_paciente import gerar_pdf_paciente
from app.models.paciente import Paciente
from app.schemas.paciente import PacienteCreate, PacienteResponse
from app.core.deps import get_usuario_atual
from app.models.usuario import Usuario
from app.api.routes.timeline import listar_timeline_paciente

router = APIRouter(prefix="/pacientes", tags=["Pacientes"])


@router.get("/{paciente_id}/relatorio-pdf")
def baixar_relatorio_paciente_pdf(
    paciente_id: int,
    db: Session = Depends(get_db),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()

    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    try:
        eventos = listar_timeline_paciente(
            paciente_id=paciente_id,
            db=db,
            usuario_atual=None,
        )
    except Exception:
        eventos = []

    eventos_dict = [
        e.dict() if hasattr(e, "dict") else dict(e)
        for e in eventos
    ]

    paciente_dict = {
        "nome": paciente.nome,
        "data_nascimento": paciente.data_nascimento,
        "genero": paciente.genero,
        "responsavel_nome": paciente.responsavel_nome,
        "responsavel_email": paciente.responsavel_email,
        "clinica_nome": getattr(paciente, "clinica_nome", None),
        "profissional_nome": getattr(paciente, "profissional_nome", None),
    }

    try:
        pdf_bytes = gerar_pdf_paciente(paciente_dict, eventos_dict)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar PDF: {str(e)}"
        )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="relatorio_paciente_{paciente_id}.pdf"'
        },
    )


@router.post("/", response_model=PacienteResponse)
def criar_paciente(
    paciente: PacienteCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if usuario.clinica_id is None:
        raise HTTPException(status_code=400, detail="Usuário sem clínica vinculada")

    data = paciente.dict(exclude={"clinica_id"})
    novo = Paciente(**data)
    novo.clinica_id = usuario.clinica_id

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
