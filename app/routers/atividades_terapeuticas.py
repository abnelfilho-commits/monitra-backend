from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session
from sqlalchemy import func

from typing import Optional

from app.database import get_db
from app.models.atividade_terapeutica import (
    AtividadeTerapeutica,
    OcupacaoProfissional,
    AtividadeOcupacao,
)
from app.schemas.atividade_terapeutica import (
    AtividadeTerapeuticaCreate,
    AtividadeTerapeuticaResponse,
    OcupacaoProfissionalCreate,
    OcupacaoProfissionalResponse,
    AtividadeOcupacaoCreate,
)

router = APIRouter(
    prefix="/atividades-terapeuticas",
    tags=["Atividades Terapêuticas"]
)


@router.get("/", response_model=list[AtividadeTerapeuticaResponse])
def listar_atividades(
    modulo_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = (
        db.query(AtividadeTerapeutica)
        .filter(AtividadeTerapeutica.ativo == True)
    )

    if modulo_id is not None:
        query = query.filter(
            AtividadeTerapeutica.modulo_id == modulo_id
        )

    return (
        query
        .order_by(AtividadeTerapeutica.nome)
        .all()
    )

@router.post("/", response_model=AtividadeTerapeuticaResponse)
def criar_atividade(
    atividade: AtividadeTerapeuticaCreate,
    db: Session = Depends(get_db)
):
    nova_atividade = AtividadeTerapeutica(
        nome=atividade.nome,
        descricao=atividade.descricao,
        duracao_minutos=atividade.duracao_minutos,
        modulo_id=atividade.modulo_id,
        ativo=True
    )
    atividade_existente = (
        db.query(AtividadeTerapeutica)
        .filter(func.lower(AtividadeTerapeutica.nome) == atividade.nome.strip().lower())
        .first()
    )

    if atividade_existente:
        raise HTTPException(
            status_code=400,
            detail="Esta atividade já está cadastrada."
        )
    db.add(nova_atividade)
    db.commit()
    db.refresh(nova_atividade)

    return nova_atividade


@router.get("/ocupacoes-profissionais", response_model=list[OcupacaoProfissionalResponse])
def listar_ocupacoes(db: Session = Depends(get_db)):
    return (
        db.query(OcupacaoProfissional)
        .filter(OcupacaoProfissional.ativo == True)
        .order_by(OcupacaoProfissional.nome)
        .all()
    )


@router.post("/ocupacoes-profissionais", response_model=OcupacaoProfissionalResponse)
def criar_ocupacao(
    ocupacao: OcupacaoProfissionalCreate,
    db: Session = Depends(get_db)
):
    nova_ocupacao = OcupacaoProfissional(
        nome=ocupacao.nome,
        ativo=True
    )
    ocupacao_existente = (
        db.query(OcupacaoProfissional)
        .filter(func.lower(OcupacaoProfissional.nome) == ocupacao.nome.strip().lower())
        .first()
    )

    if ocupacao_existente:
        raise HTTPException(
            status_code=400,
            detail="Esta ocupação já está cadastrada."
        )
    db.add(nova_ocupacao)
    db.commit()
    db.refresh(nova_ocupacao)

    return nova_ocupacao


@router.post("/{atividade_id}/ocupacoes")
def vincular_ocupacao_atividade(
    atividade_id: int,
    vinculo: AtividadeOcupacaoCreate,
    db: Session = Depends(get_db)
):
    atividade = (
        db.query(AtividadeTerapeutica)
        .filter(AtividadeTerapeutica.id == atividade_id)
        .first()
    )

    if not atividade:
        raise HTTPException(
            status_code=404,
            detail="Atividade terapêutica não encontrada."
        )

    ocupacao = (
        db.query(OcupacaoProfissional)
        .filter(OcupacaoProfissional.id == vinculo.ocupacao_id)
        .first()
    )

    if not ocupacao:
        raise HTTPException(
            status_code=404,
            detail="Ocupação profissional não encontrada."
        )

    vinculo_existente = (
        db.query(AtividadeOcupacao)
        .filter(
            AtividadeOcupacao.atividade_id == atividade_id,
            AtividadeOcupacao.ocupacao_id == vinculo.ocupacao_id
        )
        .first()
    )

    if vinculo_existente:
        raise HTTPException(
            status_code=400,
            detail="Esta ocupação já está vinculada a esta atividade."
        )

    novo_vinculo = AtividadeOcupacao(
        atividade_id=atividade_id,
        ocupacao_id=vinculo.ocupacao_id
    )

    db.add(novo_vinculo)
    db.commit()

    return {
        "message": "Ocupação vinculada à atividade com sucesso."
    }

@router.get("/{atividade_id}/ocupacoes", response_model=list[OcupacaoProfissionalResponse])
def listar_ocupacoes_da_atividade(
    atividade_id: int,
    db: Session = Depends(get_db)
):
    atividade = db.query(AtividadeTerapeutica).filter(
        AtividadeTerapeutica.id == atividade_id
    ).first()

    if not atividade:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")

    return (
        db.query(OcupacaoProfissional)
        .join(AtividadeOcupacao, AtividadeOcupacao.ocupacao_id == OcupacaoProfissional.id)
        .filter(AtividadeOcupacao.atividade_id == atividade_id)
        .order_by(OcupacaoProfissional.nome)
        .all()
    )


@router.delete("/{atividade_id}/ocupacoes/{ocupacao_id}")
def remover_ocupacao_da_atividade(
    atividade_id: int,
    ocupacao_id: int,
    db: Session = Depends(get_db)
):
    vinculo = db.query(AtividadeOcupacao).filter(
        AtividadeOcupacao.atividade_id == atividade_id,
        AtividadeOcupacao.ocupacao_id == ocupacao_id
    ).first()

    if not vinculo:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado.")

    db.delete(vinculo)
    db.commit()

    return {"message": "Vínculo removido com sucesso."}
