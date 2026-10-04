"""Authenticated read-only Mental Health boundary. No global-role bypass."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.schemas.saude_mental import InstituicaoDisponivel, JornadaMental, PessoasMentais
from app.services.saude_mental import SaudeMentalService, MentalHealthUnavailable

router = APIRouter(prefix='/saude-mental', tags=['Saúde Mental'])
service = SaudeMentalService()


def read(operation):
    try:
        return operation()
    except MentalHealthUnavailable:
        raise HTTPException(503, {'code': 'MENTAL_HEALTH_UNAVAILABLE'}) from None


@router.get('/instituicoes', response_model=list[InstituicaoDisponivel])
def institutions(db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return service.institutions(db, actor_id=actor.id)


@router.get('/pessoas', response_model=PessoasMentais)
def people(instituicao_id: int = Query(..., gt=0, le=2147483647),
           offset: int = Query(0, ge=0), db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return read(lambda: service.people(db, actor_id=actor.id, institution=instituicao_id, offset=offset))


@router.get('/pessoas/{pessoa_id}/contextos/{contexto_id}', response_model=JornadaMental)
def journey(pessoa_id: int = Path(..., gt=0, le=2147483647),
            contexto_id: int = Path(..., gt=0, le=2147483647),
            instituicao_id: int = Query(..., gt=0, le=2147483647),
            db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    result = read(lambda: service.journey(db, actor_id=actor.id, institution=instituicao_id,
                                         person=pessoa_id, context=contexto_id))
    if result is None:
        raise HTTPException(404, {'code': 'JOURNEY_UNAVAILABLE'})
    return result
