from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.registro import RegistroDiario
from app.services.eixos import calcular_eixo_dominante
from app.core.acl import is_admin, is_admin_global
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.paciente import Paciente
from app.models.clinica import Clinica
from app.models.profissional import Profissional
from app.models.usuario import Usuario
from app.schemas.paciente import PacienteCreate,PacienteUpdate, PacienteResponse
from app.routers.timeline import listar_timeline_paciente

from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.services.report_engine.report_service import ReportService  

from app.models.modular import PacienteModulo, ModuloClinico

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
        "altura": float(p.altura) if p.altura is not None else None,
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

    if not is_admin_global(usuario_atual):
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

    if not is_admin_global(usuario) and paciente.clinica_id != usuario.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Buscar últimos registros
    registros_recentes = []

    # Calcular eixo
    leitura_eixo = calcular_eixo_dominante(registros_recentes)

    # Montar resposta
    paciente_dict = serializar_paciente(paciente)

    paciente_dict["status_clinico"] = {
        "eixo_dominante": leitura_eixo["eixo_dominante"],
        "eixo_dominante_label": leitura_eixo["eixo_dominante_label"],
        "confianca_eixo": leitura_eixo["confianca_eixo"],
        "base_sustentacao": leitura_eixo["base_sustentacao"],
    }
   
    return paciente_dict

@router.post("/")
def criar_paciente(
    payload: PacienteCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    data = payload.dict()

    modulo_id = data.pop("modulo_id", None)

    if not modulo_id:
        raise HTTPException(
            status_code=400,
            detail="Módulo é obrigatório para criar paciente",
        )

    modulo = (
        db.query(ModuloClinico)
        .filter(
            ModuloClinico.id == modulo_id,
            ModuloClinico.ativo == True,
        )
        .first()
    )

    if not modulo:
        raise HTTPException(
            status_code=404,
            detail="Módulo clínico não encontrado",
        )

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
            raise HTTPException(
                status_code=404,
                detail="Profissional não encontrado",
            )

    if not is_admin(usuario):
        if usuario.clinica_id is None:
            raise HTTPException(
                status_code=403,
                detail="Usuário sem clínica vinculada",
            )

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

    try:
        novo = Paciente(**data)
        db.add(novo)

        # Precisamos do ID do paciente sem concluir a transação.
        db.flush()

        paciente_modulo = PacienteModulo(
            paciente_id=novo.id,
            modulo_id=modulo_id,
            ativo=True,
        )

        db.add(paciente_modulo)

        # Paciente + módulo são confirmados juntos.
        db.commit()
        db.refresh(novo)

        return serializar_paciente(novo)

    except Exception:
        db.rollback()
        raise

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

    if not is_admin_global(usuario) and p.clinica_id != usuario.clinica_id:
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

        if not is_admin_global(usuario) and profissional.clinica_id != usuario.clinica_id:
            raise HTTPException(
                status_code=403,
                detail="Profissional não pertence à clínica do usuário",
            )

    p.nome = payload.nome
    p.data_nascimento = payload.data_nascimento
    p.genero = payload.genero
    p.altura = payload.altura
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

    if not is_admin_global(usuario) and p.clinica_id != usuario.clinica_id:
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
    paciente = (
        db.query(Paciente)
        .filter(
            Paciente.id == paciente_id,
            Paciente.ativo == True,
        )
        .first()
    )

    if not paciente:
        raise HTTPException(
            status_code=404,
            detail="Paciente não encontrado.",
        )

    if (
        not is_admin_global(usuario)
        and paciente.clinica_id != usuario.clinica_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Usuário sem permissão para este paciente.",
        )

    vinculos = (
        db.query(
            PacienteModulo,
            ModuloClinico,
        )
        .join(
            ModuloClinico,
            ModuloClinico.id == PacienteModulo.modulo_id,
        )
        .filter(
            PacienteModulo.paciente_id == paciente_id,
            PacienteModulo.ativo == True,
            ModuloClinico.ativo == True,
        )
        .all()
    )

    if not vinculos:
        raise HTTPException(
            status_code=400,
            detail="Paciente sem módulo clínico ativo.",
        )

    module_map = {
        "neurodesenvolvimento": "NEURO",
    }

    modulos_suportados = [
        (
            paciente_modulo,
            modulo,
            module_map.get(modulo.slug),
        )
        for paciente_modulo, modulo in vinculos
        if modulo.slug in module_map
    ]

    if not modulos_suportados:
        modulos = ", ".join(
            modulo.nome
            for _, modulo in vinculos
        )

        raise HTTPException(
            status_code=422,
            detail=(
                "Relatório Longitudinal Inteligente "
                f"ainda não disponível para: {modulos}."
            ),
        )

    if len(modulos_suportados) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Paciente possui mais de um módulo clínico "
                "compatível com o relatório. "
                "É necessário selecionar o módulo."
            ),
        )

    _, modulo_clinico, report_module = modulos_suportados[0]

    period_start = (
        paciente.created_at.date()
        if paciente.created_at
        else date.today()
    )

    period_end = date.today()

    temp_path = None

    try:
        service = ReportService()

        context = service.generate(
            report_code="CLN-001",
            subject_id=paciente_id,
            requested_by=usuario.id,
            period_start=period_start,
            period_end=period_end,
            module=report_module,
            db=db,
        )

        with NamedTemporaryFile(
            prefix=f"cln_001_{paciente_id}_",
            suffix=".pdf",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name

        service.render(
            context=context,
            output_path=temp_path,
        )

        pdf_bytes = Path(temp_path).read_bytes()

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Erro ao gerar Relatório Longitudinal Inteligente: "
                f"{str(exc)}"
            ),
        )

    finally:
        if temp_path:
            path = Path(temp_path)

            if path.exists():
                path.unlink()

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="'
                f'relatorio_longitudinal_{paciente_id}.pdf"'
            )
        },
    )
