"""Authenticated legacy assessments; contextual journeys keep their own routes."""
from functools import wraps
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models.avaliacao_clinica import AvaliacaoClinica as Assessment
from app.services.clinical_engine.assessment_service import executar_avaliacao_por_registro
from app.services.clinical_engine.assessment_access import (
    assessment_access, execution_access, permitted_modules, record_access,
    unavailable, valid_assessments,
)

router = APIRouter(prefix='/assessments', tags=['Assessments'])


class AssessmentExecuteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    registro_id: int = Field(strict=True, gt=0, le=2147483647)
    instrumento: str = Field(min_length=1, max_length=50)


def sanitized(operation):
    @wraps(operation)
    def run(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except HTTPException:
            raise
        except Exception:
            # No exception text, SQL, answers or identifiers in response/logs.
            raise HTTPException(500, 'Não foi possível processar a avaliação clínica.') from None
    return run


SUMMARY = ('id', 'registro_id', 'paciente_id', 'modulo_id', 'instrumento',
           'score', 'classificacao', 'created_at')
DETAIL = ('id', 'registro_id', 'paciente_id', 'modulo_id', 'instrumento', 'versao',
          'score', 'score_texto', 'classificacao', 'classificacao_codigo', 'conduta',
          'interpretacao', 'resultado', 'engine_version', 'profissional_id',
          'status', 'executado_em', 'created_at')


def serialize(row, fields=DETAIL):
    result = {field: getattr(row, field) for field in fields}
    result['score'] = float(row.score) if row.score is not None else None
    return result


@router.post('/execute')
@sanitized
def executar_assessment(payload: AssessmentExecuteRequest, db: Session = Depends(get_db),
                         usuario=Depends(get_usuario_atual)):
    try:
        with db.no_autoflush:
            execution_access(db, usuario, payload.registro_id, payload.instrumento)
        result = executar_avaliacao_por_registro(db=db, registro_id=payload.registro_id,
                                                instrumento=payload.instrumento, commit=False)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get('/registro/{registro_id}')
@sanitized
def obter_assessment_por_registro(registro_id: int = Path(gt=0, le=2147483647),
                                  db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    with db.no_autoflush:
        record_access(db, usuario, registro_id)
        row = db.scalars(valid_assessments().where(Assessment.registro_id == registro_id)
                         .order_by(Assessment.id.desc()).limit(1)).first()
        if row is None:
            raise unavailable()
        return serialize(row)


@router.get('/paciente/{paciente_id}')
@sanitized
def listar_assessments_paciente(paciente_id: int = Path(gt=0, le=2147483647),
                                db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    with db.no_autoflush:
        modules = permitted_modules(db, usuario, paciente_id)
        rows = db.scalars(valid_assessments().where(Assessment.paciente_id == paciente_id,
                         Assessment.modulo_id.in_(modules)).order_by(Assessment.created_at.desc()))
        return [serialize(row, SUMMARY) for row in rows]


@router.get('/{assessment_id}')
@sanitized
def obter_assessment(assessment_id: int = Path(gt=0, le=2147483647),
                      db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    with db.no_autoflush:
        row = assessment_access(db, usuario, assessment_id)
        if row is None:
            raise unavailable()
        return serialize(row)
