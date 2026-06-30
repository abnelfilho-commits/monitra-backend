from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db


router = APIRouter(
    prefix="/formularios",
    tags=["Formulários"]
)


@router.get("/{formulario_id}")
def obter_formulario(
    formulario_id: int,
    db: Session = Depends(get_db)
):
    formulario = db.execute(text("""
        SELECT
            id,
            modulo_id,
            nome,
            tipo,
            ativo
        FROM formularios_modulo
        WHERE id = :formulario_id
    """), {
        "formulario_id": formulario_id
    }).fetchone()

    if not formulario:
        raise HTTPException(
            status_code=404,
            detail="Formulário não encontrado."
        )

    campos = db.execute(text("""
        SELECT
            id,
            nome_campo,
            label,
            tipo_campo,
            obrigatorio,
            ordem,
            opcoes,
            regra_exibicao,
            ativo
        FROM campos_formulario
        WHERE formulario_id = :formulario_id
          AND ativo = true
        ORDER BY ordem ASC
    """), {
        "formulario_id": formulario_id
    }).fetchall()

    return {
        "id": formulario.id,
        "modulo_id": formulario.modulo_id,
        "nome": formulario.nome,
        "tipo": formulario.tipo,
        "ativo": formulario.ativo,
        "campos": [
            {
                "id": campo.id,
                "nome_campo": campo.nome_campo,
                "label": campo.label,
                "tipo_campo": campo.tipo_campo,
                "obrigatorio": campo.obrigatorio,
                "ordem": campo.ordem,
                "opcoes": campo.opcoes,
                "regra_exibicao": campo.regra_exibicao,
                "ativo": campo.ativo
            }
            for campo in campos
        ]
    }
    
@router.get("/codigo/{codigo}")
def obter_formulario_por_codigo(
    codigo: str,
    db: Session = Depends(get_db)
):
    formulario = db.execute(text("""
        SELECT
            id,
            codigo,
            modulo_id,
            nome,
            tipo,
            ativo
        FROM formularios_modulo
        WHERE codigo = :codigo
    """), {
        "codigo": codigo.upper()
    }).fetchone()

    if not formulario:
        raise HTTPException(
            status_code=404,
            detail="Formulário não encontrado."
        )

    campos = db.execute(text("""
        SELECT
            id,
            nome_campo,
            label,
            tipo_campo,
            obrigatorio,
            ordem,
            opcoes,
            regra_exibicao,
            ativo
        FROM campos_formulario
        WHERE formulario_id = :formulario_id
          AND ativo = true
        ORDER BY ordem
    """), {
        "formulario_id": formulario.id
    }).fetchall()

    return {
        "id": formulario.id,
        "codigo": formulario.codigo,
        "modulo_id": formulario.modulo_id,
        "nome": formulario.nome,
        "tipo": formulario.tipo,
        "ativo": formulario.ativo,
        "campos": [
            {
                "id": campo.id,
                "nome_campo": campo.nome_campo,
                "label": campo.label,
                "tipo_campo": campo.tipo_campo,
                "obrigatorio": campo.obrigatorio,
                "ordem": campo.ordem,
                "opcoes": campo.opcoes,
                "regra_exibicao": campo.regra_exibicao,
                "ativo": campo.ativo,
            }
            for campo in campos
        ]
    }