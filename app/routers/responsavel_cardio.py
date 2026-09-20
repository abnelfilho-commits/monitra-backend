from app.services.daily_record.concurrency import lock_context
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.responsavel import Responsavel
from app.models.responsavel_paciente import ResponsavelPaciente
from app.models.paciente import Paciente
from app.core.deps import get_responsavel_atual
from app.schemas.responsavel_cardio import RegistroCardioResponsavelCreate
from app.services.daily_record import DailyRecordSubmission, ActorRef, ActorType
from app.services.daily_record.adapters import call_write
from app.services.care_lines import CareOrigin


router = APIRouter(
    prefix="/responsavel",
    tags=["App Responsável - Cardio"]
)


def validar_vinculo_ativo(db: Session, responsavel_id: int, paciente_id: int):
    vinculo = (
        db.query(ResponsavelPaciente)
        .filter(
            ResponsavelPaciente.responsavel_id == responsavel_id,
            ResponsavelPaciente.paciente_id == paciente_id,
            ResponsavelPaciente.ativo == True,
        )
        .first()
    )
    return vinculo is not None


@router.post("/pacientes/{paciente_id}/registros-cardio")
def criar_registro_cardio_responsavel(
    paciente_id: int,
    payload: RegistroCardioResponsavelCreate,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    lock_context(db, paciente_id, responsavel.id)
    if not validar_vinculo_ativo(db, responsavel.id, paciente_id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado a este paciente.")

    paciente = (
        db.query(Paciente)
        .filter(Paciente.id == paciente_id, Paciente.ativo == True)
        .populate_existing()
        .first()
    )

    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    hoje = date.today()

    if payload.data < (hoje - timedelta(days=1)) or payload.data > hoje:
        raise HTTPException(
            status_code=400,
            detail="A data do registro deve ser hoje ou ontem."
        )

    existente = db.execute(
        text("""
            SELECT id
            FROM registros_longitudinais
            WHERE paciente_id = :paciente_id
              AND data_registro = :data_registro
              AND origem IN ('RESPONSAVEL', 'RESPONSAVEL_APP', 'RESPONSAVEL_WHATSAPP')
              AND criado_por_responsavel_id = :responsavel_id
              AND modulo_id = 2
            LIMIT 1
        """),
        {
            "paciente_id": paciente_id,
            "data_registro": payload.data,
            "responsavel_id": responsavel.id,
        }
    ).fetchone()

    if existente:
        raise HTTPException(
            status_code=400,
            detail="Você já enviou um registro cardiometabólico para esta data."
        )

    # The shared provider resolves the active Cardio membership and form, scopes
    # answer fields to that form and persists observations in the approved column.
    values = payload.model_dump(exclude={'data'})
    result = call_write(db, DailyRecordSubmission(paciente_id, 'CARDIO', payload.data,
        CareOrigin.RESPONSAVEL_APP, ActorRef(ActorType.RESPONSIBLE, responsavel.id), values))
    derived = db.execute(text("""SELECT score_clinico, risco, protocolo, leitura_clinica
        FROM registros_longitudinais WHERE id=:id"""), {'id': result.record_id}).mappings().one()

    return {
        "message": "Registro cardiometabólico criado com sucesso.",
        "registro_id": result.record_id,
        "score_clinico": derived["score_clinico"],
        "risco": derived["risco"],
        "protocolo": derived["protocolo"],
        "leitura_clinica": derived["leitura_clinica"],
    }
    
@router.get("/pacientes/{paciente_id}/registros-cardio")
def listar_registros_cardio_responsavel(
    paciente_id: int,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):

    if not validar_vinculo_ativo(
        db,
        responsavel.id,
        paciente_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado."
        )

    registros = db.execute(
        text("""
            SELECT
                id,
                data_registro,
                glicemia_jejum,
                pressao_sistolica,
                pressao_diastolica,
                peso,
                score_clinico,
                risco,
                protocolo,
                leitura_clinica,
                observacoes,
                origem,
                criado_por_responsavel_id
            FROM registros_longitudinais
            WHERE paciente_id = :paciente_id
              AND modulo_id = 2
              AND origem IN ('RESPONSAVEL', 'RESPONSAVEL_APP', 'RESPONSAVEL_WHATSAPP')
            ORDER BY data_registro DESC
        """),
        {
            "paciente_id": paciente_id
        }
    ).mappings().all()

    return [dict(r) for r in registros]