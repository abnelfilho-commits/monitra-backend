from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.usuario import Usuario
from app.services.cockpit_profissional_service import (
    CockpitProfissionalService,
)

from app.services.cockpit_gestao_service import CockpitGestaoService

router = APIRouter(
    prefix="/cockpit",
    tags=["Cockpit"],
)
    
@router.get("/profissional")
def obter_cockpit_profissional(
    care_line: str = Query(..., min_length=1),
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    return CockpitProfissionalService.get_cockpit(db, usuario, care_line, offset, limit)

@router.get("/gestao")
def obter_cockpit_gestao(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if usuario.perfil not in ("ADMIN", "ADMIN_CLINICA"):
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito a administradores.",
        )

    analises_clinicas = CockpitGestaoService.obter_analises_clinicas(
        db=db,
        usuario=usuario,
    )

    resumo = CockpitGestaoService.obter_resumo(
        db=db,
        usuario=usuario,
        analises_clinicas=analises_clinicas,
    )

    eventos_recentes = CockpitGestaoService.obter_eventos_recentes(
        db=db,
        usuario=usuario,
        limit=10,
    )

    continuidade_longitudinal = (
        CockpitGestaoService.obter_continuidade_longitudinal(
            db=db,
            usuario=usuario,
        )
    )

    estrutura_operacao = CockpitGestaoService.obter_estrutura_operacao(
        db=db,
        usuario=usuario,
        analises_clinicas=analises_clinicas,
        continuidade_longitudinal=continuidade_longitudinal,
        periodo_dias=30,
    )

    acompanhamento = CockpitGestaoService.obter_acompanhamento_ativo(
        db=db,
        usuario=usuario,
        periodo_dias=30,
    )

    atividade_assistencial = CockpitGestaoService.obter_atividade_assistencial(
        db=db,
        usuario=usuario,
        periodo_dias=30,
    )

    atencao_necessaria = CockpitGestaoService.obter_atencao_necessaria(
        db=db,
        usuario=usuario,
        analises_clinicas=analises_clinicas,
        continuidade_longitudinal=continuidade_longitudinal,
    )
    
    profissionais_ativos = CockpitGestaoService.obter_profissionais_ativos(
        db=db,
        usuario=usuario,
    )

    cockpit_v2 = CockpitGestaoService.montar_cockpit_v2(
        usuario=usuario,
        resumo=resumo,
        continuidade_longitudinal=continuidade_longitudinal,
        acompanhamento=acompanhamento,
        atencao_necessaria=atencao_necessaria,
        atividade_assistencial=atividade_assistencial,
        estrutura_operacao=estrutura_operacao,
        eventos_recentes=eventos_recentes,
        profissionais_ativos=profissionais_ativos,
    )

    return {
        **resumo,
        "eventos_recentes": eventos_recentes,
        "continuidade_longitudinal": continuidade_longitudinal,
        "acompanhamento": acompanhamento,
        "atencao_necessaria": atencao_necessaria,
        "atividade_assistencial": atividade_assistencial,
        "estrutura_operacao": estrutura_operacao,
        "cockpit_v2": cockpit_v2,
    }