from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.acl import is_admin
from app.core.acl import assert_clinica_access
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.paciente import Paciente
from app.models.profissional import Profissional
from app.models.usuario import Usuario
from app.schemas.paciente import PacienteCreate, PacienteUpdate
from app.services.relatorio_paciente import gerar_pdf_paciente

router = APIRouter(
    prefix="/pacientes",
    tags=["Pacientes"],
)


def calcular_idade(data_nascimento):
    if not data_nascimento:
        return None

    hoje = date.today()
    return hoje.year - data_nascimento.year - (
        (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day)
    )


def serializar_paciente(p: Paciente):
    profissional = getattr(p, "profissional", None)
    clinica = getattr(p, "clinica", None)

    if not clinica and profissional:
        clinica = getattr(profissional, "clinica", None)

    return {
        "id": p.id,
        "nome": p.nome,
        "data_nascimento": p.data_nascimento,
        "genero": p.genero,
        "responsavel_nome": p.responsavel_nome,
        "responsavel_email": p.responsavel_email,
        "clinica_id": p.clinica_id,
        "profissional_id": p.profissional_id,
        "idade": calcular_idade(p.data_nascimento),
        "profissional_nome": profissional.nome if profissional else None,
        "clinica_nome": clinica.nome if clinica else None,
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

    return query.order_by(Paciente.nome.asc()).all()


@router.get("/{paciente_id}")
def obter_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    p = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    assert_clinica_access(usuario, p.clinica_id)
    return serializar_paciente(p)


@router.post("/")
def criar_paciente(
    paciente: PacienteCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    data = paciente.dict()

    profissional = None
    if data.get("profissional_id"):
        profissional = (
            db.query(Profissional)
            .filter(
                Profissional.id == data["profissional_id"],
                Profissional.ativo == True,
            )
            .first()
        )

        if not profissional:
            raise HTTPException(status_code=404, detail="Profissional não encontrado")

    if usuario.perfil != "admin":
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

    if not data.get("clinica_id") and profissional:
        data["clinica_id"] = profissional.clinica_id

    novo = Paciente(**data)
    db.add(novo)

    try:
        db.commit()
        db.refresh(novo)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Dados inválidos para criar paciente")

    return serializar_paciente(novo)


@router.put("/{paciente_id}")
def atualizar_paciente(
    paciente_id: int,
    paciente: PacienteUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    p = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    assert_clinica_access(usuario, p.clinica_id)

    profissional = None
    if paciente.profissional_id:
        profissional = (
            db.query(Profissional)
            .filter(
                Profissional.id == paciente.profissional_id,
                Profissional.ativo == True,
            )
            .first()
        )

        if not profissional:
            raise HTTPException(status_code=404, detail="Profissional não encontrado")

        if usuario.perfil != "admin" and profissional.clinica_id != usuario.clinica_id:
            raise HTTPException(
                status_code=403,
                detail="Profissional não pertence à clínica do usuário",
            )

    p.nome = paciente.nome
    p.data_nascimento = paciente.data_nascimento
    p.genero = paciente.genero
    p.responsavel_nome = paciente.responsavel_nome
    p.responsavel_email = paciente.responsavel_email
    p.profissional_id = paciente.profissional_id

    if profissional:
        p.clinica_id = profissional.clinica_id
    elif usuario.perfil == "admin" and paciente.clinica_id:
        p.clinica_id = paciente.clinica_id

    try:
        db.commit()
        db.refresh(p)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Dados inválidos para atualizar paciente")

    return serializar_paciente(p)


@router.delete("/{paciente_id}")
def inativar_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    p = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    assert_clinica_access(usuario, p.clinica_id)

    p.ativo = False
    db.commit()
    return {"ok": True}


@router.get("/{paciente_id}/timeline")
def listar_timeline_consolidada(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    assert_clinica_access(usuario, paciente.clinica_id)

    q = text(
        """
        SELECT id, tipo_evento, data, descricao, usuario_id
        FROM vw_timeline_paciente
        WHERE paciente_id = :paciente_id
        ORDER BY data DESC
        """
    )

    return db.execute(q, {"paciente_id": paciente_id}).mappings().all()


@router.get("/{paciente_id}/relatorio-pdf")
def baixar_relatorio_paciente_pdf(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    p = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    if usuario.perfil != "admin" and p.clinica_id != usuario.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    q = text(
        """
        SELECT id, tipo_evento, data, descricao, usuario_id
        FROM vw_timeline_paciente
        WHERE paciente_id = :paciente_id
        ORDER BY data DESC
        """
    )

    eventos = db.execute(q, {"paciente_id": paciente_id}).mappings().all()
    eventos = [dict(e) for e in eventos]

    paciente_dict = {
        "id": p.id,
        "nome": p.nome,
        "data_nascimento": p.data_nascimento,
        "genero": getattr(p, "genero", None),
        "responsavel_nome": getattr(p, "responsavel_nome", None),
        "responsavel_email": getattr(p, "responsavel_email", None),
        "profissional_nome": p.profissional.nome if getattr(p, "profissional", None) else None,
        "clinica_nome": (
            p.profissional.clinica.nome
            if getattr(p, "profissional", None) and getattr(p.profissional, "clinica", None)
            else (p.clinica.nome if getattr(p, "clinica", None) else None)
        ),
    }

    pdf_bytes = gerar_pdf_paciente(paciente_dict, eventos)
    filename = f"relatorio_paciente_{p.id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
