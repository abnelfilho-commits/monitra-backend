import re
from datetime import date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.responsavel import Responsavel
from app.models.responsavel_paciente import ResponsavelPaciente
from app.models.whatsapp_conversa import WhatsAppConversa

from app.services.responsavel_registro_service import (
    ResponsavelRegistroService,
)

MODULO_NEURO_ID = 1
FORMULARIO_REGISTRO_NEURO_ID = 2


def registro_responsavel_existe_na_data(
    db: Session,
    paciente_id: int,
    data_referencia: date,
) -> bool:
    existente = db.execute(text("""
        SELECT id
        FROM registros_longitudinais
        WHERE paciente_id = :paciente_id
          AND modulo_id = :modulo_id
          AND formulario_id = :formulario_id
          AND data_registro = :data_registro
          AND origem = 'RESPONSAVEL'
        LIMIT 1
    """), {
        "paciente_id": paciente_id,
        "modulo_id": MODULO_NEURO_ID,
        "formulario_id": FORMULARIO_REGISTRO_NEURO_ID,
        "data_registro": data_referencia,
    }).fetchone()

    return existente is not None


def referencia_dia(conversa: WhatsAppConversa) -> str:
    ontem = date.today() - timedelta(days=1)
    return "ontem" if conversa.data_referencia == ontem else "hoje"


def iniciar_questionario(
    db: Session,
    conversa: WhatsAppConversa,
    data_referencia: date,
):
    conversa.data_referencia = data_referencia
    conversa.etapa_atual = "SONO"
    conversa.respostas_json = {}
    db.commit()

    dia = referencia_dia(conversa)

    return (
        "Ótimo! Vamos começar. 😊\n\n"
        f"Como foi a qualidade do sono {dia}?\n\n"
        "1 - Muito ruim\n"
        "2 - Ruim\n"
        "3 - Regular\n"
        "4 - Bom\n"
        "5 - Muito bom"
    )


def normalizar_telefone(telefone: str) -> str:
    """
    Mantém somente números.
    Exemplo:
    +55 (65) 99999-9999 -> 5565999999999
    """
    return re.sub(r"\D", "", telefone or "")


def buscar_responsavel_por_telefone(
    db: Session,
    telefone: str,
):
    telefone_normalizado = normalizar_telefone(telefone)

    if not telefone_normalizado:
        return None

    responsaveis = (
        db.query(Responsavel)
        .filter(Responsavel.ativo.is_(True))
        .all()
    )

    for responsavel in responsaveis:
        telefone_banco = normalizar_telefone(
            responsavel.telefone
        )

        if not telefone_banco:
            continue

        # Comparação direta
        if telefone_banco == telefone_normalizado:
            return responsavel

        # Compatibilidade caso o banco esteja sem DDI 55
        if (
            telefone_normalizado.startswith("55")
            and telefone_normalizado[2:] == telefone_banco
        ):
            return responsavel

        if (
            telefone_banco.startswith("55")
            and telefone_banco[2:] == telefone_normalizado
        ):
            return responsavel

    return None


def buscar_pacientes_vinculados(
    db: Session,
    responsavel_id: int,
):
    return (
        db.query(ResponsavelPaciente)
        .filter(
            ResponsavelPaciente.responsavel_id
            == responsavel_id,
            ResponsavelPaciente.ativo.is_(True),
        )
        .order_by(
            ResponsavelPaciente.principal.desc(),
            ResponsavelPaciente.id.asc(),
        )
        .all()
    )


def buscar_conversa_ativa(
    db: Session,
    responsavel_id: int,
    telefone: str,
):
    telefone_normalizado = normalizar_telefone(
        telefone
    )

    return (
        db.query(WhatsAppConversa)
        .filter(
            WhatsAppConversa.responsavel_id
            == responsavel_id,
            WhatsAppConversa.telefone
            == telefone_normalizado,
        )
        .order_by(
            WhatsAppConversa.updated_at.desc()
        )
        .first()
    )


def criar_conversa(
    db: Session,
    responsavel_id: int,
    telefone: str,
    paciente_id: int = None,
):
    conversa = WhatsAppConversa(
        responsavel_id=responsavel_id,
        paciente_id=paciente_id,
        telefone=normalizar_telefone(telefone),
        etapa_atual="INICIO",
        respostas_json={},
    )

    db.add(conversa)
    db.commit()
    db.refresh(conversa)

    return conversa


