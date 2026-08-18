from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.responsavel_paciente import ResponsavelPaciente
from app.services.registros_longitudinais import (
    criar_registro_longitudinal,
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


class ResponsavelRegistroService:

    @staticmethod
    def validar_vinculo(
        db: Session,
        responsavel_id: int,
        paciente_id: int,
    ):
        vinculo = (
            db.query(ResponsavelPaciente)
            .filter(
                ResponsavelPaciente.responsavel_id
                == responsavel_id,
                ResponsavelPaciente.paciente_id
                == paciente_id,
                ResponsavelPaciente.ativo.is_(True),
            )
            .first()
        )

        if not vinculo:
            raise ValueError(
                "Responsável não possui vínculo ativo "
                "com este paciente."
            )

        return vinculo

    @staticmethod
    def criar_registro_neuro(
        db: Session,
        responsavel_id: int,
        paciente_id: int,
        data_registro: date,
        respostas: dict,
    ):
        # ---------------------------------------------
        # Validar vínculo
        # ---------------------------------------------

        ResponsavelRegistroService.validar_vinculo(
            db=db,
            responsavel_id=responsavel_id,
            paciente_id=paciente_id,
        )

        # ---------------------------------------------
        # Validar paciente
        # ---------------------------------------------

        paciente = (
            db.query(Paciente)
            .filter(
                Paciente.id == paciente_id,
                Paciente.ativo.is_(True),
            )
            .first()
        )

        if not paciente:
            raise ValueError(
                "Paciente não encontrado."
            )

        # ---------------------------------------------
        # Validar data
        # ---------------------------------------------

        hoje = date.today()

        if (
            data_registro < hoje - timedelta(days=1)
            or data_registro > hoje
        ):
            raise ValueError(
                "A data do registro deve ser hoje ou ontem."
            )

        # ---------------------------------------------
        # Impedir duplicidade
        # ---------------------------------------------

        existente = db.execute(
            text(
                """
                SELECT id
                FROM registros_longitudinais
                WHERE paciente_id = :paciente_id
                  AND modulo_id = :modulo_id
                  AND formulario_id = :formulario_id
                  AND data_registro = :data_registro
                  AND origem = 'RESPONSAVEL'
                LIMIT 1
                """
            ),
            {
                "paciente_id": paciente_id,
                "modulo_id": MODULO_NEURO_ID,
                "formulario_id":
                    FORMULARIO_REGISTRO_NEURO_ID,
                "data_registro": data_registro,
            },
        ).fetchone()

        if existente:
            raise ValueError(
                "Já existe um acompanhamento enviado "
                "para esta data."
            )

        # ---------------------------------------------
        # Montar respostas longitudinais
        # ---------------------------------------------

        respostas_longitudinais = []

        for nome_campo, campo_id in (
            CAMPOS_REGISTRO_NEURO.items()
        ):
            respostas_longitudinais.append(
                SimpleNamespace(
                    campo_id=campo_id,
                    valor=respostas.get(nome_campo),
                )
            )

        payload = SimpleNamespace(
            paciente_id=paciente_id,
            modulo_id=MODULO_NEURO_ID,
            formulario_id=
                FORMULARIO_REGISTRO_NEURO_ID,
            data_registro=data_registro,
            origem="RESPONSAVEL",
            respostas=respostas_longitudinais,
        )

        registro = criar_registro_longitudinal(
            db=db,
            payload=payload,
        )

        return registro