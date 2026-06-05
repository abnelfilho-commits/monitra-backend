from sqlalchemy.orm import Session
from app.models import (
    RegistroLongitudinal,
    RespostaRegistro
)


def criar_registro_longitudinal(db: Session, payload):
    registro = RegistroLongitudinal(
        paciente_id=payload.paciente_id,
        modulo_id=payload.modulo_id,
        formulario_id=payload.formulario_id,
        data_registro=payload.data_registro,
        origem=payload.origem,
    )

    db.add(registro)
    db.flush()

    for resposta in payload.respostas:
        r = RespostaRegistro(
            registro_id=registro.id,
            campo_id=resposta.campo_id
        )

        valor = resposta.valor

        if isinstance(valor, bool):
            r.valor_booleano = valor
        elif isinstance(valor, (int, float)):
            r.valor_numero = valor
        elif isinstance(valor, str):
            r.valor_texto = valor
        else:
            r.valor_json = valor

        db.add(r)

    db.commit()
    db.refresh(registro)

    return registro
