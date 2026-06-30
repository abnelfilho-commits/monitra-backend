from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from sqlalchemy import text

from app.database import get_db
from app.models.capacidade_instalada import CapacidadeInstalada
from app.models.atividade_terapeutica import OcupacaoProfissional
from app.schemas.capacidade_instalada import (
    CapacidadeInstaladaCreate,
    CapacidadeInstaladaUpdate,
    CapacidadeInstaladaResponse,
)

router = APIRouter(
    prefix="/capacidade-instalada",
    tags=["Capacidade Instalada"]
)


@router.get("/", response_model=list[CapacidadeInstaladaResponse])
def listar_capacidade_instalada(
    modulo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(CapacidadeInstalada).filter(
        CapacidadeInstalada.ativo == True
    )

    if modulo_id is not None:
        query = query.filter(CapacidadeInstalada.modulo_id == modulo_id)

    return query.order_by(CapacidadeInstalada.id.desc()).all()


@router.post("/", response_model=CapacidadeInstaladaResponse)
def criar_capacidade_instalada(
    dados: CapacidadeInstaladaCreate,
    db: Session = Depends(get_db)
):
    ocupacao = (
        db.query(OcupacaoProfissional)
        .filter(OcupacaoProfissional.id == dados.ocupacao_id)
        .first()
    )

    if not ocupacao:
        raise HTTPException(
            status_code=404,
            detail="Ocupação profissional não encontrada."
        )

    existente = (
        db.query(CapacidadeInstalada)
        .filter(
            CapacidadeInstalada.modulo_id == dados.modulo_id,
            CapacidadeInstalada.ocupacao_id == dados.ocupacao_id,
            CapacidadeInstalada.ativo == True,
        )
        .first()
    )

    if existente:
        raise HTTPException(
            status_code=400,
            detail="Já existe capacidade instalada ativa para esta ocupação neste módulo."
        )

    item = CapacidadeInstalada(
        modulo_id=dados.modulo_id,
        ocupacao_id=dados.ocupacao_id,
        quantidade_profissionais=dados.quantidade_profissionais,
        horas_semanais_por_profissional=dados.horas_semanais_por_profissional,
        ativo=True,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


@router.put("/{capacidade_id}", response_model=CapacidadeInstaladaResponse)
def atualizar_capacidade_instalada(
    capacidade_id: int,
    dados: CapacidadeInstaladaUpdate,
    db: Session = Depends(get_db)
):
    item = (
        db.query(CapacidadeInstalada)
        .filter(CapacidadeInstalada.id == capacidade_id)
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Capacidade instalada não encontrada."
        )

    if dados.quantidade_profissionais is not None:
        item.quantidade_profissionais = dados.quantidade_profissionais

    if dados.horas_semanais_por_profissional is not None:
        item.horas_semanais_por_profissional = dados.horas_semanais_por_profissional

    if dados.ativo is not None:
        item.ativo = dados.ativo

    db.commit()
    db.refresh(item)

    return item


@router.delete("/{capacidade_id}")
def excluir_capacidade_instalada(
    capacidade_id: int,
    db: Session = Depends(get_db)
):
    item = (
        db.query(CapacidadeInstalada)
        .filter(CapacidadeInstalada.id == capacidade_id)
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Capacidade instalada não encontrada."
        )

    item.ativo = False

    db.commit()

    return {
        "message": "Capacidade instalada removida com sucesso."
    }
    
@router.get("/demanda-capacidade")
def listar_demanda_capacidade(
    modulo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    resultado = db.execute(text("""
        SELECT
            modulo_id,
            ocupacao_id,
            ocupacao_nome,
            demanda_horas_ano,
            capacidade_horas_ano,
            saldo_horas,
            percentual_utilizacao
        FROM vw_demanda_capacidade
        WHERE (:modulo_id IS NULL OR modulo_id = :modulo_id)
        ORDER BY demanda_horas_ano DESC
    """), {
        "modulo_id": modulo_id
    }).mappings().all()

    return list(resultado)