from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.intervencao import IntervencaoCreate, IntervencaoUpdate
from app.services.daily_record.models import ActorRef, ActorType
from app.services.interventions import InterventionService, InterventionSubmission, InterventionUpdate
from app.services.interventions.models import SourceType
from app.services.interventions.http import call, generic_response

router = APIRouter(prefix='/intervencoes', tags=['Intervenções'])
service = InterventionService()
SOURCE = SourceType.GENERIC_INTERVENTION


@router.post('/')
def criar_intervencao(intervencao: IntervencaoCreate, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(get_usuario_atual)):
    record = call(lambda: service.create(db, InterventionSubmission(
        intervencao.paciente_id, intervencao.requested_care_line,
        ActorRef(ActorType.PROFESSIONAL, usuario.id), intervencao.tipo,
        intervencao.descricao, intervencao.data_intervencao), user=usuario))
    return generic_response(record)


@router.get('/paciente/{paciente_id}')
def listar_por_paciente(paciente_id: int, care_line: str = Query(...), db: Session = Depends(get_db),
                        usuario: Usuario = Depends(get_usuario_atual)):
    return [generic_response(r) for r in call(lambda: service.list_for_patient(
        db, paciente_id, user=usuario, source_type=SOURCE, requested_care_line=care_line))]


@router.get('/{intervencao_id}')
def obter_intervencao(intervencao_id: int, care_line: str = Query(...), db: Session = Depends(get_db),
                     usuario: Usuario = Depends(get_usuario_atual)):
    return generic_response(call(lambda: service.get(db, SOURCE, intervencao_id, user=usuario, requested_care_line=care_line)))


@router.put('/{intervencao_id}')
def atualizar_intervencao(intervencao_id: int, payload: IntervencaoUpdate, care_line: str = Query(...),
                         db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    return generic_response(call(lambda: service.update(db, SOURCE, intervencao_id,
        InterventionUpdate(payload.tipo, payload.descricao, payload.data_intervencao),
        user=usuario, expected_patient_id=payload.paciente_id, requested_care_line=care_line)))


@router.delete('/{intervencao_id}')
def excluir_intervencao(intervencao_id: int, care_line: str = Query(...), db: Session = Depends(get_db),
                       usuario: Usuario = Depends(get_usuario_atual)):
    call(lambda: service.delete(db, SOURCE, intervencao_id, user=usuario, requested_care_line=care_line))
    return {'ok': True}
