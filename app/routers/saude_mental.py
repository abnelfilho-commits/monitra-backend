"""Authenticated Mental Health boundary. No global-role bypass."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.schemas.saude_mental import InstituicaoDisponivel, JornadaMentalDetalhe, PessoasMentais
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


@router.get('/pessoas/{pessoa_id}/contextos/{contexto_id}', response_model=JornadaMentalDetalhe)
def journey(pessoa_id: int = Path(..., gt=0, le=2147483647),
            contexto_id: int = Path(..., gt=0, le=2147483647),
            instituicao_id: int = Query(..., gt=0, le=2147483647),
            db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    result = read(lambda: service.journey(db, actor_id=actor.id, institution=instituicao_id,
                                         person=pessoa_id, context=contexto_id))
    if result is None:
        raise HTTPException(404, {'code': 'JOURNEY_UNAVAILABLE'})
    return result


from sqlalchemy.exc import SQLAlchemyError
from app.schemas.checkin_bem_estar import CheckinCreate, CheckinOut
from app.services.checkin_bem_estar import CheckinBemEstarService, CheckinDenied, CheckinInvalid, CheckinUnavailable


@router.post('/pessoas/{pessoa_id}/contextos/{contexto_id}/check-ins', response_model=CheckinOut, status_code=201)
def create_checkin(payload: CheckinCreate,
                   pessoa_id: int = Path(..., gt=0, le=2147483647),
                   contexto_id: int = Path(..., gt=0, le=2147483647),
                   instituicao_id: int = Query(..., gt=0, le=2147483647),
                   db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    try:
        result=CheckinBemEstarService().create(db,payload,actor=actor.id,institution=instituicao_id,person=pessoa_id,context=contexto_id)
        response=CheckinOut.model_validate(result).model_dump(mode='json')
        db.commit()
        return response
    except CheckinDenied:
        db.rollback()
        raise HTTPException(403, {'code':'CHECKIN_UNAVAILABLE'}) from None
    except CheckinInvalid:
        db.rollback()
        raise HTTPException(422, {'code':'INVALID_CHECKIN'}) from None
    except CheckinUnavailable:
        db.rollback()
        raise HTTPException(503, {'code':'CHECKIN_CATALOG_UNAVAILABLE'}) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, {'code':'CHECKIN_NOT_SAVED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code':'CHECKIN_NOT_SAVED'}) from None


from app.schemas.diagnostico_mental import DiagnosticoMentalCreate, DiagnosticoMentalOut
from app.services.diagnostico_mental import DiagnosticoMentalService, DiagnosisDenied


@router.post('/pessoas/{pessoa_id}/contextos/{contexto_id}/diagnosticos', response_model=DiagnosticoMentalOut, status_code=201)
def create_diagnosis(payload: DiagnosticoMentalCreate,
                     pessoa_id: int = Path(..., gt=0, le=2147483647),
                     contexto_id: int = Path(..., gt=0, le=2147483647),
                     instituicao_id: int = Query(..., gt=0, le=2147483647),
                     db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    try:
        result = DiagnosticoMentalService().create(db, payload, actor=actor.id, institution=instituicao_id,
                                                   person=pessoa_id, context=contexto_id)
        response = DiagnosticoMentalOut.model_validate(result).model_dump(mode='json')
        db.commit()
        return response
    except DiagnosisDenied:
        db.rollback()
        raise HTTPException(403, {'code': 'DIAGNOSIS_UNAVAILABLE'}) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, {'code': 'DIAGNOSIS_NOT_SAVED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'DIAGNOSIS_NOT_SAVED'}) from None


from app.schemas.intervencao_mental import IntervencaoMentalCreate, IntervencaoMentalOut
from app.services.intervencao_mental import IntervencaoMentalService, InterventionDenied


@router.post('/pessoas/{pessoa_id}/contextos/{contexto_id}/intervencoes', response_model=IntervencaoMentalOut, status_code=201)
def create_intervention(payload: IntervencaoMentalCreate,
                     pessoa_id: int = Path(..., gt=0, le=2147483647),
                     contexto_id: int = Path(..., gt=0, le=2147483647),
                     instituicao_id: int = Query(..., gt=0, le=2147483647),
                     db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    try:
        result = IntervencaoMentalService().create(db, payload, actor=actor.id, institution=instituicao_id,
                                                   person=pessoa_id, context=contexto_id)
        response = IntervencaoMentalOut.model_validate(result).model_dump(mode='json')
        db.commit()
        return response
    except InterventionDenied:
        db.rollback()
        raise HTTPException(403, {'code': 'INTERVENTION_UNAVAILABLE'}) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, {'code': 'INTERVENTION_NOT_SAVED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'INTERVENTION_NOT_SAVED'}) from None


from app.schemas.phq9 import PHQ9Create, PHQ9Out
from app.services.phq9 import PHQ9Service, PHQ9Denied, PHQ9Unavailable


@router.post('/pessoas/{pessoa_id}/contextos/{contexto_id}/phq9', response_model=PHQ9Out, status_code=201)
def create_phq9(payload: PHQ9Create,
                     pessoa_id: int = Path(..., gt=0, le=2147483647),
                     contexto_id: int = Path(..., gt=0, le=2147483647),
                     instituicao_id: int = Query(..., gt=0, le=2147483647),
                     db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    try:
        result = PHQ9Service().create(db, payload, actor=actor.id, institution=instituicao_id,
                                                   person=pessoa_id, context=contexto_id)
        response = PHQ9Out.model_validate(result).model_dump(mode='json')
        db.commit()
        return response
    except PHQ9Denied:
        db.rollback()
        raise HTTPException(403, {'code': 'PHQ9_UNAVAILABLE'}) from None
    except PHQ9Unavailable:
        db.rollback()
        raise HTTPException(503, {'code': 'PHQ9_CATALOG_UNAVAILABLE'}) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, {'code': 'PHQ9_NOT_SAVED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'PHQ9_NOT_SAVED'}) from None


from app.schemas.gad7 import GAD7Create, GAD7Out
from app.services.gad7 import GAD7Service, GAD7Denied, GAD7Unavailable


@router.post('/pessoas/{pessoa_id}/contextos/{contexto_id}/gad7', response_model=GAD7Out, status_code=201)
def create_gad7(payload: GAD7Create,
                     pessoa_id: int = Path(..., gt=0, le=2147483647),
                     contexto_id: int = Path(..., gt=0, le=2147483647),
                     instituicao_id: int = Query(..., gt=0, le=2147483647),
                     db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    try:
        result = GAD7Service().create(db, payload, actor=actor.id, institution=instituicao_id,
                                                   person=pessoa_id, context=contexto_id)
        response = GAD7Out.model_validate(result).model_dump(mode='json')
        db.commit()
        return response
    except GAD7Denied:
        db.rollback()
        raise HTTPException(403, {'code': 'GAD7_UNAVAILABLE'}) from None
    except GAD7Unavailable:
        db.rollback()
        raise HTTPException(503, {'code': 'GAD7_CATALOG_UNAVAILABLE'}) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, {'code': 'GAD7_NOT_SAVED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'GAD7_NOT_SAVED'}) from None


from app.schemas.cbi import CBICreate, CBIOut
from app.services.cbi import CBIService, CBIDenied, CBIUnavailable


@router.post('/pessoas/{pessoa_id}/contextos/{contexto_id}/cbi', response_model=CBIOut, status_code=201)
def create_cbi(payload: CBICreate,
                     pessoa_id: int = Path(..., gt=0, le=2147483647),
                     contexto_id: int = Path(..., gt=0, le=2147483647),
                     instituicao_id: int = Query(..., gt=0, le=2147483647),
                     db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    try:
        result = CBIService().create(db, payload, actor=actor.id, institution=instituicao_id,
                                                   person=pessoa_id, context=contexto_id)
        response = CBIOut.model_validate(result).model_dump(mode='json')
        db.commit()
        return response
    except CBIDenied:
        db.rollback()
        raise HTTPException(403, {'code': 'CBI_UNAVAILABLE'}) from None
    except CBIUnavailable:
        db.rollback()
        raise HTTPException(503, {'code': 'CBI_CATALOG_UNAVAILABLE'}) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(409, {'code': 'CBI_NOT_SAVED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'CBI_NOT_SAVED'}) from None