def iniciar_fluxo_um_paciente(
    db: Session,
    conversa: WhatsAppConversa,
    responsavel,
    vinculo,
):
    conversa.paciente_id = vinculo.paciente_id
    conversa.respostas_json = {}

    hoje = date.today()
    ontem = hoje - timedelta(days=1)

    existe_hoje = registro_responsavel_existe_na_data(
        db, vinculo.paciente_id, hoje
    )
    existe_ontem = registro_responsavel_existe_na_data(
        db, vinculo.paciente_id, ontem
    )

    nome_responsavel = (
        responsavel.nome.split()[0]
        if responsavel.nome
        else "Olá"
    )

    nome_paciente = (
        vinculo.paciente.nome.split()[0]
        if vinculo.paciente and vinculo.paciente.nome
        else "o paciente"
    )

    if existe_hoje and existe_ontem:
        conversa.etapa_atual = "INICIO"
        conversa.data_referencia = None
        conversa.paciente_id = None
        db.commit()

        return (
            f"Olá, {nome_responsavel}! 👋\n\n"
            f"Os acompanhamentos de hoje e ontem de "
            f"{nome_paciente} já foram registrados. ✅\n\n"
            "Quando houver uma nova data disponível, "
            "é só mandar uma mensagem por aqui."
        )

    if existe_hoje and not existe_ontem:
        conversa.etapa_atual = "CONFIRMAR_ONTEM"
        conversa.data_referencia = ontem
        db.commit()
        db.refresh(conversa)

        return (
            f"Olá, {nome_responsavel}! 👋\n\n"
            f"O acompanhamento de hoje de {nome_paciente} "
            f"já foi registrado.\n\n"
            f"Você gostaria de registrar como foi o dia de ontem?\n\n"
            f"1 - Sim\n"
            f"2 - Agora não"
        )

    if not existe_hoje and not existe_ontem:
        conversa.etapa_atual = "SELECIONAR_DATA"
        conversa.data_referencia = None
        db.commit()
        db.refresh(conversa)

        return (
            f"Olá, {nome_responsavel}! 👋\n\n"
            f"Qual dia você deseja registrar para {nome_paciente}?\n\n"
            f"1 - Hoje\n"
            f"2 - Ontem"
        )

    conversa.etapa_atual = "CONFIRMAR_INICIO"
    conversa.data_referencia = hoje
    db.commit()
    db.refresh(conversa)

    return (
        f"Olá, {nome_responsavel}! 👋\n\n"
        f"Vamos registrar como foi o dia de {nome_paciente}?\n\n"
        f"Responda:\n"
        f"1 - Sim\n"
        f"2 - Agora não"
    )

