from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import (
    RegistroLongitudinal,
    RespostaRegistro,
    CampoFormulario,
)

from app.models import FormularioModulo

from app.services.clinical_engine.assessment_service import (
    executar_avaliacao_por_registro,
)

def extrair_valor(resposta: RespostaRegistro):
    if resposta.valor_booleano is not None:
        return resposta.valor_booleano

    if resposta.valor_numero is not None:
        valor = resposta.valor_numero
        try:
            if valor == int(valor):
                return int(valor)
        except Exception:
            pass
        return float(valor)

    if resposta.valor_texto is not None:
        return resposta.valor_texto

    if resposta.valor_data is not None:
        return resposta.valor_data

    if resposta.valor_hora is not None:
        return resposta.valor_hora

    if resposta.valor_json is not None:
        return resposta.valor_json

    return None


def preencher_resposta(resposta: RespostaRegistro, valor):
    resposta.valor_texto = None
    resposta.valor_numero = None
    resposta.valor_booleano = None
    resposta.valor_data = None
    resposta.valor_hora = None
    resposta.valor_json = None

    if isinstance(valor, bool):
        resposta.valor_booleano = valor
    elif isinstance(valor, (int, float)):
        resposta.valor_numero = valor
    elif isinstance(valor, str):
        resposta.valor_texto = valor
    else:
        resposta.valor_json = valor


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

    for item in payload.respostas:
        resposta = RespostaRegistro(
            registro_id=registro.id,
            campo_id=item.campo_id,
        )

        preencher_resposta(resposta, item.valor)
        db.add(resposta)
        
        print("RESPOSTA:", item.campo_id, item.valor)
        
    db.commit()
    db.refresh(registro)

    formulario = (
        db.query(FormularioModulo)
        .filter(FormularioModulo.id == registro.formulario_id)
        .first()
    )

    if formulario and formulario.tipo == "ASSESSMENT":

        instrumento = (
            formulario.codigo
            if formulario.codigo
            else formulario.nome.upper().replace("-", "").replace(" ", "_")
        )

        try:
            executar_avaliacao_por_registro(
                db=db,
                registro_id=registro.id,
                instrumento=instrumento,
            )

        except Exception as e:
            print(f"Erro ao executar assessment: {e}")

    return registro


def obter_registro_longitudinal(db: Session, registro_id: int):
    registro = (
        db.query(RegistroLongitudinal)
        .filter(RegistroLongitudinal.id == registro_id)
        .first()
    )

    if not registro:
        raise HTTPException(status_code=404, detail="Registro longitudinal não encontrado.")

    respostas = (
        db.query(RespostaRegistro, CampoFormulario)
        .join(CampoFormulario, CampoFormulario.id == RespostaRegistro.campo_id)
        .filter(RespostaRegistro.registro_id == registro.id)
        .all()
    )

    respostas_dict = {}

    for resposta, campo in respostas:
        respostas_dict[campo.nome_campo] = extrair_valor(resposta)

    return {
        "id": registro.id,
        "paciente_id": registro.paciente_id,
        "modulo_id": registro.modulo_id,
        "formulario_id": registro.formulario_id,
        "data_registro": registro.data_registro,
        "origem": registro.origem,
        "respostas": respostas_dict,
    }


def atualizar_registro_longitudinal(db: Session, registro_id: int, payload):
    registro = (
        db.query(RegistroLongitudinal)
        .filter(RegistroLongitudinal.id == registro_id)
        .first()
    )

    if not registro:
        raise HTTPException(status_code=404, detail="Registro longitudinal não encontrado.")

    registro.paciente_id = payload.paciente_id
    registro.modulo_id = payload.modulo_id
    registro.formulario_id = payload.formulario_id
    registro.data_registro = payload.data_registro
    registro.origem = payload.origem

    db.query(RespostaRegistro).filter(
        RespostaRegistro.registro_id == registro.id
    ).delete()

    db.flush()

    for item in payload.respostas:
        resposta = RespostaRegistro(
            registro_id=registro.id,
            campo_id=item.campo_id,
        )

        preencher_resposta(resposta, item.valor)
        db.add(resposta)

    db.commit()
    db.refresh(registro)

    return obter_registro_longitudinal(db, registro.id)