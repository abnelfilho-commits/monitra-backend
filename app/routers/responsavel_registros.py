from app.services.daily_record import ActorRef, ActorType, DailyRecordSubmission
from app.services.daily_record.adapters import call_write
from app.services.daily_record.providers.neuro import FIELDS
from app.services.care_lines import CareOrigin
from app.models.modular import RegistroLongitudinal
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.responsavel import Responsavel
from app.models.responsavel_paciente import ResponsavelPaciente
from app.models.paciente import Paciente
from app.core.deps import get_responsavel_atual
from app.schemas.registro import (
    RegistroDiarioResponsavelCreate,
)
from app.services.registros_longitudinais import criar_registro_longitudinal


router = APIRouter(
    prefix="/responsavel",
    tags=["App Responsável - Registros"]
)


MODULO_NEURO_ID = 1
FORMULARIO_REGISTRO_NEURO_ID = 2

CAMPOS_REGISTRO_NEURO = {
    "sono_qualidade": 34,
    "irritabilidade": 35,
    "crise_sensorial": 36,
    "tempo_tela": 37,
    "seletividade_alimentar": 38,
    "aceitou_alimento_novo": 39,
    "observacao": 40,
    "evacuacao": 41,
    "consistencia_fezes": 42,
}


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


def montar_respostas(payload: RegistroDiarioResponsavelCreate):
    valores = {
        "sono_qualidade": payload.sono_qualidade,
        "evacuacao": payload.evacuacao,
        "consistencia_fezes": payload.consistencia_fezes,
        "irritabilidade": payload.irritabilidade,
        "crise_sensorial": payload.crise_sensorial,
        "tempo_tela": payload.tempo_tela,
        "seletividade_alimentar": payload.seletividade_alimentar,
        "aceitou_alimento_novo": payload.aceitou_alimento_novo,
        "observacao": payload.observacao,
    }

    return [
        SimpleNamespace(
            campo_id=CAMPOS_REGISTRO_NEURO[nome_campo],
            valor=valor,
        )
        for nome_campo, valor in valores.items()
    ]


def extrair_respostas_registro(db: Session, registro_id: int):
    rows = db.execute(text("""
        SELECT
            cf.nome_campo,
            rr.valor_texto,
            rr.valor_numero,
            rr.valor_booleano,
            rr.valor_data,
            rr.valor_hora,
            rr.valor_json
        FROM respostas_registro rr
        JOIN campos_formulario cf
            ON cf.id = rr.campo_id
        WHERE rr.registro_id = :registro_id
    """), {
        "registro_id": registro_id
    }).fetchall()

    respostas = {}

    for row in rows:
        valor = None

        if row.valor_booleano is not None:
            valor = row.valor_booleano
        elif row.valor_numero is not None:
            valor = int(row.valor_numero) if row.valor_numero == int(row.valor_numero) else float(row.valor_numero)
        elif row.valor_texto is not None:
            valor = row.valor_texto
        elif row.valor_data is not None:
            valor = row.valor_data
        elif row.valor_hora is not None:
            valor = row.valor_hora
        elif row.valor_json is not None:
            valor = row.valor_json

        respostas[row.nome_campo] = valor

    return respostas


def montar_response_registro(row, respostas):
    return {
        "id": row.id,
        "paciente_id": row.paciente_id,
        "data": row.data_registro,
        "sono_qualidade": respostas.get("sono_qualidade"),
        "evacuacao": respostas.get("evacuacao"),
        "consistencia_fezes": respostas.get("consistencia_fezes"),
        "irritabilidade": respostas.get("irritabilidade"),
        "crise_sensorial": respostas.get("crise_sensorial"),
        "tempo_tela": respostas.get("tempo_tela"),
        "seletividade_alimentar": respostas.get("seletividade_alimentar"),
        "aceitou_alimento_novo": respostas.get("aceitou_alimento_novo"),
        "observacao": respostas.get("observacao"),
        "origem": row.origem,
        "responsavel_id": row.criado_por_responsavel_id,
        "criado_por_tipo": "RESPONSAVEL",
        "criado_por_id": row.criado_por_responsavel_id,
        "created_at": row.criado_em,
    }


@router.get("/pacientes/{paciente_id}/registros")
def listar_registros_meu_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    if not validar_vinculo_ativo(db, responsavel.id, paciente_id):
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado a este paciente."
        )

    registros = db.execute(text("""
        SELECT
            id,
            paciente_id,
            data_registro,
            origem,
            criado_por_responsavel_id,
            criado_em
        FROM registros_longitudinais
        WHERE paciente_id = :paciente_id
          AND modulo_id = :modulo_id
          AND formulario_id = :formulario_id
          AND origem IN ('RESPONSAVEL', 'RESPONSAVEL_APP', 'RESPONSAVEL_WHATSAPP')
        ORDER BY data_registro DESC, id DESC
    """), {
        "paciente_id": paciente_id,
        "modulo_id": MODULO_NEURO_ID,
        "formulario_id": FORMULARIO_REGISTRO_NEURO_ID,
    }).fetchall()

    resultado = []

    for registro in registros:
        respostas = extrair_respostas_registro(db, registro.id)
        resultado.append(
            montar_response_registro(registro, respostas)
        )

    return resultado


@router.post("/pacientes/{paciente_id}/registros")
def criar_registro_meu_paciente(
    paciente_id: int,
    payload: RegistroDiarioResponsavelCreate,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    if not validar_vinculo_ativo(db, responsavel.id, paciente_id):
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado a este paciente."
        )

    paciente = (
        db.query(Paciente)
        .filter(
            Paciente.id == paciente_id,
            Paciente.ativo == True,
        )
        .with_for_update()
        .first()
    )

    if not paciente:
        raise HTTPException(
            status_code=404,
            detail="Paciente não encontrado."
        )

    hoje = date.today()

    if payload.data < (hoje - timedelta(days=1)) or payload.data > hoje:
        raise HTTPException(
            status_code=400,
            detail="A data do registro deve ser hoje ou ontem."
        )

    submission = DailyRecordSubmission(
        paciente_id, 'NEURO', payload.data, CareOrigin.RESPONSAVEL_APP,
        ActorRef(ActorType.RESPONSIBLE, responsavel.id),
        {name: getattr(payload, name) for name in FIELDS},
    )
    result = call_write(db, submission)
    registro = db.query(RegistroLongitudinal).filter(RegistroLongitudinal.id == result.record_id).one()

    respostas = extrair_respostas_registro(db, registro.id)

    return montar_response_registro(registro, respostas)


@router.get("/registros/{registro_id}")
def obter_registro(
    registro_id: int,
    db: Session = Depends(get_db),
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    registro = db.execute(text("""
        SELECT
            id,
            paciente_id,
            data_registro,
            origem,
            criado_por_responsavel_id,
            criado_em
        FROM registros_longitudinais
        WHERE id = :registro_id
          AND modulo_id = :modulo_id
          AND formulario_id = :formulario_id
          AND origem IN ('RESPONSAVEL', 'RESPONSAVEL_APP', 'RESPONSAVEL_WHATSAPP')
        LIMIT 1
    """), {
        "registro_id": registro_id,
        "modulo_id": MODULO_NEURO_ID,
        "formulario_id": FORMULARIO_REGISTRO_NEURO_ID,
    }).fetchone()

    if not registro:
        raise HTTPException(
            status_code=404,
            detail="Registro não encontrado."
        )

    if not validar_vinculo_ativo(db, responsavel.id, registro.paciente_id):
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado a este registro."
        )

    respostas = extrair_respostas_registro(db, registro.id)

    return montar_response_registro(registro, respostas)