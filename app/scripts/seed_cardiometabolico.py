from dotenv import load_dotenv

load_dotenv()

from datetime import date, timedelta
import random

from sqlalchemy import text

from app.database import SessionLocal


db = SessionLocal()


def obter_campo_id(nome_campo):
    row = db.execute(
        text("""
            SELECT id
            FROM campos_formulario
            WHERE nome_campo = :nome
            LIMIT 1
        """),
        {"nome": nome_campo}
    ).fetchone()

    return row.id if row else None


def criar_resposta(registro_id, campo_id, valor):
    if campo_id is None:
        return

    payload = {
        "registro_id": registro_id,
        "campo_id": campo_id,
        "valor_texto": None,
        "valor_numero": None,
        "valor_booleano": None,
    }

    if isinstance(valor, bool):
        payload["valor_booleano"] = valor

    elif isinstance(valor, (int, float)):
        payload["valor_numero"] = valor

    else:
        payload["valor_texto"] = str(valor)

    db.execute(
        text("""
            INSERT INTO respostas_registro (
                registro_id,
                campo_id,
                valor_texto,
                valor_numero,
                valor_booleano
            )
            VALUES (
                :registro_id,
                :campo_id,
                :valor_texto,
                :valor_numero,
                :valor_booleano
            )
        """),
        payload
    )


# IDs fixos
MODULO_ID = 2
FORMULARIO_ID = 1

# Pacientes
PACIENTES = [
    {
        "id": 1,
        "perfil": "diabetes_descompensado",
        "peso_base": 108,
        "altura": 1.72,
        "glicemia_base": 180,
        "pressao_base": 150,
    },
    {
        "id": 2,
        "perfil": "hipertenso_estavel",
        "peso_base": 84,
        "altura": 1.75,
        "glicemia_base": 105,
        "pressao_base": 130,
    },
    {
        "id": 3,
        "perfil": "obesidade_morbida",
        "peso_base": 145,
        "altura": 1.70,
        "glicemia_base": 220,
        "pressao_base": 170,
    },
    {
        "id": 4,
        "perfil": "melhora_clinica",
        "peso_base": 132,
        "altura": 1.73,
        "glicemia_base": 210,
        "pressao_base": 165,
    },
]

# Campos
campos = {
    "glicemia_jejum": obter_campo_id("glicemia_jejum"),
    "glicemia_pos_prandial": obter_campo_id("glicemia_pos_prandial"),
    "pressao_sistolica": obter_campo_id("pressao_sistolica"),
    "pressao_diastolica": obter_campo_id("pressao_diastolica"),
    "peso": obter_campo_id("peso"),
    "altura": obter_campo_id("altura"),
    "atividade_fisica": obter_campo_id("atividade_fisica"),
}

for paciente in PACIENTES:

    for i in range(30):

        data_registro = date.today() - timedelta(days=i)

        registro = db.execute(
            text("""
                INSERT INTO registros_longitudinais (
                    paciente_id,
                    modulo_id,
                    formulario_id,
                    origem,
                    data_registro
                )
                VALUES (
                    :paciente_id,
                    :modulo_id,
                    :formulario_id,
                    'PROFISSIONAL',
                    :data_registro
                )
                RETURNING id
            """),
            {
                "paciente_id": paciente["id"],
                "modulo_id": MODULO_ID,
                "formulario_id": FORMULARIO_ID,
                "data_registro": data_registro,
            }
        ).fetchone()

        registro_id = registro.id

        if paciente["perfil"] == "diabetes_descompensado":

            peso = round(
                paciente["peso_base"] + (i * 0.08) + random.uniform(-1, 1),
                1
            )

            glicemia = round(
                paciente["glicemia_base"] + (i * 2) + random.uniform(-10, 10),
                1
            )

        elif paciente["perfil"] == "hipertenso_estavel":

            peso = round(
                paciente["peso_base"] + random.uniform(-1, 1),
                1
            )

            glicemia = round(
                paciente["glicemia_base"] + random.uniform(-8, 8),
                1
            )

        elif paciente["perfil"] == "obesidade_morbida":

            peso = round(
                paciente["peso_base"] + (i * 0.12) + random.uniform(-1, 1),
                1
            )

            glicemia = round(
                paciente["glicemia_base"] + (i * 1.8) + random.uniform(-15, 15),
                1
            )

        elif paciente["perfil"] == "melhora_clinica":

            peso = round(
                paciente["peso_base"] - (i * 0.15) + random.uniform(-1, 1),
                1
            )

            glicemia = round(
                paciente["glicemia_base"] - (i * 2.2) + random.uniform(-10, 10),
                1
            )

        else:

          peso = round(
              paciente["peso_base"] + random.uniform(-2, 2),
              1
          )

          glicemia = round(
              paciente["glicemia_base"] + random.uniform(-20, 20),
              1
          )

        glicemia_pos = round(
            glicemia + random.uniform(10, 40),
            1
        )

        sistolica = round(
            paciente["pressao_base"] + random.uniform(-10, 10)
        )

        diastolica = round(
            (sistolica * 0.65) + random.uniform(-5, 5)
        )

        atividade = random.choice([True, False])

        criar_resposta(
            registro_id,
            campos["peso"],
            peso
        )

        criar_resposta(
            registro_id,
            campos["altura"],
            paciente["altura"]
        )

        criar_resposta(
            registro_id,
            campos["glicemia_jejum"],
            glicemia
        )

        criar_resposta(
            registro_id,
            campos["glicemia_pos_prandial"],
            glicemia_pos
        )

        criar_resposta(
            registro_id,
            campos["pressao_sistolica"],
            sistolica
        )

        criar_resposta(
            registro_id,
            campos["pressao_diastolica"],
            diastolica
        )

        criar_resposta(
            registro_id,
            campos["atividade_fisica"],
            atividade
        )

db.commit()

print("Seed cardiometabólico criado com sucesso.")
