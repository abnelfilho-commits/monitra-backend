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
from app.services.cardiometabolico_engine import (
    calcular_score,
    classificar_risco,
    definir_protocolo,
    gerar_leitura_clinica,
)

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
    if not validar_vinculo_ativo(db, responsavel.id, paciente_id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado a este paciente.")

    paciente = (
        db.query(Paciente)
        .filter(Paciente.id == paciente_id, Paciente.ativo == True)
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
              AND origem = 'RESPONSAVEL'
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

    dados_motor = {
        "glicemia_jejum": payload.glicemia_jejum,
        "pressao_sistolica": payload.pressao_sistolica,
        "pressao_diastolica": payload.pressao_diastolica,
        "peso": payload.peso,
        "atividade_fisica": None,
        "humor": payload.humor,
        "sono": payload.sono,
    }

    score = calcular_score(dados_motor)
    risco = classificar_risco(score)
    protocolo = definir_protocolo(score)
    leitura_clinica = gerar_leitura_clinica(dados_motor, score)

    formulario = db.execute(
        text("""
            SELECT id
            FROM formularios_modulo
            WHERE modulo_id = 2
            AND tipo = 'REGISTRO_DIARIO'
            AND ativo = true
            ORDER BY id
            LIMIT 1
        """)
    ).fetchone()

    if not formulario:
        raise HTTPException(
            status_code=400,
            detail="Formulário cardiometabólico não configurado."
        )

    registro = db.execute(
        text("""
            INSERT INTO registros_longitudinais (
                paciente_id,
                modulo_id,
                formulario_id,
                origem,
                data_registro,
                modulo,
                glicemia_jejum,
                pressao_sistolica,
                pressao_diastolica,
                peso,
                sono,
                humor,
                observacoes,
                score_clinico,
                risco,
                protocolo,
                leitura_clinica,
                criado_por_responsavel_id
            )
            VALUES (
                :paciente_id,
                2,
                :formulario_id,
                'RESPONSAVEL',
                :data_registro,
                'cardiometabolico',
                :glicemia_jejum,
                :pressao_sistolica,
                :pressao_diastolica,
                :peso,
                :sono,
                :humor,
                :observacoes,
                :score_clinico,
                :risco,
                :protocolo,
                :leitura_clinica,
                :responsavel_id
            )
            RETURNING id
        """),
        {
            "paciente_id": paciente_id,
            "formulario_id": formulario.id,
            "data_registro": payload.data,
            "glicemia_jejum": payload.glicemia_jejum,
            "pressao_sistolica": payload.pressao_sistolica,
            "pressao_diastolica": payload.pressao_diastolica,
            "peso": payload.peso,
            "sono": payload.sono,
            "humor": payload.humor,
            "observacoes": payload.observacoes,
            "score_clinico": score,
            "risco": risco,
            "protocolo": protocolo,
            "leitura_clinica": leitura_clinica,
            "responsavel_id": responsavel.id,
        }
    ).fetchone()

    campos = {
        "glicemia_jejum": payload.glicemia_jejum,
        "pressao_sistolica": payload.pressao_sistolica,
        "pressao_diastolica": payload.pressao_diastolica,
        "peso": payload.peso,
        "sono": payload.sono,
        "humor": payload.humor,
    }

    for nome_campo, valor in campos.items():
        if valor is None:
            continue

        campo = db.execute(
            text("""
                SELECT id
                FROM campos_formulario
                WHERE nome_campo = :nome_campo
                LIMIT 1
            """),
            {"nome_campo": nome_campo}
        ).fetchone()

        if not campo:
            continue

        if isinstance(valor, (int, float)):
            db.execute(
                text("""
                    INSERT INTO respostas_registro (
                        registro_id,
                        campo_id,
                        valor_numero
                    )
                    VALUES (
                        :registro_id,
                        :campo_id,
                        :valor
                    )
                """),
                {
                    "registro_id": registro.id,
                    "campo_id": campo.id,
                    "valor": valor,
                }
            )
        else:
            db.execute(
                text("""
                    INSERT INTO respostas_registro (
                        registro_id,
                        campo_id,
                        valor_texto
                    )
                    VALUES (
                        :registro_id,
                        :campo_id,
                        :valor
                    )
                """),
                {
                    "registro_id": registro.id,
                    "campo_id": campo.id,
                    "valor": str(valor),
                }
            )

    db.commit()

    return {
        "message": "Registro cardiometabólico criado com sucesso.",
        "registro_id": registro.id,
        "score_clinico": score,
        "risco": risco,
        "protocolo": protocolo,
        "leitura_clinica": leitura_clinica,
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
                observacoes
            FROM registros_longitudinais
            WHERE paciente_id = :paciente_id
              AND modulo_id = 2
              AND origem = 'RESPONSAVEL'
            ORDER BY data_registro DESC
        """),
        {
            "paciente_id": paciente_id
        }
    ).mappings().all()

    return [dict(r) for r in registros]