def processar_mensagem(
    db: Session,
    telefone: str,
    mensagem: str,
):
    """
    Motor conversacional inicial do WhatsApp.

    Ainda NÃO envia mensagem para WhatsApp.
    Apenas recebe:
        telefone
        mensagem

    E devolve:
        resposta textual
    """

    telefone_normalizado = normalizar_telefone(
        telefone
    )

    mensagem_normalizada = (
        str(mensagem or "").strip()
    )

    # -------------------------------------------------
    # 1. IDENTIFICAR RESPONSÁVEL
    # -------------------------------------------------

    responsavel = buscar_responsavel_por_telefone(
        db,
        telefone_normalizado,
    )

    if not responsavel:
        return (
            "Olá! 👋\n\n"
            "Não consegui localizar este número "
            "como responsável cadastrado no "
            "Integra Care.\n\n"
            "Entre em contato com a equipe de "
            "atendimento para atualizar seu cadastro."
        )

    # -------------------------------------------------
    # 2. BUSCAR VÍNCULOS
    # -------------------------------------------------

    vinculos = buscar_pacientes_vinculados(
        db,
        responsavel.id,
    )

    if not vinculos:
        return (
            f"Olá, {responsavel.nome.split()[0]}! 👋\n\n"
            "Seu cadastro foi localizado, mas não "
            "encontrei nenhum paciente ativo "
            "vinculado a você."
        )

    # -------------------------------------------------
    # 3. BUSCAR OU CRIAR CONVERSA
    # -------------------------------------------------

    conversa = buscar_conversa_ativa(
        db,
        responsavel.id,
        telefone_normalizado,
    )

    if not conversa:
        conversa = criar_conversa(
            db,
            responsavel.id,
            telefone_normalizado,
        )

    # -------------------------------------------------
    # 4. INÍCIO
    # -------------------------------------------------

    if conversa.etapa_atual == "INICIO":

        # MVP:
        # se houver apenas um paciente, entra direto.
        if len(vinculos) == 1:
            return iniciar_fluxo_um_paciente(
                db,
                conversa,
                responsavel,
                vinculos[0],
            )

        # Mais de um paciente:
        # pedir escolha.
        conversa.etapa_atual = "SELECIONAR_PACIENTE"

        db.commit()

        linhas = [
            f"Olá, {responsavel.nome.split()[0]}! 👋",
            "",
            "Para quem você deseja fazer "
            "o acompanhamento diário?",
            "",
        ]

        for indice, vinculo in enumerate(
            vinculos,
            start=1,
        ):
            nome = (
                vinculo.paciente.nome
                if vinculo.paciente
                else f"Paciente {vinculo.paciente_id}"
            )

            linhas.append(
                f"{indice} - {nome}"
            )

        return "\n".join(linhas)

    # -------------------------------------------------
    # 5. SELEÇÃO DE PACIENTE
    # -------------------------------------------------

    if (
        conversa.etapa_atual
        == "SELECIONAR_PACIENTE"
    ):
        try:
            escolha = int(
                mensagem_normalizada
            )
        except ValueError:
            return (
                "Por favor, responda apenas com "
                "o número correspondente ao paciente."
            )

        if escolha < 1 or escolha > len(vinculos):
            return (
                "Essa opção não está disponível.\n\n"
                "Responda com o número do paciente."
            )

        vinculo = vinculos[escolha - 1]

        return iniciar_fluxo_um_paciente(
            db,
            conversa,
            responsavel,
            vinculo,
        )

    # -------------------------------------------------
    # 6. SELECIONAR DATA (HOJE / ONTEM)
    # -------------------------------------------------

    if conversa.etapa_atual == "SELECIONAR_DATA":
        if mensagem_normalizada not in {"1", "2"}:
            return (
                "Por favor, escolha uma opção:\n\n"
                "1 - Hoje\n"
                "2 - Ontem"
            )

        data_escolhida = (
            date.today()
            if mensagem_normalizada == "1"
            else date.today() - timedelta(days=1)
        )

        if registro_responsavel_existe_na_data(
            db,
            conversa.paciente_id,
            data_escolhida,
        ):
            conversa.etapa_atual = "INICIO"
            conversa.respostas_json = {}
            conversa.data_referencia = None
            conversa.paciente_id = None
            db.commit()

            return (
                "Esse acompanhamento já foi registrado. ✅\n\n"
                "Envie uma nova mensagem para verificar "
                "as datas disponíveis."
            )

        return iniciar_questionario(
            db,
            conversa,
            data_escolhida,
        )

    # -------------------------------------------------
    # 7. CONFIRMAR REGISTRO DE ONTEM
    # -------------------------------------------------

    if conversa.etapa_atual == "CONFIRMAR_ONTEM":
        resposta = mensagem_normalizada.lower()

        respostas_sim = {"1", "sim", "s", "yes"}
        respostas_nao = {"2", "não", "nao", "n"}

        if resposta in respostas_nao:
            conversa.etapa_atual = "INICIO"
            conversa.respostas_json = {}
            conversa.data_referencia = None
            conversa.paciente_id = None
            db.commit()

            return (
                "Tudo bem! 😊\n\n"
                "Quando quiser fazer o acompanhamento, "
                "é só mandar uma mensagem por aqui."
            )

        if resposta not in respostas_sim:
            return (
                "Não entendi sua resposta. 😊\n\n"
                "Responda:\n"
                "1 - Sim\n"
                "2 - Agora não"
            )

        ontem = date.today() - timedelta(days=1)

        if registro_responsavel_existe_na_data(
            db,
            conversa.paciente_id,
            ontem,
        ):
            conversa.etapa_atual = "INICIO"
            conversa.respostas_json = {}
            conversa.data_referencia = None
            conversa.paciente_id = None
            db.commit()

            return (
                "O acompanhamento de ontem já foi registrado. ✅\n\n"
                "Envie uma nova mensagem para verificar "
                "as datas disponíveis."
            )

        return iniciar_questionario(
            db,
            conversa,
            ontem,
        )

    # -------------------------------------------------
    # 6. CONFIRMAR INÍCIO
    # -------------------------------------------------

    if (
        conversa.etapa_atual
        == "CONFIRMAR_INICIO"
    ):
        resposta = mensagem_normalizada.lower()

        respostas_sim = {
            "1",
            "sim",
            "s",
            "yes",
        }

        respostas_nao = {
            "2",
            "não",
            "nao",
            "n",
        }

        if resposta in respostas_nao:
            conversa.etapa_atual = "INICIO"
            conversa.respostas_json = {}

            db.commit()

            return (
                "Tudo bem! 😊\n\n"
                "Quando quiser fazer o acompanhamento, "
                "é só mandar uma mensagem por aqui."
            )

        if resposta not in respostas_sim:
            return (
                "Não entendi sua resposta. 😊\n\n"
                "Responda:\n"
                "1 - Sim\n"
                "2 - Agora não"
            )

        hoje = date.today()

        if registro_responsavel_existe_na_data(
            db,
            conversa.paciente_id,
            hoje,
        ):
            conversa.etapa_atual = "INICIO"
            conversa.respostas_json = {}
            conversa.data_referencia = None
            conversa.paciente_id = None
            db.commit()

            return (
                "O acompanhamento de hoje já foi registrado. ✅\n\n"
                "Envie uma nova mensagem para verificar "
                "as datas disponíveis."
            )

        return iniciar_questionario(
            db,
            conversa,
            hoje,
        )

    # -------------------------------------------------
    # 7. SONO
    # -------------------------------------------------

    if conversa.etapa_atual == "SONO":
        if mensagem_normalizada not in {"1", "2", "3", "4", "5"}:
            return (
                "Por favor, escolha uma opção:\n\n"
                "1 - Muito ruim\n"
                "2 - Ruim\n"
                "3 - Regular\n"
                "4 - Bom\n"
                "5 - Muito bom"
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["sono_qualidade"] = int(mensagem_normalizada)

        conversa.respostas_json = respostas
        conversa.etapa_atual = "EVACUACAO"

        db.commit()

        dia = referencia_dia(conversa)

        return (
            f"Houve evacuação {dia}?\n\n"
            "1 - Sim\n"
            "2 - Não"
        )

    # -------------------------------------------------
    # 8. EVACUAÇÃO
    # -------------------------------------------------

    if conversa.etapa_atual == "EVACUACAO":
        if mensagem_normalizada not in {"1", "2"}:
            return (
                "Por favor, responda:\n\n"
                "1 - Sim\n"
                "2 - Não"
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["evacuacao"] = mensagem_normalizada == "1"

        conversa.respostas_json = respostas

        if mensagem_normalizada == "1":
            conversa.etapa_atual = "BRISTOL"
            db.commit()

            dia = referencia_dia(conversa)

            return (
                f"Como estavam as fezes {dia}?\n\n"
                "1 - Muito ressecadas\n"
                "2 - Ressecadas\n"
                "3 - Tendendo a ressecadas\n"
                "4 - Normal\n"
                "5 - Tendendo a pastosas\n"
                "6 - Pastosas\n"
                "7 - Líquidas"
            )

        # Se não evacuou, Bristol não se aplica.
        respostas["consistencia_fezes"] = None
        conversa.respostas_json = respostas
        conversa.etapa_atual = "IRRITABILIDADE"

        db.commit()

        dia = referencia_dia(conversa)

        return (
            f"Como estava a irritabilidade {dia}?\n\n"
            "0 - Nenhuma\n"
            "1 - Leve\n"
            "2 - Moderada\n"
            "3 - Alta\n"
            "4 - Muito alta"
        )

    # -------------------------------------------------
    # 9. BRISTOL
    # -------------------------------------------------

    if conversa.etapa_atual == "BRISTOL":
        if mensagem_normalizada not in {
            "1", "2", "3", "4", "5", "6", "7"
        }:
            return (
                "Escolha uma opção de 1 a 7 para "
                "a consistência das fezes."
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["consistencia_fezes"] = int(mensagem_normalizada)

        conversa.respostas_json = respostas
        conversa.etapa_atual = "IRRITABILIDADE"

        db.commit()

        dia = referencia_dia(conversa)

        return (
            f"Como estava a irritabilidade {dia}?\n\n"
            "0 - Nenhuma\n"
            "1 - Leve\n"
            "2 - Moderada\n"
            "3 - Alta\n"
            "4 - Muito alta"
        )

    # -------------------------------------------------
    # 10. IRRITABILIDADE
    # -------------------------------------------------

    if conversa.etapa_atual == "IRRITABILIDADE":
        if mensagem_normalizada not in {"0", "1", "2", "3", "4"}:
            return (
                "Escolha uma opção:\n\n"
                "0 - Nenhuma\n"
                "1 - Leve\n"
                "2 - Moderada\n"
                "3 - Alta\n"
                "4 - Muito alta"
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["irritabilidade"] = int(mensagem_normalizada)

        conversa.respostas_json = respostas
        conversa.etapa_atual = "CRISE_SENSORIAL"

        db.commit()

        dia = referencia_dia(conversa)

        return (
            f"Houve crise sensorial {dia}?\n\n"
            "0 - Não\n"
            "1 - Leve\n"
            "2 - Moderada\n"
            "3 - Intensa"
        )

    # -------------------------------------------------
    # 11. CRISE SENSORIAL
    # -------------------------------------------------

    if conversa.etapa_atual == "CRISE_SENSORIAL":
        if mensagem_normalizada not in {"0", "1", "2", "3"}:
            return (
                "Escolha uma opção:\n\n"
                "0 - Não\n"
                "1 - Leve\n"
                "2 - Moderada\n"
                "3 - Intensa"
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["crise_sensorial"] = int(mensagem_normalizada)

        conversa.respostas_json = respostas
        conversa.etapa_atual = "TEMPO_TELA"

        db.commit()

        dia = referencia_dia(conversa)

        return (
            f"Quanto tempo de tela teve {dia}?\n\n"
            "1 - Menos de 1 hora\n"
            "2 - 1 a 2 horas\n"
            "3 - 2 a 4 horas\n"
            "4 - Mais de 4 horas"
        )

    # -------------------------------------------------
    # 12. TEMPO DE TELA
    # -------------------------------------------------

    if conversa.etapa_atual == "TEMPO_TELA":
        mapa_tela = {
            "1": "MENOS_1H",
            "2": "1_2H",
            "3": "2_4H",
            "4": "MAIS_4H",
        }

        if mensagem_normalizada not in mapa_tela:
            return (
                "Escolha uma opção:\n\n"
                "1 - Menos de 1 hora\n"
                "2 - 1 a 2 horas\n"
                "3 - 2 a 4 horas\n"
                "4 - Mais de 4 horas"
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["tempo_tela"] = mapa_tela[mensagem_normalizada]

        conversa.respostas_json = respostas
        conversa.etapa_atual = "SELETIVIDADE"

        db.commit()

        dia = referencia_dia(conversa)

        return (
            f"Como estava a seletividade alimentar {dia}?\n\n"
            "0 - Nenhuma\n"
            "1 - Leve\n"
            "2 - Moderada\n"
            "3 - Grave"
        )

    # -------------------------------------------------
    # 13. SELETIVIDADE ALIMENTAR
    # -------------------------------------------------

    if conversa.etapa_atual == "SELETIVIDADE":
        mapa_seletividade = {
            "0": "NENHUMA",
            "1": "LEVE",
            "2": "MODERADA",
            "3": "GRAVE",
        }

        if mensagem_normalizada not in mapa_seletividade:
            return (
                "Escolha uma opção:\n\n"
                "0 - Nenhuma\n"
                "1 - Leve\n"
                "2 - Moderada\n"
                "3 - Grave"
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["seletividade_alimentar"] = (
            mapa_seletividade[mensagem_normalizada]
        )

        conversa.respostas_json = respostas
        conversa.etapa_atual = "ALIMENTO_NOVO"

        db.commit()

        dia = referencia_dia(conversa)

        return (
            f"Aceitou algum alimento novo {dia}?\n\n"
            "1 - Sim\n"
            "2 - Não"
        )

    # -------------------------------------------------
    # 14. ALIMENTO NOVO
    # -------------------------------------------------

    if conversa.etapa_atual == "ALIMENTO_NOVO":
        if mensagem_normalizada not in {"1", "2"}:
            return (
                "Por favor, responda:\n\n"
                "1 - Sim\n"
                "2 - Não"
            )

        respostas = dict(conversa.respostas_json or {})
        respostas["aceitou_alimento_novo"] = (
            mensagem_normalizada == "1"
        )

        conversa.respostas_json = respostas
        conversa.etapa_atual = "OBSERVACAO"

        db.commit()

        return (
            "Para finalizar, aconteceu algo importante "
            "que você gostaria de contar para a equipe?\n\n"
            "Digite sua observação ou responda:\n"
            "0 - Nada a acrescentar"
        )

    # -------------------------------------------------
    # 15. OBSERVAÇÃO
    # -------------------------------------------------

    if conversa.etapa_atual == "OBSERVACAO":
        respostas = dict(conversa.respostas_json or {})

        respostas["observacao"] = (
            None
            if mensagem_normalizada == "0"
            else mensagem_normalizada
        )

        conversa.respostas_json = respostas
        conversa.etapa_atual = "CONFIRMAR_REGISTRO"

        db.commit()

        nome_paciente = "paciente"

        for vinculo in vinculos:
            if vinculo.paciente_id == conversa.paciente_id:
                if vinculo.paciente and vinculo.paciente.nome:
                    nome_paciente = vinculo.paciente.nome.split()[0]
                break

        return (
            f"Pronto! 😊\n\n"
            f"Já tenho as informações sobre o dia de "
            f"{nome_paciente}.\n\n"
            f"Deseja enviar este acompanhamento para "
            f"a equipe?\n\n"
            f"1 - Sim, enviar\n"
            f"2 - Cancelar"
        )

    # -------------------------------------------------
    # 16. CONFIRMAÇÃO FINAL E REGISTRO
    # -------------------------------------------------

    if conversa.etapa_atual == "CONFIRMAR_REGISTRO":

        if mensagem_normalizada == "2":
            conversa.etapa_atual = "INICIO"
            conversa.respostas_json = {}
            conversa.data_referencia = None
            conversa.paciente_id = None

            db.commit()

            return (
                "Tudo bem. 😊\n\n"
                "O acompanhamento foi cancelado e "
                "nenhuma informação foi registrada."
            )

        if mensagem_normalizada != "1":
            return (
                "Por favor, responda:\n\n"
                "1 - Sim, enviar\n"
                "2 - Cancelar"
            )

        respostas = dict(
            conversa.respostas_json or {}
        )

        try:
            registro = (
                ResponsavelRegistroService
                .criar_registro_neuro(
                    db=db,
                    responsavel_id=responsavel.id,
                    paciente_id=conversa.paciente_id,
                    data_registro=(
                        conversa.data_referencia
                        or date.today()
                    ),
                    respostas=respostas,
                )
            )

        except ValueError as erro:
            return (
                "Não consegui enviar o acompanhamento."
                "\n\n"
                f"{str(erro)}"
            )

        nome_paciente = "paciente"

        for vinculo in vinculos:
            if (
                vinculo.paciente_id
                == conversa.paciente_id
            ):
                if (
                    vinculo.paciente
                    and vinculo.paciente.nome
                ):
                    nome_paciente = (
                        vinculo.paciente.nome
                        .split()[0]
                    )

                break

        registro_id = registro.id

        # Limpar conversa para o próximo dia
        conversa.etapa_atual = "INICIO"
        conversa.respostas_json = {}
        conversa.data_referencia = None
        conversa.paciente_id = None

        db.commit()

        return (
            "✅ Acompanhamento enviado com sucesso!"
            "\n\n"
            f"Obrigado por acompanhar o dia de "
            f"{nome_paciente}. 💙"
            "\n\n"
            "As informações já estão disponíveis "
            "para a equipe responsável pelo cuidado."
            "\n\n"
            f"Registro #{registro_id}"
        )