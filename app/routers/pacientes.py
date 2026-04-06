from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.acl import is_admin
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.paciente import Paciente
from app.models.clinica import Clinica
from app.models.profissional import Profissional
from app.models.usuario import Usuario
from app.schemas.paciente import PacienteCreate,PacienteUpdate, PacienteResponse
from app.routers.timeline import listar_timeline_paciente
from app.services.relatorio_paciente import gerar_pdf_paciente   

router = APIRouter(
    prefix="/pacientes",
    tags=["Pacientes"],
)

def serializar_paciente(p: Paciente):
    return {
        "id": p.id,
        "nome": p.nome,
        "data_nascimento": p.data_nascimento.isoformat() if p.data_nascimento else None,
        "genero": p.genero,
        "responsavel_nome": p.responsavel_nome,
        "responsavel_email": p.responsavel_email,
        "profissional_id": p.profissional_id,
        "profissional_nome": (
            p.profissional.nome if getattr(p, "profissional", None) else None
        ),
        "clinica_id": p.clinica_id,
        "clinica_nome": (
            p.clinica.nome if getattr(p, "clinica", None) else None
        ),
        "ativo": p.ativo,
    }


@router.get("/")
def listar_pacientes(
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual),
):
    query = db.query(Paciente).filter(Paciente.ativo == True)

    if not is_admin(usuario_atual):
        if not usuario_atual.clinica_id:
            raise HTTPException(status_code=403, detail="Usuário sem clínica vinculada")
        query = query.filter(Paciente.clinica_id == usuario_atual.clinica_id)

    pacientes = query.order_by(Paciente.nome.asc()).all()
    return [serializar_paciente(p) for p in pacientes]


@router.get("/{paciente_id}")
def obter_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id, Paciente.ativo == True).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    if not is_admin(usuario) and paciente.clinica_id != usuario.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return serializar_paciente(paciente)


@router.post("/")
def criar_paciente(
    payload: PacienteCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    data = payload.dict()

    profissional = None
    if data.get("profissional_id"):
        profissional = (
            db.query(Profissional)
            .filter(Profissional.id == data["profissional_id"], Profissional.ativo == True)
            .first()
        )
        if not profissional:
            raise HTTPException(status_code=404, detail="Profissional não encontrado")

    if not is_admin(usuario):
        if usuario.clinica_id is None:
            raise HTTPException(status_code=403, detail="Usuário sem clínica vinculada")

        data["clinica_id"] = usuario.clinica_id

        if profissional and profissional.clinica_id != usuario.clinica_id:
            raise HTTPException(
                status_code=403,
                detail="Profissional não pertence à clínica do usuário",
            )
    else:
        if profissional:
            data["clinica_id"] = profissional.clinica_id

        if not data.get("clinica_id"):
            raise HTTPException(
                status_code=400,
                detail="Clínica é obrigatória para criar paciente",
            )

    novo = Paciente(**data)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return serializar_paciente(novo)


@router.put("/{paciente_id}")
def atualizar_paciente(
    paciente_id: int,
    payload: PacienteUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    p = db.query(Paciente).filter(Paciente.id == paciente_id, Paciente.ativo == True).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    if not is_admin(usuario) and p.clinica_id != usuario.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    profissional = None
    if payload.profissional_id:
        profissional = (
            db.query(Profissional)
            .filter(Profissional.id == payload.profissional_id, Profissional.ativo == True)
            .first()
        )
        if not profissional:
            raise HTTPException(status_code=404, detail="Profissional não encontrado")

        if not is_admin(usuario) and profissional.clinica_id != usuario.clinica_id:
            raise HTTPException(
                status_code=403,
                detail="Profissional não pertence à clínica do usuário",
            )

    p.nome = payload.nome
    p.data_nascimento = payload.data_nascimento
    p.genero = payload.genero
    p.responsavel_nome = payload.responsavel_nome
    p.responsavel_email = payload.responsavel_email
    p.profissional_id = payload.profissional_id

    if profissional:
        p.clinica_id = profissional.clinica_id
    elif is_admin(usuario) and payload.clinica_id:
        p.clinica_id = payload.clinica_id

    db.commit()
    db.refresh(p)
    return serializar_paciente(p)


@router.delete("/{paciente_id}")
def inativar_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    p = db.query(Paciente).filter(Paciente.id == paciente_id, Paciente.ativo == True).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    if not is_admin(usuario) and p.clinica_id != usuario.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    p.ativo = False
    db.commit()
    return {"ok": True}

@router.get("/{paciente_id}/relatorio-pdf")
def baixar_relatorio_paciente_pdf(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()

    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    if usuario.clinica_id is not None and paciente.clinica_id != usuario.clinica_id:
        raise HTTPException(
            status_code=403,
            detail="Usuário sem permissão para este paciente."
        )

    try:
        eventos = listar_timeline_paciente(
            paciente_id=paciente_id,
            db=db,
            usuario_atual=usuario,
        )
    except Exception:
        eventos = []

    eventos_dict = [
        e.dict() if hasattr(e, "dict") else dict(e)
        for e in eventos
    ]

    clinica = None
    profissional = None

    if getattr(paciente, "clinica_id", None):
        clinica = db.query(Clinica).filter(Clinica.id == paciente.clinica_id).first()

    if getattr(paciente, "profissional_id", None):
        profissional = (
            db.query(Profissional)
            .filter(Profissional.id == paciente.profissional_id)
            .first()
        )

    paciente_dict = {
        "nome": paciente.nome,
        "data_nascimento": paciente.data_nascimento,
        "genero": paciente.genero,
        "responsavel_nome": getattr(paciente, "responsavel_nome", None),
        "responsavel_email": getattr(paciente, "responsavel_email", None),
        "clinica_nome": clinica.nome if clinica else None,
        "profissional_nome": profissional.nome if profissional else None,
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
