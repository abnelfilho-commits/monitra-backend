"""Administrative identity only. No digital-account creation endpoint."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.core.permissoes import exigir_admin
from app.schemas.identidade import CpfConsulta, IdentidadeComando, AdicionarPapel, AssociarPapelLegado, AssociarContaLegada
from app.services.identidade import IdentidadeService, IdentidadeErro, constraint_violation

router = APIRouter(prefix="/admin/identidades", tags=["Identidade administrativa"])
service = IdentidadeService()


def write(db, actor, command):
    try:
        result = service.executar(db, actor.id, command)
        db.commit()
        return result
    except IdentidadeErro as exc:
        db.rollback()
        raise HTTPException(exc.status, {"code": exc.code, "fields": exc.fields}) from None
    except IntegrityError as exc:
        db.rollback()
        names = ("uq_pacientes_pessoa_id", "uq_profissionais_pessoa_id", "uq_responsaveis_pessoa_id", "uq_usuarios_pessoa_id", "uq_identidade_operacao_chave")
        if any(constraint_violation(exc, n) for n in names):
            raise HTTPException(409, {"code": "CONCURRENT_IDENTITY_CONFLICT"}) from None
        raise HTTPException(500, {"code": "IDENTITY_PERSISTENCE_FAILED"}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {"code": "IDENTITY_OPERATION_FAILED"}) from None


@router.post("/localizar")
def localizar(payload: CpfConsulta, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return service.localizar(db, admin.id, payload.cpf)


@router.post("/pessoas")
def pessoa(payload: IdentidadeComando, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return write(db, admin, payload)


@router.post("/papeis")
def papel(payload: AdicionarPapel, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return write(db, admin, payload)


@router.post("/associacoes/papeis-legados")
def associar_papel(payload: AssociarPapelLegado, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return write(db, admin, payload)


@router.post("/associacoes/contas-legadas")
def associar_conta(payload: AssociarContaLegada, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return write(db, admin, payload)


@router.get("/operacoes/{key}")
def resultado(key: UUID, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    try:
        return service.resultado(db, admin.id, key)
    except IdentidadeErro as exc:
        raise HTTPException(exc.status, {"code": exc.code}) from None
