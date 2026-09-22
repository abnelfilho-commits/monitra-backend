from app.services import cardio_longitudinal
from app.services.cardio_evolution import evolution
from fastapi import Query
from app.services.care_lines.access import authorized_patient
from datetime import date as clinical_date
from app.services.daily_record import ActorRef, ActorType, DailyRecordSubmission
from app.services.daily_record.adapters import call_write
from app.services.daily_record.providers.cardio import NUMERIC, TEXT
from app.services.care_lines import CareOrigin
from app.services.interventions import InterventionService, InterventionSubmission
from app.services.interventions.models import SourceType
from app.services.interventions.http import call as intervention_call, cardio_response


from datetime import datetime
from fastapi import HTTPException, APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.core.acl import is_admin_global

from app.database import get_db
from app.schemas.cardiometabolico import (
    RegistroDiarioCardio,
    IntervencaoCreate,
)


router = APIRouter(
    prefix="/cardiometabolico",
    tags=["Cardiometabólico"]
)

intervention_service = InterventionService()


@router.get("/pacientes/{paciente_id}")
def obter_paciente_cardiometabolico(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    return cardio_longitudinal.patient_detail(db, usuario, paciente_id)

@router.get("/pacientes/{paciente_id}/dashboard")
def dashboard_paciente_cardiometabolico(paciente_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return cardio_longitudinal.patient_detail(db, usuario, paciente_id)


@router.get("/pacientes")
def listar_pacientes_cardiometabolico(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return cardio_longitudinal.population(db, usuario)


@router.get("/pacientes/{paciente_id}/evolucao")
def evolucao_cardiometabolica(paciente_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    _, line = authorized_patient(db, usuario, paciente_id, 'CARDIO')
    return evolution(db, [paciente_id], line.module_id)


@router.get("/pacientes/{paciente_id}/timeline")
def timeline_cardiometabolica(paciente_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return cardio_longitudinal.patient_timeline(db, usuario, paciente_id)


@router.get("/dashboard")
def dashboard_cardiometabolico(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return cardio_longitudinal.cockpit(db, usuario)['indicadores']


@router.get("/dashboard-analytics")
def dashboard_analytics(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual),
                        offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return cardio_longitudinal.cockpit(db, usuario, offset, limit)


@router.get("/alertas")
def alertas_cardiometabolico(
    db: Session = Depends(get_db)
    ):
    rows = db.execute(text("""
        SELECT
            p.id,
            p.nome,

            MAX(
                CASE
                    WHEN c.nome_campo = 'glicemia_jejum'
                    THEN r.valor_numero
                END
            ) AS glicemia,

            MAX(
                CASE
                    WHEN c.nome_campo = 'pressao_sistolica'
                    THEN r.valor_numero
                END
            ) AS sistolica,

            MAX(
                CASE
                    WHEN c.nome_campo = 'peso'
                    THEN r.valor_numero
                END
            ) AS peso,

            MAX(
                CASE
                    WHEN c.nome_campo = 'altura'
                    THEN r.valor_numero
                END
            ) AS altura

        FROM pacientes p

        JOIN registros_longitudinais rl
          ON rl.paciente_id = p.id

        JOIN respostas_registro r
          ON r.registro_id = rl.id

        JOIN campos_formulario c
          ON c.id = r.campo_id

        JOIN modulos_clinicos m
          ON m.id = rl.modulo_id

        WHERE m.slug = 'cardiometabolico'

        GROUP BY p.id, p.nome
    """)).fetchall()

    alertas = []

    for row in rows:
        glicemia = row.glicemia or 0
        sistolica = row.sistolica or 0

        peso = row.peso or 0
        altura = row.altura or 0

        imc = 0

        if peso and altura:
            imc = round(
                peso / (altura * altura),
                1
            )

        if glicemia >= 250:

            alertas.append({
                "tipo": "glicemia_critica",
                "paciente_id": row.id,
                "paciente": row.nome,
                "mensagem":
                    "Glicemia criticamente elevada.",
                "gravidade": "alta"
            })

        if sistolica >= 180:

            alertas.append({
                "tipo": "hipertensao_severa",
                "paciente_id": row.id,
                "paciente": row.nome,
                "mensagem":
                    "Hipertensão severa identificada.",
                "gravidade": "alta"
            })

        if imc >= 40:

            alertas.append({
                "tipo": "obesidade_morbida",
                "paciente_id": row.id,
                "paciente": row.nome,
                "mensagem":
                    "Obesidade mórbida identificada.",
                "gravidade": "moderada"
            })

    return {
        "total_alertas": len(alertas),
        "alertas": alertas
    }

@router.post("/registro-diario")
def criar_registro_diario(
    payload: RegistroDiarioCardio,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
    ):
    authorized_patient(db, usuario, payload.paciente_id, 'CARDIO', write=True)
    # Preserve approved structured fields and the independent complementary narrative.
    values = {name: getattr(payload, name) for name in NUMERIC | TEXT | {'observacoes'}}
    submission = DailyRecordSubmission(payload.paciente_id, 'CARDIO', clinical_date.today(),
        CareOrigin.PROFISSIONAL, ActorRef(ActorType.PROFESSIONAL, usuario.id), values)
    result = call_write(db, submission)
    return {"message": "Registro diário criado com sucesso.", "registro_id": result.record_id}

@router.get("/mapa-risco")
def mapa_risco_cardiometabolico(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    return cardio_longitudinal.risk_map(db, usuario)


@router.post("/pacientes/{paciente_id}/intervencoes")
def criar_intervencao(paciente_id: int, payload: IntervencaoCreate,
                     db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    intervention_call(lambda: intervention_service.create(db, InterventionSubmission(
        paciente_id, 'CARDIO', ActorRef(ActorType.PROFESSIONAL, usuario.id),
        payload.tipo, payload.descricao, payload={'priority': payload.prioridade}), user=usuario))
    return {"success": True}


@router.get("/pacientes/{paciente_id}/intervencoes")
def listar_intervencoes(paciente_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return [cardio_response(r) for r in intervention_call(lambda: intervention_service.list_for_patient(
        db, paciente_id, user=usuario, source_type=SourceType.CARDIO_INTERVENTION, requested_care_line="CARDIO"))]
