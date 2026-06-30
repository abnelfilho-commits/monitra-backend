from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.services.clinical_engine.assessment_service import executar_avaliacao_por_registro

router = APIRouter(
    prefix="/assessments",
    tags=["Assessments"]
)


class AssessmentExecuteRequest(BaseModel):
    registro_id: int
    instrumento: str


@router.post("/execute")
def executar_assessment(
    payload: AssessmentExecuteRequest,
    db: Session = Depends(get_db)
):
    try:
        return executar_avaliacao_por_registro(
            db=db,
            registro_id=payload.registro_id,
            instrumento=payload.instrumento
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao executar avaliação clínica: {str(e)}"
        )
        
@router.get("/registro/{registro_id}")
def obter_assessment_por_registro(
    registro_id: int,
    db: Session = Depends(get_db)
):
    avaliacao = db.execute(text("""
        SELECT
            id,
            registro_id,
            paciente_id,
            modulo_id,
            instrumento,
            versao,
            score,
            score_texto,
            classificacao,
            classificacao_codigo,
            conduta,
            interpretacao,
            resultado,
            engine_version,
            profissional_id,
            status,
            executado_em,
            created_at
        FROM avaliacoes_clinicas
        WHERE registro_id = :registro_id
        ORDER BY id DESC
        LIMIT 1
    """), {
        "registro_id": registro_id
    }).fetchone()

    if not avaliacao:
        raise HTTPException(
            status_code=404,
            detail="Avaliação clínica não encontrada para este registro."
        )

    return {
        "id": avaliacao.id,
        "registro_id": avaliacao.registro_id,
        "paciente_id": avaliacao.paciente_id,
        "modulo_id": avaliacao.modulo_id,
        "instrumento": avaliacao.instrumento,
        "versao": avaliacao.versao,
        "score": float(avaliacao.score) if avaliacao.score is not None else None,
        "score_texto": avaliacao.score_texto,
        "classificacao": avaliacao.classificacao,
        "classificacao_codigo": avaliacao.classificacao_codigo,
        "conduta": avaliacao.conduta,
        "interpretacao": avaliacao.interpretacao,
        "resultado": avaliacao.resultado,
        "engine_version": avaliacao.engine_version,
        "profissional_id": avaliacao.profissional_id,
        "status": avaliacao.status,
        "executado_em": avaliacao.executado_em,
        "created_at": avaliacao.created_at,
    }
    
@router.get("/paciente/{paciente_id}")
def listar_assessments_paciente(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    avaliacoes = db.execute(text("""
        SELECT
            id,
            registro_id,
            paciente_id,
            modulo_id,
            instrumento,
            score,
            classificacao,
            created_at
        FROM avaliacoes_clinicas
        WHERE paciente_id = :paciente_id
        ORDER BY created_at DESC
    """), {
        "paciente_id": paciente_id
    }).fetchall()

    return [
        {
            "id": a.id,
            "registro_id": a.registro_id,
            "paciente_id": a.paciente_id,
            "modulo_id": a.modulo_id,
            "instrumento": a.instrumento,
            "score": float(a.score) if a.score is not None else None,
            "classificacao": a.classificacao,
            "created_at": a.created_at,
        }
        for a in avaliacoes
    ]
    
@router.get("/{assessment_id}")
def obter_assessment(
    assessment_id: int,
    db: Session = Depends(get_db)
):
    avaliacao = db.execute(text("""
        SELECT
            id,
            registro_id,
            paciente_id,
            modulo_id,
            instrumento,
            versao,
            score,
            score_texto,
            classificacao,
            classificacao_codigo,
            conduta,
            interpretacao,
            resultado,
            engine_version,
            profissional_id,
            status,
            executado_em,
            created_at
        FROM avaliacoes_clinicas
        WHERE id = :assessment_id
        LIMIT 1
    """), {
        "assessment_id": assessment_id
    }).fetchone()

    if not avaliacao:
        raise HTTPException(
            status_code=404,
            detail="Avaliação clínica não encontrada."
        )

    return {
        "id": avaliacao.id,
        "registro_id": avaliacao.registro_id,
        "paciente_id": avaliacao.paciente_id,
        "modulo_id": avaliacao.modulo_id,
        "instrumento": avaliacao.instrumento,
        "versao": avaliacao.versao,
        "score": float(avaliacao.score) if avaliacao.score is not None else None,
        "score_texto": avaliacao.score_texto,
        "classificacao": avaliacao.classificacao,
        "classificacao_codigo": avaliacao.classificacao_codigo,
        "conduta": avaliacao.conduta,
        "interpretacao": avaliacao.interpretacao,
        "resultado": avaliacao.resultado,
        "engine_version": avaliacao.engine_version,
        "profissional_id": avaliacao.profissional_id,
        "status": avaliacao.status,
        "executado_em": avaliacao.executado_em,
        "created_at": avaliacao.created_at,
    }