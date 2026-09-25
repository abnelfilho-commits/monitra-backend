"""Global ADMIN transport for institutional links; domain rules stay in G2.B.1."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.core.permissoes import exigir_admin
from app.models.institucional import PacienteInstituicao, ProfissionalInstituicao, PacienteProfissional
from app.schemas.institucional import (
    PacienteInstituicaoRequest, ProfissionalInstituicaoRequest, PacienteProfissionalRequest,
    PacienteInstituicaoResponse, ProfissionalInstituicaoResponse, PacienteProfissionalResponse,
    CloseInstitucionalRequest, MotivoInstitucional,
)
from app.services.institucional import InstitucionalService, InstitucionalErro


class InstitutionalRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError:
                # Scope validation formatting to this router, preserving legacy APIs.
                raise HTTPException(422, {'code': 'INVALID_PAYLOAD'}) from None
        return handle


router = APIRouter(prefix='/admin/vinculos-institucionais',
                   tags=['Vínculos institucionais administrativos'], route_class=InstitutionalRoute)
service = InstitucionalService()
ERROR_STATUS = {
    'ADMIN_REQUIRED': 403, 'LINK_NOT_FOUND': 404,
    'PERIOD_CONFLICT': 409, 'CLOSE_CONFLICT': 409, 'LINK_INVALIDATED': 409,
    'DEPENDENT_LINK_CONFLICT': 409, 'LEGACY_CONTEXT_UNRESOLVED': 409,
    'PATIENT_MISMATCH': 409, 'INSTITUTION_MISMATCH': 409, 'PARENT_PERIOD_OR_STATE_CONFLICT': 409,
    'INVALID_CLOSE': 422, 'INVALID_PERIOD': 422, 'REASON_REQUIRED': 422,
    'EXPLICIT_INSTITUTION_REQUIRED': 422,
}


def respond(db, operation, response, *, write=False, many=False):
    try:
        result = operation()
        # Validate output before committing any mutation.
        output = ([response.model_validate(row) for row in result] if many
                  else response.model_validate(result))
        if write:
            db.commit()
        return output
    except InstitucionalErro as exc:
        db.rollback()
        status = ERROR_STATUS.get(exc.code, 500)
        code = exc.code if status != 500 else 'INSTITUTIONAL_OPERATION_FAILED'
        raise HTTPException(status, {'code': code}) from None
    except IntegrityError:
        db.rollback()
        raise  # Preserve the existing application's global integrity handler.
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'INSTITUTIONAL_OPERATION_FAILED'}) from None


@router.post('/pacientes', response_model=PacienteInstituicaoResponse)
def create_pacientes(payload: PacienteInstituicaoRequest, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.create(db, PacienteInstituicao, payload.model_dump(exclude={'motivo'}),
        actor_id=admin.id, motivo=payload.motivo), PacienteInstituicaoResponse, write=True)


@router.get('/pacientes/{identity}', response_model=PacienteInstituicaoResponse)
def get_pacientes(identity: int, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.get(db, PacienteInstituicao, identity, actor_id=admin.id), PacienteInstituicaoResponse)


@router.get('/pacientes', response_model=list[PacienteInstituicaoResponse])
def list_pacientes(instituicao_id: int = Query(...), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.list(db, PacienteInstituicao, instituicao_id=instituicao_id,
        actor_id=admin.id), PacienteInstituicaoResponse, many=True)


@router.post('/pacientes/{identity}/close', response_model=PacienteInstituicaoResponse)
def close_pacientes(identity: int, payload: CloseInstitucionalRequest, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.close(db, PacienteInstituicao, identity, payload.data_fim,
        actor_id=admin.id, motivo=payload.motivo), PacienteInstituicaoResponse, write=True)


@router.post('/pacientes/{identity}/invalidate', response_model=PacienteInstituicaoResponse)
def invalidate_pacientes(identity: int, payload: MotivoInstitucional, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.invalidate(db, PacienteInstituicao, identity,
        actor_id=admin.id, motivo=payload.motivo), PacienteInstituicaoResponse, write=True)


@router.post('/profissionais', response_model=ProfissionalInstituicaoResponse)
def create_profissionais(payload: ProfissionalInstituicaoRequest, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.create(db, ProfissionalInstituicao, payload.model_dump(exclude={'motivo'}),
        actor_id=admin.id, motivo=payload.motivo), ProfissionalInstituicaoResponse, write=True)


@router.get('/profissionais/{identity}', response_model=ProfissionalInstituicaoResponse)
def get_profissionais(identity: int, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.get(db, ProfissionalInstituicao, identity, actor_id=admin.id), ProfissionalInstituicaoResponse)


@router.get('/profissionais', response_model=list[ProfissionalInstituicaoResponse])
def list_profissionais(instituicao_id: int = Query(...), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.list(db, ProfissionalInstituicao, instituicao_id=instituicao_id,
        actor_id=admin.id), ProfissionalInstituicaoResponse, many=True)


@router.post('/profissionais/{identity}/close', response_model=ProfissionalInstituicaoResponse)
def close_profissionais(identity: int, payload: CloseInstitucionalRequest, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.close(db, ProfissionalInstituicao, identity, payload.data_fim,
        actor_id=admin.id, motivo=payload.motivo), ProfissionalInstituicaoResponse, write=True)


@router.post('/profissionais/{identity}/invalidate', response_model=ProfissionalInstituicaoResponse)
def invalidate_profissionais(identity: int, payload: MotivoInstitucional, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.invalidate(db, ProfissionalInstituicao, identity,
        actor_id=admin.id, motivo=payload.motivo), ProfissionalInstituicaoResponse, write=True)


@router.post('/paciente-profissionais', response_model=PacienteProfissionalResponse)
def create_paciente_profissionais(payload: PacienteProfissionalRequest, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.create(db, PacienteProfissional, payload.model_dump(exclude={'motivo'}),
        actor_id=admin.id, motivo=payload.motivo), PacienteProfissionalResponse, write=True)


@router.get('/paciente-profissionais/{identity}', response_model=PacienteProfissionalResponse)
def get_paciente_profissionais(identity: int, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.get(db, PacienteProfissional, identity, actor_id=admin.id), PacienteProfissionalResponse)


@router.get('/paciente-profissionais', response_model=list[PacienteProfissionalResponse])
def list_paciente_profissionais(instituicao_id: int = Query(...), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.list(db, PacienteProfissional, instituicao_id=instituicao_id,
        actor_id=admin.id), PacienteProfissionalResponse, many=True)


@router.post('/paciente-profissionais/{identity}/close', response_model=PacienteProfissionalResponse)
def close_paciente_profissionais(identity: int, payload: CloseInstitucionalRequest, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.close(db, PacienteProfissional, identity, payload.data_fim,
        actor_id=admin.id, motivo=payload.motivo), PacienteProfissionalResponse, write=True)


@router.post('/paciente-profissionais/{identity}/invalidate', response_model=PacienteProfissionalResponse)
def invalidate_paciente_profissionais(identity: int, payload: MotivoInstitucional, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.invalidate(db, PacienteProfissional, identity,
        actor_id=admin.id, motivo=payload.motivo), PacienteProfissionalResponse, write=True)
