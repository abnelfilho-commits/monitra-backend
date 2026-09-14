from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models.agenda_cuidado import AgendaCuidado
from app.models.sessao_assistencial import SessaoAssistencial
from app.schemas.agenda_cuidado import (AgendaCuidadoCreate, AgendaCuidadoUpdate,
    AgendaCuidadoResponse, AgendaFrequenciaUpdate)
from app.services.care_plan_service import CarePlanService, call

router = APIRouter(prefix="/agenda-cuidados", tags=["Agenda de Cuidados"])
service = CarePlanService()

def montar_response_agenda(
    item: AgendaCuidado,
    db: Session,
):
    sessoes_geradas = (
        db.query(SessaoAssistencial.id)
        .filter(
            SessaoAssistencial.agenda_cuidado_id == item.id
        )
        .count()
    )

    return {
        "id": item.id,
        "pts_id": item.pts_id,
        "objetivo_id": item.objetivo_id,

        "atividade_id": item.atividade_id,
        "ocupacao_id": item.ocupacao_id,

        "atividade_nome":
            item.atividade.nome
            if item.atividade else None,

        "ocupacao_nome":
            item.ocupacao.nome
            if item.ocupacao else None,

        "frequencia_semanal":
            item.frequencia_semanal,

        "duracao_minutos":
            item.duracao_minutos,

        "data_inicio":
            item.data_inicio,

        "data_fim":
            item.data_fim,

        "status":
            item.status,

        "status_execucao":
            item.status_execucao,

        "data_realizacao":
            item.data_realizacao,

        "observacao_execucao":
            item.observacao_execucao,

        "observacoes":
            item.observacoes,

        "profissional_id":
            item.profissional_id,

        "profissional_nome":
            item.profissional.nome
            if item.profissional else None,

        "quantidade_sessoes":
            item.quantidade_sessoes,
            
        "cronograma_confirmado":
            sessoes_geradas > 0,

        "sessoes_geradas":
            sessoes_geradas,

        "created_at":
            item.created_at,
    }


@router.get("/objetivo/{objetivo_id}", response_model=list[AgendaCuidadoResponse])
def listar_agenda_objetivo(objetivo_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    rows = call(lambda: service.list_agendas(db, objetivo_id, usuario))
    return [montar_response_agenda(row, db) for row in rows]

@router.post("/", response_model=AgendaCuidadoResponse)
def criar_agenda_cuidado(payload: AgendaCuidadoCreate, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    row = call(lambda: service.create_agenda(db, payload, usuario))
    return montar_response_agenda(row, db)

@router.put("/{agenda_id}", response_model=AgendaCuidadoResponse)
def atualizar_agenda_cuidado(agenda_id: int, payload: AgendaCuidadoUpdate,
                            db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    row = call(lambda: service.update_agenda(db, agenda_id, payload, usuario))
    return montar_response_agenda(row, db)

@router.delete("/{agenda_id}")
def excluir_agenda_cuidado(agenda_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    call(lambda: service.delete_agenda(db, agenda_id, usuario))
    return {"message": "Agenda removida com sucesso."}

@router.patch("/{agenda_id}/frequencia", response_model=AgendaCuidadoResponse)
def registrar_frequencia(agenda_id: int, payload: AgendaFrequenciaUpdate,
                         db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    # Preserve legacy replacement (including omitted optional fields becoming null).
    update = AgendaCuidadoUpdate(**payload.model_dump())
    row = call(lambda: service.update_agenda(db, agenda_id, update, usuario))
    return montar_response_agenda(row, db)
